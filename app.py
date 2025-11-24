import streamlit as st
import requests
import json
import datetime
from google import genai

# Set page configuration
st.set_page_config(page_title="Creative Studio", page_icon="🎨", layout="wide")

# --- CSS Injection ---
try:
    with open('style.css') as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
except FileNotFoundError:
    pass # Graceful fallback if style.css is missing

# --- Secrets Management ---
try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ `GEMINI_API_KEY` not found in `secrets.toml`. Please configure it to proceed.")
    st.stop()

canvas_key_default = ""
try:
    if "CANVAS_API_KEY" in st.secrets:
        canvas_key_default = st.secrets["CANVAS_API_KEY"]
except FileNotFoundError:
    pass

# --- Sidebar ---
with st.sidebar:
    st.markdown("### Configuration")
    with st.expander("🔌 Settings", expanded=False):
        canvas_url = st.text_input("Canvas URL", placeholder="https://canvas.instructure.com")
        course_id = st.text_input("Course ID", placeholder="e.g., 12345")
        api_token = st.text_input("Canvas API Token", value=canvas_key_default, type="password", placeholder="Your Canvas API Token")

# --- Main Interface ---
st.markdown('<h1 class="hero-header">Creative Studio</h1>', unsafe_allow_html=True)
st.markdown('<p class="hero-sub">Design engaging learning experiences with AI</p>', unsafe_allow_html=True)

# Main Inputs
topic = st.text_input("Topic", placeholder="Enter the main topic (e.g., The Great Gatsby)", help="The core subject matter.")
col_sub, col_type = st.columns([2, 1])
with col_sub:
    subtopic = st.text_input("Subtopic", placeholder="Specific focus (e.g., Symbolism of the Green Light)")
with col_type:
    content_type = st.radio("Content Type", ["Assignment", "Quiz"], horizontal=True)

# --- Differentiation & Accommodations ---
with st.expander('♿ Differentiation & Accommodations'):
    sped_toggle = st.toggle('Generate SPED Accommodation Version')
    ml_toggle = st.toggle('Generate Multilingual Learner (ML) Version')
    
    target_language = "Spanish" # Default
    if ml_toggle:
        target_language = st.selectbox('Target Home Language', ['Spanish', 'Portuguese', 'Arabic', 'Vietnamese', 'Chinese', 'French', 'Haitian Creole', 'Russian', 'Other'])

