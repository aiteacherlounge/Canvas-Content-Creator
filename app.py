import streamlit as st
import requests
import json
import datetime
import re
from google import genai

# --- Page Configuration ---
st.set_page_config(page_title="Creative Studio", page_icon="🎨", layout="wide")

# --- CSS Injection ---
try:
    with open('style.css') as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
except FileNotFoundError:
    pass

# --- Helper Functions ---
def clean_json(text):
    """Sanitizes AI output to ensure valid JSON."""
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def extract_text(uploaded_file):
    """Extracts text from PDF, DOCX, XLSX, CSV, or TXT files."""
    try:
        if uploaded_file.name.endswith('.pdf'):
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            return "\\n".join([page.extract_text() for page in reader.pages])
        elif uploaded_file.name.endswith('.docx'):
            import docx
            doc = docx.Document(uploaded_file)
            return "\\n".join([para.text for para in doc.paragraphs])
        elif uploaded_file.name.endswith(('.xlsx', '.csv')):
            import pandas as pd
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            return df.to_string()
        else: # txt
            return uploaded_file.read().decode("utf-8")
    except Exception as e:
        return f"Error reading file: {str(e)}"

# --- Authentication (Session Gate) ---
if 'canvas_token' not in st.session_state:
    st.session_state.canvas_token = None

if not st.session_state.canvas_token:
    st.markdown("## 🔐 Authentication Required")
    
    # Terms of Service
    with st.expander("📜 Read Terms & Conditions", expanded=False):
        st.markdown("""
        ### 1. Data Privacy (RAM Only)
        - **No Database Storage**: Your Canvas API Token is **NOT** stored in any database or file.
        - **Session Only**: The token lives only in your browser's temporary 'Session State' and is wiped immediately when you close this tab.
        - **FERPA Compliance**: This tool is a **Content Generator**. It does **NOT** read, access, or store any Student Data.

        ### 2. AI Liability (Human-in-the-Loop)
        - **AI Warning**: Artificial Intelligence can make mistakes (hallucinations).
        - **Teacher Responsibility**: The Teacher acknowledges they are the **final editor** and responsible for reviewing all Quizzes/Assignments for accuracy before publishing to students.

        ### 3. Limitation of Liability
        - The developer is not responsible for any data loss, course disruption, or incorrect grading resulting from the use of this tool.
        """)
    
    tos_agreed = st.checkbox("I have read and agree to the Terms of Service and Privacy Policy.")
    
    token_input = st.text_input("Paste Canvas API Token", type="password", help="Your token is stored in temporary session memory only.")
    
    if st.button("Enter Creative Studio"):
        if not tos_agreed:
            st.warning("⚠️ You must agree to the Terms of Service to proceed.")
        elif token_input:
            st.session_state.canvas_token = token_input
            st.rerun()
        else:
            st.warning("Please enter a valid Canvas API Token.")
    
    st.markdown("---")
    st.info("Need a token? [How to get a Canvas API Token](https://community.canvaslms.com/t5/Admin-Guide/How-do-I-manage-API-access-tokens-as-an-admin/ta-p/89)")
    st.stop()

# --- Secrets Management (Gemini) ---
try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    st.error("⚠️ `GEMINI_API_KEY` not found in `secrets.toml`.")
    st.stop()

# --- Main Interface (Creative Studio) ---
st.markdown('<h1 class="hero-header">Creative Studio</h1>', unsafe_allow_html=True)
st.markdown('<p class="hero-sub">Design engaging learning experiences with AI</p>', unsafe_allow_html=True)

# 1. Hero Input
topic = st.text_input("Topic", placeholder="Enter the main topic (e.g., The Great Gatsby)", label_visibility="collapsed")
subtopic = st.text_input("Subtopic (Optional)", placeholder="Specific focus (e.g., Symbolism of the Green Light)")
uploaded_file = st.file_uploader("📂 Upload Source Material (Optional)", type=['pdf', 'docx', 'xlsx', 'txt', 'csv'], help="For Google Docs/Sheets, please download them as PDF or Excel first.")