# Curriculum Alignment (Preserved from previous step)
col_grade, col_standard = st.columns([1, 2])
with col_grade:
    grade_level = st.selectbox("Target Grade Level", ['K', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', 'Higher Ed'])
with col_standard:
    standard = st.text_input("State Standard / Learning Objective", placeholder="e.g., Utah Standard 9-10.SL.1")

# --- Advanced Options ---
st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

with st.expander("⚙️ Advanced Options", expanded=False):
    st.markdown("#### Logistics")
    col_dates, col_points, col_attempts = st.columns([2, 1, 1])
    
    with col_dates:
        today = datetime.date.today()
        next_week = today + datetime.timedelta(days=7)
        date_range = st.date_input("Schedule (Start - End)", value=(today, next_week))
        
        # Date Logic
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            unlock_at = datetime.datetime.combine(start_date, datetime.time(0, 0)).isoformat()
            due_at = datetime.datetime.combine(end_date, datetime.time(23, 59)).isoformat()
            lock_at = due_at
        elif isinstance(date_range, tuple) and len(date_range) == 1:
            start_date = date_range[0]
            unlock_at = datetime.datetime.combine(start_date, datetime.time(0, 0)).isoformat()
            due_at = None
            lock_at = None
        else:
            unlock_at = datetime.datetime.now().isoformat()
            due_at = None
            lock_at = None

    with col_points:
        points_possible = st.number_input("Points", min_value=0, value=20)
    
    with col_attempts:
        attempts_choice = st.selectbox("Allowed Attempts", ['Unlimited', '1', '2', '3'])
        # Logic moved to publish time to ensure fresh state
        
    st.markdown("---")
    
    # Type Specific Settings
    quiz_settings = {}
    assignment_settings = {}

    if content_type == "Quiz":
        st.markdown("#### Quiz Settings")
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            num_questions = st.number_input("Questions", min_value=1, max_value=20, value=5)
            shuffle_answers = st.checkbox("Shuffle Answers", value=True)
        with col_q2:
            time_limit = st.number_input("Time Limit (mins)", min_value=0, value=30)
            one_question_at_a_time = st.checkbox("One Question at a Time", value=False)
        
        quiz_settings = {
            "num_questions": num_questions,
            "time_limit": time_limit,
            "shuffle_answers": shuffle_answers,
            "one_question_at_a_time": one_question_at_a_time
        }
    else: # Assignment
        st.markdown("#### Submission Types")
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        with col_s1: s_text = st.checkbox("Text Entry", value=True)
        with col_s2: s_url = st.checkbox("Website URL", value=True)
        with col_s3: s_media = st.checkbox("Media Recording")
        with col_s4: s_file = st.checkbox("File Upload")
        
        selected_types = []
        if s_text: selected_types.append('online_text_entry')
        if s_url: selected_types.append('online_url')
        if s_media: selected_types.append('media_recording')
        if s_file: selected_types.append('online_upload')
        
        assignment_settings = {"submission_types": selected_types}

# Initialize session state
if 'generated_content' not in st.session_state:
    st.session_state.generated_content = None

# --- Action Area ---
st.markdown("<div style='margin-top: 2rem; text-align: center;'>", unsafe_allow_html=True)
if st.button("Generate Content ✨", type="primary", use_container_width=True):
    if not topic:
        st.warning("Please enter a topic.")
    else:
        try:
            with st.spinner(f"✨ Designing {content_type.lower()}..."):
                client = genai.Client(api_key=gemini_api_key)
                target_standard = standard if standard else "general educational standards"
                
                if content_type == "Quiz":
                    prompt = f"""
                    Act as an expert teacher for Grade {grade_level}. Research the topic '{topic}' (Subtopic: '{subtopic}').
                    Create a Canvas Quiz with {quiz_settings['num_questions']} multiple-choice questions.
                    CRITICAL: Ensure alignment with standard: {target_standard}.
                    Return ONLY a valid JSON object:
                    - "title": Creative title.
                    - "description": HTML description/instructions.
                    - "questions": List of objects with "question_name", "question_text", "question_type": "multiple_choice_question", "answers" (list of {{"text": "...", "weight": 100/0}}).
                    """
                else: # Assignment
                    prompt = f"""
                    Act as an expert teacher for Grade {grade_level}. Research the topic '{topic}' (Subtopic: '{subtopic}').
                    Create a Canvas Assignment.
                    CRITICAL: Ensure alignment with standard: {target_standard}.
                    Return ONLY a valid JSON object:
                    - "title": Creative title.
                    - "description": HTML description with instructions & rubric.
                    - "questions": []
                    """
                
                # Differentiation Logic
                if sped_toggle:
                    prompt += "\nMODIFICATION: The student has an IEP/504. Rewrite the assignment description to use simplified vocabulary (Lexile 600-800), chunked instructions with clear headers, and 50% extra time allocation. If creating a quiz, reduce option choices from 4 to 3."
                
                if ml_toggle:
                    prompt += f"\nMODIFICATION: The student is a Multilingual Learner. Provide key vocabulary definitions translated into {target_language} in parentheses. Simplify sentence structures and avoid idioms. Ensure cultural context is explained."

                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt
                )
                
                # JSON Parsing
                response_text = response.text
                if response_text.startswith("```json"): response_text = response_text[7:]
                if response_text.endswith("```"): response_text = response_text[:-3]
                
                st.session_state.generated_content = json.loads(response_text.strip())
                
                # Append Modified Tag
                if sped_toggle or ml_toggle:
                    st.session_state.generated_content['title'] += " -(Modified)"
                st.success("Design complete!")

        except Exception as e:
            st.error(f"Generation failed: {str(e)}")
st.markdown("</div>", unsafe_allow_html=True)

# --- Preview & Publish ---
if st.session_state.generated_content:
    data = st.session_state.generated_content
    st.markdown("---")
    st.subheader("Preview")
    
    with st.container(border=True):
        st.markdown(f"## {data.get('title')}")
        st.markdown(data.get('description'), unsafe_allow_html=True)
        if content_type == "Quiz" and data.get('questions'):
            with st.expander(f"View {len(data['questions'])} Questions"):
                st.json(data['questions'])

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    
    col_pub_1, col_pub_2 = st.columns([1, 3])
    with col_pub_2:
        if st.button("Publish to Canvas 🚀", type="primary", use_container_width=True):
            if not canvas_url or not course_id or not api_token:
                st.error("Please configure Canvas settings in the sidebar.")
            else:
                base_url = canvas_url.rstrip('/')
                headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
                
                try:
                    with st.spinner("Publishing..."):
                        # 1. Sanitize Data
                        final_attempts = -1 if attempts_choice == 'Unlimited' else int(attempts_choice)
                        final_points = float(points_possible)
                        
                        # 2. Date Handling
                        final_unlock = None
                        final_due = None
                        final_lock = None
                        
                        if date_range:
                            # Handle tuple unpacking safely
                            if isinstance(date_range, tuple):
                                if len(date_range) == 2:
                                    start_d, end_d = date_range
                                    final_unlock = start_d.isoformat() + 'T00:00:00Z'
                                    final_due = end_d.isoformat() + 'T23:59:59Z'
                                    final_lock = final_due
                                elif len(date_range) == 1:
                                    start_d = date_range[0]
                                    final_unlock = start_d.isoformat() + 'T00:00:00Z'
                            else:
                                # Fallback if it's just a single date object
                                final_unlock = date_range.isoformat() + 'T00:00:00Z'

                        common_payload = {
                            "description": data.get('description'),
                            "published": True
                        }
                        if final_due: common_payload["due_at"] = final_due
                        if final_unlock: common_payload["unlock_at"] = final_unlock
                        if final_lock: common_payload["lock_at"] = final_lock

                        if content_type == "Assignment":
                            endpoint = f"{base_url}/api/v1/courses/{course_id}/assignments"
                            payload = {
                                "assignment": {
                                    "name": data.get('title'),
                                    "points_possible": final_points,
                                    "allowed_attempts": final_attempts,
                                    "submission_types": assignment_settings['submission_types'],
                                    **common_payload
                                }
                            }
                            
                            st.write("DEBUG Payload:", payload)
                            
                            res = requests.post(endpoint, headers=headers, json=payload)
                            res.raise_for_status()
                            st.success(f"Published! [View in Canvas]({res.json().get('html_url')})")
                            st.balloons()

                        else: # Quiz
                            endpoint = f"{base_url}/api/v1/courses/{course_id}/quizzes"
                            payload = {
                                "quiz": {
                                    "title": data.get('title'),
                                    "quiz_type": "assignment",
                                    "time_limit": quiz_settings['time_limit'],
                                    "shuffle_answers": quiz_settings['shuffle_answers'],
                                    "one_question_at_a_time": quiz_settings['one_question_at_a_time'],
                                    "allowed_attempts": final_attempts,
                                    **common_payload
                                }
                            }
                            
                            st.write("DEBUG Payload:", payload)
                            
                            res = requests.post(endpoint, headers=headers, json=payload)
                            res.raise_for_status()
                            quiz_data = res.json()
                            
                            # Questions
                            q_endpoint = f"{base_url}/api/v1/courses/{course_id}/quizzes/{quiz_data.get('id')}/questions"
                            prog = st.progress(0)
                            questions = data.get('questions', [])
                            for i, q in enumerate(questions):
                                q_payload = {
                                    "question": {
                                        "question_name": q.get('question_name'),
                                        "question_text": q.get('question_text'),
                                        "question_type": "multiple_choice_question",
                                        "points_possible": points_possible / len(questions) if len(questions) > 0 else 1,
                                        "answers": q.get('answers')
                                    }
                                }
                                requests.post(q_endpoint, headers=headers, json=q_payload)
                                prog.progress((i+1)/len(questions))
                            
                            st.success(f"Published! [View in Canvas]({quiz_data.get('html_url')})")
                            st.balloons()

                except Exception as e:
                    st.error(f"Publishing failed: {str(e)}")