# 2. Curriculum & Differentiation
col_grade, col_standard = st.columns([1, 2])
with col_grade:
    grade_level = st.selectbox("Grade Level", ['K', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', 'Higher Ed'])
with col_standard:
    standard = st.text_input("State Standard / Objective", placeholder="e.g., TEKS 4.2B or CCSS.ELA-LITERACY.RL.9-10.1")

# Differentiation Toggles
col_diff1, col_diff2 = st.columns(2)
with col_diff1:
    sped_toggle = st.toggle('Generate SPED Accommodation Version')
with col_diff2:
    ml_toggle = st.toggle('Generate Multilingual Learner (ML) Version')

if ml_toggle:
    target_language = st.selectbox('Target Home Language', ['Spanish', 'Portuguese', 'Arabic', 'Vietnamese', 'Chinese', 'French', 'Haitian Creole', 'Russian', 'Other'])
else:
    target_language = "Spanish"

# 3. Content Type
content_type = st.radio("Content Type", ["Assignment", "Quiz"], horizontal=True)

# 4. Advanced Settings (Collapsed)
with st.expander("⚙️ Advanced Settings", expanded=False):
    st.markdown("#### Canvas Configuration")
    canvas_url = st.text_input("Canvas URL", value="https://canvas.instructure.com")
    course_id = st.text_input("Course ID", placeholder="e.g., 12345")
    
    st.markdown("#### Logistics")
    col_dates, col_points, col_attempts = st.columns([2, 1, 1])
    
    with col_dates:
        today = datetime.date.today()
        next_week = today + datetime.timedelta(days=7)
        date_range = st.date_input("Schedule (Start - End)", value=(today, next_week))
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            start_time = st.time_input("Start Time", value=datetime.time(8, 0))
        with col_t2:
            due_time = st.time_input("Due Time", value=datetime.time(23, 59))
    
    with col_points:
        points_possible = st.number_input("Points", min_value=0, value=20)
    
    with col_attempts:
        attempts_choice = st.selectbox("Allowed Attempts", ['Unlimited', '1', '2', '3'])

    # Type Specific
    quiz_settings = {}
    assignment_settings = {}
    
    if content_type == "Quiz":
        st.markdown("#### Quiz Options")
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            num_questions = st.number_input("Questions", min_value=1, max_value=50, value=10)
            shuffle_answers = st.checkbox("Shuffle Answers", value=True)
        with col_q2:
            time_limit = st.number_input("Time Limit (mins)", min_value=0, value=30)
            one_question_at_a_time = st.checkbox("One Question at a Time", value=False)
        
        question_types = st.multiselect("Included Question Types", 
            ['Multiple Choice', 'True/False', 'Short Answer (Fill-in-Blank)', 'Multiple Select', 'Matching', 'Essay'],
            default=['Multiple Choice'])
        st.caption("The AI will mix these types randomly to reach your total question count.")

        quiz_settings = {
            "num_questions": num_questions,
            "time_limit": time_limit,
            "shuffle_answers": shuffle_answers,
            "one_question_at_a_time": one_question_at_a_time,
            "question_types": question_types
        }
    else:
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

# --- Generation Logic ---
if 'generated_content' not in st.session_state:
    st.session_state.generated_content = None

st.markdown("<div style='margin-top: 2rem; text-align: center;'>", unsafe_allow_html=True)
if st.button("Generate Content ✨", type="primary", use_container_width=True):
    if not topic:
        st.warning("Please enter a topic.")
    else:
        try:
            with st.spinner(f"✨ Designing {content_type.lower()}..."):
                client = genai.Client(api_key=gemini_api_key)
                target_standard = standard if standard else "general educational standards"
                
                # Source Material Extraction
                source_text = ""
                if uploaded_file:
                    source_text = extract_text(uploaded_file)
                
                # Prompt Construction & API Call
                if content_type == "Quiz":
                    all_questions = []
                    total_questions = quiz_settings['num_questions']
                    batch_size = 10
                    num_batches = (total_questions + batch_size - 1) // batch_size
                    
                    prog_gen = st.progress(0, text="Initializing generation...")
                    
                    generated_title = ""
                    generated_description = ""
                    
                    for i in range(num_batches):
                        prog_gen.progress((i) / num_batches, text=f"Generating Batch {i+1} of {num_batches}...")
                        
                        current_batch_size = min(batch_size, total_questions - len(all_questions))
                        
                        prompt = f"""
                        Act as an expert teacher for Grade {grade_level}. Research the topic '{topic}' (Subtopic: '{subtopic}').
                        Create a Canvas Quiz with {current_batch_size} questions.
                        Mix the following question types: {', '.join(quiz_settings['question_types'])}.
                        CRITICAL: Ensure alignment with standard: {target_standard}.
                        Return ONLY a valid JSON object:
                        - "title": Creative title.
                        - "description": HTML description/instructions.
                        - "questions": List of objects with:
                            - "question_name": Short identifier.
                            - "question_text": The question content.
                            - "question_type": One of ['multiple_choice_question', 'true_false_question', 'short_answer_question', 'multiple_answers_question', 'matching_question', 'essay_question'].
                            - "correct_feedback": Explanation for correct answer.
                            - "incorrect_feedback": Hint for wrong answers.
                            - "answers": List of objects based on type:
                                - Multiple Choice/True False/Multiple Select: {{"text": "...", "weight": 100/0}}
                                - Short Answer: {{"text": "Acceptable Answer", "weight": 100}}
                                - Matching: {{"answer_match_left": "Key", "answer_match_right": "Value"}}
                                - Essay: [] (Empty list)
                        """
                        
                        # Avoid duplicates
                        if all_questions:
                            existing_names = [q.get('question_name', '') for q in all_questions]
                            prompt += f"\\nIMPORTANT: Do NOT repeat these questions: {', '.join(existing_names[:20])}..."

                        # Source Material Injection
                        if source_text:
                            prompt += f"\\nSOURCE MATERIAL: {source_text}\\nINSTRUCTION: Create the content based EXCLUSIVELY on the source material above."
                        
                        # Differentiation
                        if sped_toggle:
                            prompt += "\\nMODIFICATION: The student has an IEP/504. Rewrite the assignment description to use simplified vocabulary (Lexile 600-800), chunked instructions with clear headers, and 50% extra time allocation. If creating a quiz, reduce option choices from 4 to 3."
                        if ml_toggle:
                            prompt += f"\\nMODIFICATION: The student is a Multilingual Learner. Provide key vocabulary definitions translated into {target_language} in parentheses. Simplify sentence structures and avoid idioms. Ensure cultural context is explained."

                        # API Call
                        response = client.models.generate_content(
                            model='gemini-2.0-flash',
                            contents=prompt
                        )
                        
                        # Parse & Sanitize
                        batch_data = json.loads(clean_json(response.text))
                        
                        if i == 0:
                            generated_title = batch_data.get('title')
                            generated_description = batch_data.get('description')
                        
                        all_questions.extend(batch_data.get('questions', []))
                    
                    prog_gen.empty()
                    
                    data = {
                        "title": generated_title,
                        "description": generated_description,
                        "questions": all_questions
                    }

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
                    
                    # Source Material Injection
                    if source_text:
                        prompt += f"\\nSOURCE MATERIAL: {source_text}\\nINSTRUCTION: Create the content based EXCLUSIVELY on the source material above."
                    
                    # Differentiation
                    if sped_toggle:
                        prompt += "\\nMODIFICATION: The student has an IEP/504. Rewrite the assignment description to use simplified vocabulary (Lexile 600-800), chunked instructions with clear headers, and 50% extra time allocation. If creating a quiz, reduce option choices from 4 to 3."
                    if ml_toggle:
                        prompt += f"\\nMODIFICATION: The student is a Multilingual Learner. Provide key vocabulary definitions translated into {target_language} in parentheses. Simplify sentence structures and avoid idioms. Ensure cultural context is explained."

                    # API Call
                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=prompt
                    )
                    
                    # Parse & Sanitize
                    data = json.loads(clean_json(response.text))
                
                # Modify Title
                if sped_toggle or ml_toggle:
                    data['title'] += " -(Modified)"
                
                st.session_state.generated_content = data
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
        if st.button("Draft Assignment 🚀", type="primary", use_container_width=True):
            if not course_id:
                st.error("Please enter a Course ID in Advanced Settings.")
            else:
                base_url = canvas_url.rstrip('/')
                headers = {"Authorization": f"Bearer {st.session_state.canvas_token}", "Content-Type": "application/json"}
                
                try:
                    with st.spinner("Publishing to Canvas..."):
                        # 1. Sanitize Data
                        final_attempts = -1 if attempts_choice == 'Unlimited' else int(attempts_choice)
                        final_points = float(points_possible)
                        
                        # 2. Date Handling
                        final_unlock = None
                        final_due = None
                        final_lock = None
                        
                        if date_range:
                            if isinstance(date_range, tuple):
                                if len(date_range) == 2:
                                    start_d, end_d = date_range
                                    # Combine dates with precision times
                                    final_unlock = datetime.datetime.combine(start_d, start_time).isoformat()
                                    final_due = datetime.datetime.combine(end_d, due_time).isoformat()
                                    final_lock = final_due
                                elif len(date_range) == 1:
                                    start_d = date_range[0]
                                    final_unlock = datetime.datetime.combine(start_d, start_time).isoformat()
                            else:
                                # Fallback for single date object
                                final_unlock = datetime.datetime.combine(date_range, start_time).isoformat()

                        common_payload = {
                            "description": data.get('description'),
                            "published": True
                        }
                        if final_due: common_payload["due_at"] = final_due
                        if final_unlock: common_payload["unlock_at"] = final_unlock
                        if final_lock: common_payload["lock_at"] = final_lock

                        # 3. POST
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
                            res = requests.post(endpoint, headers=headers, json=payload)
                            res.raise_for_status()
                            st.success(f"Success! Assignment created.")
                            st.markdown(f"### [View in Canvas]({res.json().get('html_url')})")
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
                                    "hide_results": None,
                                    **common_payload
                                }
                            }
                            res = requests.post(endpoint, headers=headers, json=payload)
                            res.raise_for_status()
                            quiz_data = res.json()
                            
                            # Questions
                            q_endpoint = f"{base_url}/api/v1/courses/{course_id}/quizzes/{quiz_data.get('id')}/questions"
                            prog = st.progress(0, text="Publishing questions...")
                            questions = data.get('questions', [])
                            for i, q in enumerate(questions):
                                q_type = q.get('question_type', 'multiple_choice_question')
                                
                                # Map user-friendly types if AI returns them (fallback)
                                type_map = {
                                    'Multiple Choice': 'multiple_choice_question',
                                    'True/False': 'true_false_question',
                                    'Short Answer': 'short_answer_question',
                                    'Multiple Select': 'multiple_answers_question',
                                    'Matching': 'matching_question',
                                    'Essay': 'essay_question'
                                }
                                if q_type in type_map: q_type = type_map[q_type]

                                answers_payload = []
                                if q_type == 'matching_question':
                                    for a in q.get('answers', []):
                                        answers_payload.append({
                                            "answer_match_left": a.get('answer_match_left'),
                                            "answer_match_right": a.get('answer_match_right')
                                        })
                                elif q_type == 'essay_question':
                                    answers_payload = []
                                else:
                                    for a in q.get('answers', []):
                                        answers_payload.append({
                                            "answer_text": a.get('text'),
                                            "answer_weight": a.get('weight')
                                        })

                                q_payload = {
                                    "question": {
                                        "question_name": q.get('question_name'),
                                        "question_text": q.get('question_text'),
                                        "question_type": q_type,
                                        "points_possible": points_possible / len(questions) if len(questions) > 0 else 1,
                                        "correct_comments_html": q.get('correct_feedback', ''),
                                        "incorrect_comments_html": q.get('incorrect_feedback', ''),
                                        "answers": answers_payload
                                    }
                                }
                                requests.post(q_endpoint, headers=headers, json=q_payload)
                                prog.progress((i+1)/len(questions), text=f"Posting Question {i+1} of {len(questions)}")
                            
                            prog.empty()
                            st.success(f"Success! Quiz created.")
                            st.markdown(f"### [View in Canvas]({quiz_data.get('html_url')})")
                            st.balloons()

                except Exception as e:
                    st.error(f"Publishing failed: {str(e)}")
                    st.write("DEBUG Payload:", payload)
