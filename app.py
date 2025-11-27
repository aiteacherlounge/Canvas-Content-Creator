import streamlit as st
import requests
import os
import zipfile
import io
import xml.etree.ElementTree as ET
from google import genai
from google.genai import types
from pydantic import BaseModel
import datetime
import datetime
import json
import re
import pypdf
import docx
from fpdf import FPDF
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE

# Safety Default
target_standard = locals().get('target_standard') or globals().get('target_standard') or "General Standard"

# --- Configuration ---
st.set_page_config(page_title="Universal Canvas Builder", page_icon="✨", layout="wide")

# Initialize Session State
if 'generated_prompt' not in st.session_state:
    st.session_state['generated_prompt'] = ""
if 'lesson_plan_pdf' not in st.session_state:
    st.session_state['lesson_plan_pdf'] = None
if 'slide_deck_pptx' not in st.session_state:
    st.session_state['slide_deck_pptx'] = None
if 'is_generated' not in st.session_state:
    st.session_state['is_generated'] = False
if 'selected_tool_name' not in st.session_state:
    st.session_state['selected_tool_name'] = "None"

# Custom CSS for "Creative Teaching Assistant" Vibe
st.markdown("""
<style>
    /* 1. The Main Background */
    .stApp {
        background-color: #1E243A;
    }
/* 2. The Nuclear Option: Force ALL text white */
.stApp * {
    color: #E2E8F0 !important;
}
/* 3. Restore Input Box Backgrounds (otherwise they turn white-on-white) */
input, textarea, select, div[data-baseweb="select"] > div {
    background-color: #2A3439 !important;
    border: 1px solid #4B5563 !important;
}
/* 4. Fix Buttons (Keep them readable) */ button { background-color: #0D9488 !important; color: white !important; border: none !important; }

/* 5. Fix Code Blocks (Keep syntax highlighting) */
code {
    color: #E06C75 !important;
    background-color: #282C34 !important;
}

/* 6. Force Text Area to be High Contrast */
.stTextArea textarea {
    background-color: #2A3439 !important;
    color: #FFFFFF !important; /* Pure White Text */
    font-family: monospace !important;
    border: 1px solid #4B5563 !important;
}
/* 7. Force Labels to be White */
label {
    color: #E2E8F0 !important;
}
</style>
""", unsafe_allow_html=True)

# --- Constants ---

STEM_TOOLS = {
    "PhET: Balancing Chemical Equations": "https://phet.colorado.edu/sims/html/balancing-chemical-equations/latest/balancing-chemical-equations_en.html",
    "PhET: Circuit Construction Kit": "https://phet.colorado.edu/sims/html/circuit-construction-kit-dc/latest/circuit-construction-kit-dc_en.html",
    "PhET: Energy Skate Park": "https://phet.colorado.edu/sims/html/energy-skate-park/latest/energy-skate-park_en.html",
    "PhET: Natural Selection": "https://phet.colorado.edu/sims/html/natural-selection/latest/natural-selection_en.html",
    "PhET: Projectile Motion": "https://phet.colorado.edu/sims/html/projectile-motion/latest/projectile-motion_en.html",
    "PhET: Forces and Motion": "https://phet.colorado.edu/sims/html/forces-and-motion-basics/latest/forces-and-motion-basics_en.html",
    "Desmos: Graphing Calculator": "https://www.desmos.com/calculator",
    "Desmos: Scientific Calculator": "https://www.desmos.com/scientific",
    "GeoGebra: Geometry": "https://www.geogebra.org/geometry",
    "YouTube: Crash Course": "https://www.youtube.com/user/crashcourse",
    "YouTube: Khan Academy": "https://www.youtube.com/user/khanacademy",
    "YouTube: National Geographic": "https://www.youtube.com/user/NationalGeographic",
    "Wikipedia": "https://www.wikipedia.org/",
    "Google Slides": "https://docs.google.com/presentation/u/0/",
    "Canva": "https://www.canva.com/",
    "Desmos: Supply & Demand Shifters": "https://www.desmos.com/calculator/6mmm8psho7",
    "EconGraphs: Competitive Market": "https://www.econgraphs.org/graphs/micro/equilibrium/supply_and_demand_old",
    "Marginal Revolution: Elasticity Practice": "https://practice.mru.org/interactive-practice-supply-and-demand/",
    "Omni Margin Calculator": "https://www.omnicalculator.com/finance/margin",
    "AutoDraw": "https://www.autodraw.com/",
    "Sketchpad": "https://sketch.io/sketchpad/",
    "Color Wheel": "https://color.adobe.com/create/color-wheel",
    "Google Arts & Culture": "https://artsandculture.google.com/",
    "Python Online Compiler": "https://trinket.io/embed/python3",
    "Scratch": "https://scratch.mit.edu/projects/editor/embed"
}

# --- Helper Functions (QTI) ---

class Question(BaseModel):
    question_text: str
    options: list[str]
    correct_answer_index: int

class Quiz(BaseModel):
    questions: list[Question]

def create_imsmanifest():
    """Creates the imsmanifest.xml content."""
    manifest_template = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="man00001" xmlns="http://www.imsglobal.org/xsd/imscp_v1p1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 http://www.imsglobal.org/xsd/imscp_v1p1.xsd">
  <metadata>
    <schema>IMS Content</schema>
    <schemaversion>1.1.3</schemaversion>
  </metadata>
  <organizations/>
  <resources>
    <resource identifier="res00001" type="imsqti_xmlv1p2">
      <file href="quiz.xml"/>
    </resource>
  </resources>
</manifest>"""
    return manifest_template.encode('utf-8')

def create_quiz_xml(questions, title="Generated Quiz"):
    """Creates the quiz.xml content (QTI v1.2)."""
    root = ET.Element("questestinterop", {
        "xmlns": "http://www.imsglobal.org/xsd/ims_qtiasiv1p2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.imsglobal.org/xsd/ims_qtiasiv1p2 http://www.imsglobal.org/xsd/ims_qtiasiv1p2.xsd"
    })

    assessment = ET.SubElement(root, "assessment", {
        "ident": "quiz001",
        "title": title
    })

    section = ET.SubElement(assessment, "section", {
        "ident": "sec001",
        "title": "Main Section"
    })

    for i, q in enumerate(questions):
        item = ET.SubElement(section, "item", {
            "ident": f"q{i+1}",
            "title": f"Question {i+1}"
        })

        # Question Text
        presentation = ET.SubElement(item, "presentation")
        material = ET.SubElement(presentation, "material")
        mattext = ET.SubElement(material, "mattext", {"texttype": "text/html"})
        # Use placeholder for CDATA
        mattext.text = f"__CDATA_START__{q.question_text}__CDATA_END__"

        # Response Lid (Multiple Choice)
        response_lid = ET.SubElement(presentation, "response_lid", {
            "ident": f"response_{i+1}",
            "rcardinality": "Single"
        })
        render_choice = ET.SubElement(response_lid, "render_choice")

        for j, option in enumerate(q.options):
            response_label = ET.SubElement(render_choice, "response_label", {"ident": f"opt_{i+1}_{j}"})
            material_opt = ET.SubElement(response_label, "material")
            mattext_opt = ET.SubElement(material_opt, "mattext", {"texttype": "text/html"})
            mattext_opt.text = f"__CDATA_START__{option}__CDATA_END__"

        # Processing (Correct Answer)
        resprocessing = ET.SubElement(item, "resprocessing")
        outcomes = ET.SubElement(resprocessing, "outcomes")
        decvar = ET.SubElement(outcomes, "decvar", {
            "defaultval": "0",
            "varname": "SCORE",
            "vartype": "Integer"
        })

        respcondition = ET.SubElement(resprocessing, "respcondition", {"continue": "No"})
        conditionvar = ET.SubElement(respcondition, "conditionvar")
        correct_ident = f"opt_{i+1}_{q.correct_answer_index}"
        varequal = ET.SubElement(conditionvar, "varequal", {"respident": f"response_{i+1}"})
        varequal.text = correct_ident

        setvar = ET.SubElement(respcondition, "setvar", {
            "action": "Set",
            "varname": "SCORE"
        })
        setvar.text = "1"

    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def generate_qti_zip(quiz_data, title="Generated Quiz"):
    """Generates a QTI 1.2 Zip package."""
    try:
        # 1. Create Manifest
        manifest_data = create_imsmanifest()
        
        # 2. Create Quiz XML
        questions = [Question(**q) for q in quiz_data['questions']]
        quiz_xml_raw = create_quiz_xml(questions, title=title)
        
        # 3. Post-Process for CDATA
        # Decode bytes to string for replacement
        xml_str = quiz_xml_raw.decode('utf-8')
        # Replace placeholders with actual CDATA tags
        # Note: We also need to unescape the content inside, as ElementTree might have escaped < > &
        # But since we used placeholders, the content inside is just text. 
        # The key is that we want the FINAL output to have <![CDATA[ ... ]]>
        
        xml_str = xml_str.replace("__CDATA_START__", "<![CDATA[").replace("__CDATA_END__", "]]>")
        
        # Re-encode
        final_quiz_xml = xml_str.encode('utf-8')
        
        # 4. Zip It
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("imsmanifest.xml", manifest_data)
            zf.writestr("quiz.xml", final_quiz_xml)
            
        return zip_buffer.getvalue()
    except Exception as e:
        st.error(f"Error creating QTI Zip: {e}")
        return None

def generate_quiz_json(prompt):
    """Generates the Quiz JSON data from Gemini."""
    client = get_gemini_client()
    if not client: return None
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type='application/json')
        )
        return clean_json(response.text)
    except Exception as e:
        st.error(f"Error generating quiz JSON: {e}")
        return None

def generate_quiz_data_batched(topic, subtopic, target_count, due_date, due_time, points_per_question, question_types, grade_level, is_sped, is_ml, language, source_text=""):
    """Generates quiz questions in batches to ensure target count is met."""
    all_questions = []
    batch_size = 10
    # Over-provision: (target // 10) + 2 batches
    num_batches = (target_count // 10) + 2
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(num_batches):
        status_text.text(f"Generating Batch {i+1}/{num_batches}...")
        
        # Construct prompt for this batch
        # Note: We use batch_size here, not target_count
        prompt = construct_quiz_prompt(topic, subtopic, batch_size, due_date, due_time, points_per_question, question_types, grade_level, is_sped, is_ml, language, source_text)
        
        # Generate JSON
        batch_data = generate_quiz_json(prompt)
        
        if batch_data and 'questions' in batch_data:
            all_questions.extend(batch_data['questions'])
        
        # Update progress
        progress_bar.progress((i + 1) / num_batches)
        
        # Early break if we have enough
        if len(all_questions) >= target_count:
            break
            
    status_text.empty()
    progress_bar.empty()
    
    # Trim to exact count
    all_questions = all_questions[:target_count]
    
    return {"questions": all_questions}

# --- AI Generation Functions ---

def get_gemini_client():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error("GEMINI_API_KEY not found in secrets.toml")
        return None

def check_api_connection():
    """Checks connection to Gemini API."""
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        response = requests.get(url)
        
        if response.status_code != 200:
            st.error(f"Connection Error: {response.status_code}")
        else:
            st.toast("Connected successfully!", icon="✅")
    except Exception as e:
        st.error(f"Connection Failed: {e}")
        st.error("GEMINI_API_KEY not found in secrets.toml")
        return None

def clean_json(text):
    """Cleans JSON text by removing markdown fences and fixing unescaped backslashes."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    
    # Fix unescaped backslashes (common in LaTeX)
    # Find backslashes that are NOT followed by valid escape chars (n, r, t, b, f, u, ", \, /)
    # and double them up.
    text = re.sub(r'\\(?![nrtbfu"/\\\\])', r'\\\\', text)
    
    return json.loads(text)

def recommend_tool(topic, standard):
    client = get_gemini_client()
    if not client: return "None"

    tools_keys = list(STEM_TOOLS.keys())
    prompt = f"""
    Given the topic "{topic}" and standard "{standard}", which ONE of these tools is the absolute best match?
    Options: {tools_keys}
    
    Return ONLY the exact dictionary key. If nothing fits perfectly, return "None".
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        recommended = response.text.strip()
        if recommended in tools_keys:
            return recommended
        return "None"
    except Exception as e:
        st.error(f"Error recommending tool: {e}")
        return "None"

def generate_unit_outline(topic, num_assignments, num_quizzes):
    # Safety Default
    target_standard = locals().get('target_standard') or globals().get('target_standard') or "General Standard"
    
    client = get_gemini_client()
    if not client: return []

    prompt = f"""
    Create a unit outline for the topic: {topic}.
    Generate exactly {num_assignments} assignment titles and {num_quizzes} quiz titles.
    Return a JSON object with a list 'items', where each item has 'type' ('Assignment' or 'Quiz') and 'title'.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            )
        )
        return clean_json(response.text)['items']
    except Exception as e:
        st.error(f"Error generating outline: {e}")
        return []

def generate_lesson_plan_pdf(topic, standard, grade, strategy="None / Standard"):
    """Generates a High-Design 5E Lesson Plan PDF (Strict One-Page). Returns (pdf_bytes, raw_text)."""
    # Safety Default
    target_standard = locals().get('target_standard') or globals().get('target_standard') or "General Standard"

    client = get_gemini_client()
    if not client: return None, ""

    # 1. AI Generation (Structured JSON)
    prompt = f"""
    Create a 5E Lesson Plan for Grade {grade} on "{topic}" (Standard: {standard}).
    Return a JSON object with this EXACT structure:
    {{
        "metadata": {{
            "duration": "e.g., 60 minutes",
            "materials": ["item 1", "item 2"],
            "vocabulary": ["term 1", "term 2"],
            "differentiation": {{
                "sped": ["mod 1", "mod 2"],
                "ml": ["support 1", "support 2"]
            }}
        }},
        "sections": [
            {{"phase": "Engage", "time": "10 mins", "activity": "Brief description..."}},
            {{"phase": "Explore", "time": "15 mins", "activity": "Brief description..."}},
            {{"phase": "Explain", "time": "10 mins", "activity": "Brief description..."}},
            {{"phase": "Elaborate", "time": "15 mins", "activity": "Independent Practice referencing the {topic} Assignment..."}},
            {{"phase": "Evaluate", "time": "10 mins", "activity": "Assessment referencing the {topic} Quiz..."}}
        ]
    }}
    Keep descriptions concise (bullet points preferred).
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type='application/json')
        )
        data = clean_json(response.text)
        
        # 2. PDF Creation (High-Design Dashboard - Strict One Page)
        pdf = FPDF(orientation='P', unit='mm', format='Letter')
        pdf.add_page()
        pdf.set_auto_page_break(auto=False) # Disable auto page break
        
        # Colors
        header_bg = (30, 36, 58) # Dark Blue
        sidebar_bg = (240, 244, 248) # Light Grey/Blue
        text_color = (0, 0, 0)
        header_text_color = (255, 255, 255)
        
        # --- Header (Full Width) ---
        pdf.set_fill_color(*header_bg)
        pdf.rect(0, 0, 216, 38, 'F') # 1.5 inch approx 38mm
        
        pdf.set_text_color(*header_text_color)
        pdf.set_font("Helvetica", 'B', 16)
        pdf.set_xy(10, 10)
        pdf.cell(0, 8, f"Lesson Plan: {topic}", ln=1)
        
        # Strategy (Top Right)
        pdf.set_xy(120, 10)
        pdf.set_font("Helvetica", 'I', 10)
        pdf.cell(86, 8, f"Strategy: {strategy}", ln=1, align='R')
        
        pdf.set_font("Helvetica", '', 10)
        pdf.set_text_color(200, 200, 200) # Light Grey
        pdf.set_xy(10, 20)
        pdf.cell(0, 5, f"Grade: {grade}", ln=1)
        
        # Truncate Standard
        std_desc = standard
        if len(std_desc) > 120:
            std_desc = std_desc[:117] + "..."
        pdf.multi_cell(0, 5, f"Standard: {std_desc}")
        
        # --- Sidebar (Left 2.5 inches -> 63.5mm) ---
        sidebar_width = 64
        pdf.set_fill_color(*sidebar_bg)
        pdf.rect(0, 38, sidebar_width, 241, 'F')
        
        # Sidebar Content
        pdf.set_text_color(*text_color)
        y_pos = 45
        x_pos = 5
        
        def sidebar_section(title, items):
            nonlocal y_pos
            if y_pos > 250: return # Stop if too low
            
            # Step A: Set XY
            pdf.set_xy(x_pos, y_pos)
            
            # Step B: Print Title
            pdf.set_font("Helvetica", 'B', 9)
            pdf.cell(50, 5, title.upper(), ln=1)
            
            # Step C: Print Content
            pdf.set_font("Helvetica", '', 8)
            content_str = ""
            if isinstance(items, list):
                for item in items:
                    content_str += f"- {item}\n"
            elif isinstance(items, str):
                content_str = items
            
            safe_content = content_str.encode('latin-1', 'replace').decode('latin-1')
            
            # Save current Y before printing content? No, we print then check Y.
            # Actually, we need to set XY for content? No, ln=1 moved us down.
            # But let's be precise as requested: "Step C: Save the current Y. Print the Content"
            # The multi_cell handles the printing.
            pdf.set_xy(x_pos, pdf.get_y()) 
            pdf.multi_cell(55, 4, safe_content)
            
            # Step D: Update current_y
            y_pos = pdf.get_y() + 10

        sidebar_section("Duration", data['metadata'].get('duration', '60 mins'))
        sidebar_section("Materials", data['metadata'].get('materials', []))
        sidebar_section("Vocabulary", data['metadata'].get('vocabulary', []))
        
        # Differentiation
        if y_pos < 250:
            pdf.set_xy(x_pos, y_pos)
            pdf.set_font("Helvetica", 'B', 9)
            pdf.cell(50, 5, "DIFFERENTIATION", ln=1)
            # Update Y for content
            y_pos = pdf.get_y()
            
            diff = data['metadata'].get('differentiation', {})
            if diff.get('sped'):
                pdf.set_xy(x_pos, y_pos)
                pdf.set_font("Helvetica", 'BI', 8)
                pdf.cell(50, 4, "SPED:", ln=1)
                
                pdf.set_font("Helvetica", '', 8)
                for item in diff['sped'][:3]: # Limit to 3 items
                    pdf.set_xy(x_pos, pdf.get_y())
                    safe_item = f"- {item}".encode('latin-1', 'replace').decode('latin-1')
                    pdf.multi_cell(55, 4, safe_item)
                
                y_pos = pdf.get_y() + 2
                
            if diff.get('ml') and y_pos < 250:
                pdf.set_xy(x_pos, y_pos)
                pdf.set_font("Helvetica", 'BI', 8)
                pdf.cell(50, 4, "ML Support:", ln=1)
                
                pdf.set_font("Helvetica", '', 8)
                for item in diff['ml'][:3]: # Limit to 3 items
                    pdf.set_xy(x_pos, pdf.get_y())
                    safe_item = f"- {item}".encode('latin-1', 'replace').decode('latin-1')
                    pdf.multi_cell(55, 4, safe_item)
                
                y_pos = pdf.get_y() + 10
        
        # --- Main Content (Right Side) ---
        # Draw Border Line
        pdf.set_draw_color(200, 200, 200)
        pdf.line(sidebar_width, 38, sidebar_width, 279)
        
        y_pos = 45
        x_pos = sidebar_width + 10 # 74mm
        content_width = 130
        
        for section in data.get('sections', []):
            if y_pos > 260: break # Stop if page full
            
            pdf.set_xy(x_pos, y_pos)
            pdf.set_font("Helvetica", 'B', 11)
            pdf.set_text_color(13, 148, 136) # Teal accent
            phase = section.get('phase', 'Phase')
            time = section.get('time', '')
            pdf.cell(content_width, 6, f"{phase} ({time})", ln=1)
            y_pos += 6
            
            pdf.set_xy(x_pos, y_pos)
            pdf.set_font("Helvetica", '', 10)
            pdf.set_text_color(0, 0, 0)
            activity = section.get('activity', '')
            
            # Truncate if too long (approx 400 chars)
            if len(activity) > 400:
                activity = activity[:397] + "..."
                
            safe_activity = activity.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(content_width, 5, safe_activity)
            y_pos = pdf.get_y() + 6
            
            y_pos = pdf.get_y() + 6
            
        return pdf.output(dest='S').encode('latin-1'), response.text
        
    except Exception as e:
        st.error(f"Error generating lesson plan: {e}")
        return None, ""

def generate_slide_deck(topic, grade, strategy="None / Standard", source_text=""):
    """Generates a 7-slide PowerPoint presentation using Gemini and python-pptx."""
    # Safety Default
    target_standard = locals().get('target_standard') or globals().get('target_standard') or "General Standard"

    client = get_gemini_client()
    if not client: return None

    # Strategy Context
    strategy_instruction = ""
    if strategy and strategy != "None / Standard":
        strategy_instruction = f"""
        CRITICAL: Include a specific slide titled "{strategy} Activity Instructions".
        On this slide, provide student-facing directions that align exactly with the {strategy} method.
        (e.g., if "Station Rotation", list what happens at each station; if "Fishbowl", list the rules for the inner/outer circle).
        In the Speaker Notes for this slide, provide teacher-facing tips on how to facilitate the activity (e.g., "Set a timer for 10 minutes").
        """
    else:
        strategy_instruction = """
        Include a slide titled "Practice Activity" with clear student instructions for a standard class activity.
        """

    # Prompt Logic: Chain vs Scratch
    if source_text:
        prompt = f"""
        ### 1. ROLE
        Act as an Educational Content Creator.
        
        ### 2. TASK
        Convert the following Lesson Plan into a 7-slide PowerPoint presentation for Grade {grade}.
        
        ### 3. SOURCE MATERIAL
        \"\"\"{source_text}\"\"\"
        
        ### 4. REQUIREMENTS
        - Create 7 slides based on the lesson plan content.
        - {strategy_instruction}
        - Constraint: Use MAXIMUM 5 bullet points per slide.
        - Constraint: Use MAXIMUM 8 words per bullet point. Be extremely concise.
        - Constraint: Move ALL explanations and details into the speaker_notes. The slide text must be keywords only.
        
        ### 5. OUTPUT FORMAT
        Return a JSON object with:
        - 'slides': list of objects, where each slide has:
            - 'title': string (Clear and Action-Oriented)
            - 'bullet_points': list of strings (Max 5 points, Max 8 words each. Keywords only.)
            - 'speaker_notes': string (Detailed, scripted notes. e.g., "Ask the class: Have you ever seen...?")
            - 'image_ai_prompt': string (detailed Nano Banana prompt)
        """
    else:
        prompt = f"""
        Create a 7-slide presentation outline for Grade {grade} on "{topic}".
        {strategy_instruction}
        
        Constraint: Use MAXIMUM 5 bullet points per slide.
        Constraint: Use MAXIMUM 8 words per bullet point. Be extremely concise.
        Constraint: Move ALL explanations and details into the speaker_notes. The slide text must be keywords only.
        
        Return a JSON object with:
        - 'slides': list of objects, where each slide has:
            - 'title': string (Clear and Action-Oriented)
            - 'bullet_points': list of strings (Max 5 points, Max 8 words each. Keywords only.)
            - 'speaker_notes': string (Detailed, scripted notes. e.g., "Ask the class: Have you ever seen...?")
            - 'image_ai_prompt': string (detailed Nano Banana prompt)
        """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type='application/json')
        )
        data = clean_json(response.text)
        
        # UNIVERSAL HANDLER: Support List or Dict
        if isinstance(data, list):
            slides_data = data
        elif isinstance(data, dict):
            # Try every possible key the AI might use
            slides_data = data.get('slides') or data.get('presentation') or data.get('content') or list(data.values())[0]
        else:
            slides_data = []
            
        # Safety Check: Ensure it's actually a list
        if not isinstance(slides_data, list):
            slides_data = []
        
        prs = Presentation()
        
        # Helper to add a slide
        def add_slide_content(prs, title_text, bullets_list, notes_text, ai_prompt, is_first=False):
            slide_layout = prs.slide_layouts[1] # Title and Content
            slide = prs.slides.add_slide(slide_layout)
            
            # Title
            if slide.shapes.title:
                slide.shapes.title.text = title_text
            
            # Body Content (Standard Placeholder)
            if len(slide.placeholders) > 1:
                content = slide.placeholders[1]
                content.width = Inches(4.5)
                content.height = Inches(5.5)
                content.top = Inches(1.5)
                
                tf = content.text_frame
                tf.word_wrap = True
                tf.clear() # Clear existing
                
                for b in bullets_list:
                    p = tf.add_paragraph()
                    p.text = b
                    p.level = 0

            # Speaker Notes
            if slide.has_notes_slide:
                notes_slide = slide.notes_slide
                text_frame = notes_slide.notes_text_frame
                text_frame.text = notes_text

            # Slide 1: Pro Tip
            if is_first:
                left = Inches(0.5)
                top = Inches(0.2) # Very top
                width = Inches(9.0)
                height = Inches(0.5)
                
                tip_box = slide.shapes.add_textbox(left, top, width, height)
                tf = tip_box.text_frame
                p = tf.add_paragraph()
                p.text = "💡 PRO TIP: To style this presentation instantly, click the Design tab and select Designer (or a Theme) to match your classroom style."
                p.font.size = Pt(11)
                p.font.color.rgb = RGBColor(100, 100, 100) # Grey

            # Footer: Nano Banana Prompt
            left = Inches(0.5)
            top = Inches(7.0)
            width = Inches(9.0)
            height = Inches(0.5)
            
            disc_box = slide.shapes.add_textbox(left, top, width, height)
            tf = disc_box.text_frame
            p = tf.add_paragraph()
            p.text = f"🍌 Nano Banana Image Prompt: {ai_prompt}"
            p.font.italic = True
            p.font.size = Pt(9)
            p.font.color.rgb = RGBColor(150, 150, 150) # Light Grey

        for i, slide_info in enumerate(slides_data):
            title = slide_info.get('title', 'Untitled Slide')
            bullets = slide_info.get('bullet_points', [])
            notes = slide_info.get('speaker_notes', '')
            prompt = slide_info.get('image_ai_prompt', f"Image of {topic}")
            
            # Split if too many bullets
            if len(bullets) > 6:
                # Part 1
                add_slide_content(prs, f"{title} (Part 1)", bullets[:6], notes, prompt, is_first=(i==0))
                # Part 2
                add_slide_content(prs, f"{title} (Part 2)", bullets[6:], notes, prompt, is_first=False)
            else:
                add_slide_content(prs, title, bullets, notes, prompt, is_first=(i==0))
            
        # Save to buffer
        pptx_buffer = io.BytesIO()
        prs.save(pptx_buffer)
        return pptx_buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error generating slides: {e}")
        return None

def extract_text_from_file(uploaded_file):
    """Extracts text from PDF, DOCX, or TXT files."""
    try:
        text = ""
        if uploaded_file.type == "application/pdf":
            reader = pypdf.PdfReader(uploaded_file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif uploaded_file.type == "text/plain":
            text = uploaded_file.getvalue().decode("utf-8")
        
        # Truncate if too long
        if len(text) > 10000:
            text = text[:10000] + "\n\n[Text truncated for prompt limit...]"
            
        return text
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return ""

def construct_quiz_prompt(topic, subtopic, count, due_date, due_time, points_per_question, question_types, grade_level, is_sped, is_ml, language, source_text=""):
    
    # Build Context Strings
    sped_context = "Include specific accommodations for Special Education (SPED) students." if is_sped else ""
    ml_context = f"Include language supports for Multilingual Learners (primary language: {language})." if is_ml else ""
    
    # Build Task Constraints
    task_constraints = ""
    if is_sped:
        task_constraints += "Modify reading level to be accessible. Chunk text into smaller sections.\n"
    if is_ml:
        task_constraints += f"Provide key vocabulary definitions translated into {language}.\n"

    # Source Material Section
    source_material_section = ""
    if source_text:
        source_material_section = f"""
### 5. SOURCE MATERIAL
Use the following text as the primary source for content generation:
\"\"\" {source_text} \"\"\"
"""

    prompt = f"""
### 1. ROLE
Act as an expert Curriculum Designer for **Grade {grade_level}**.

### 2. CONTEXT
I am teaching a unit on "{topic}" (Subtopic: {subtopic}).
Student Profile: Mixed ability. {sped_context} {ml_context}
Target Standard: {standard}.

### 3. TASK
Create a Quiz that aligns perfectly with the standard above.
{task_constraints}
Generate {count} multiple choice questions.
Each question should have 4 options.
Indicate the correct answer index (0-3).

XML CONFIGURATION: Set the point value for EVERY question to {points_per_question}.
QUESTION TYPES: Generate a mix of ONLY the following types: {question_types}.
METADATA: Include the Due Date ({due_date} {due_time}) in the Quiz Description text.

### 4. FORMAT
Return the output as a JSON object matching the following schema:
{{
  "questions": [
    {{
      "question_text": "string",
      "options": ["string", "string", "string", "string"],
      "correct_answer_index": int
    }}
  ]
}}
{source_material_section}
    """
    return prompt

def construct_assignment_prompt(topic, subtopic, tool, due_date, due_time, points, grade_level, is_sped, is_ml, language, subject, strategy, source_text=""):
    tools_str = tool if tool and tool != "None" else "None"
    
    # Build Context Strings
    sped_context = "Include specific accommodations for Special Education (SPED) students." if is_sped else ""
    ml_context = f"Include language supports for Multilingual Learners (primary language: {language})." if is_ml else ""
    
    # Build Task Constraints
    task_constraints = ""
    if is_sped:
        task_constraints += "Modify reading level to be accessible. Chunk text into smaller sections.\n"
    if is_ml:
        task_constraints += f"Provide key vocabulary definitions translated into {language}.\n"
        
    # Subject Specific Logic
    subject_context = ""
    iframe_height = "450"
    
    if "Business" in subject or "Economics" in subject:
        subject_context = "Focus on market dynamics, finance, and management scenarios."
        if "Desmos" in tool or "EconGraphs" in tool:
            subject_context += ' Create scenarios that require students to shift the curves (e.g., "A drought destroys the corn crop"). Ask them to predict the new Equilibrium Price and Quantity using the embedded graph.\n'
            iframe_height = "700"
    elif "Humanities" in subject or "Arts" in subject:
        subject_context = "Focus on history, literature, visual arts, and cultural analysis."
    elif "Technology" in subject or "CS" in subject:
        subject_context = "Focus on coding, digital literacy, and systems thinking."
    
    # Pedagogy & Strategy Logic
    pedagogy_section = ""
    if strategy and strategy != "None / Standard":
        strategy_requirements = {
            "Flipped Classroom": "Create a pre-class video/reading assignment and an active in-class application task.",
            "Project-Based Learning (PBL)": "Frame the assignment around a Driving Question and a real-world final artifact.",
            "Socratic Seminar / Fishbowl": "Design discussion questions for the inner circle and observation tasks for the outer circle.",
            "Blended Learning (Station Rotation)": "Design this as a Station Rotation activity (Online Station).",
            "Inquiry-Based Learning": "Start with a complex question or problem and guide students to research/investigate answers.",
            "Gamification": "Include game elements like points, badges, or a narrative quest structure.",
            "Direct Instruction": "Focus on clear, explicit teaching of concepts with guided practice."
        }
        req = strategy_requirements.get(strategy, "Ensure the activity follows best practices for this strategy.")
        
        pedagogy_section = f"""
### 5. PEDAGOGY & STRATEGY
**Method:** {strategy}
**Requirement:** {req}
"""

    # Source Material Section
    source_material_section = ""
    if source_text:
        source_material_section = f"""
### 6. SOURCE MATERIAL
Use the following text as the primary source for content generation:
\"\"\" {source_text} \"\"\"
"""
    
    prompt = f"""
### 1. ROLE
Act as an expert Curriculum Designer for **Grade {grade_level}**.

### 2. CONTEXT
I am teaching a unit on "{topic}" (Subtopic: {subtopic}).
Subject: {subject}
Student Profile: Mixed ability. {sped_context} {ml_context}
Target Standard: {standard}.

### 3. TASK
Create an Assignment that aligns perfectly with the standard above.
{task_constraints}
{subject_context}
Tools to embed: {tools_str}
Include:
- Learning Objectives
- Instructions
- Grading Criteria

Instruction: When embedding a tool (YouTube, Desmos, PhET, etc.), you MUST write a specific 1-sentence Instructional Caption explaining how the student should use it (e.g., "Watch this video to understand X").

In the HTML output, create a highly visible "Metadata Box" at the top using a styled div that displays: Due Date: {due_date} at {due_time} | Points: {points}.

### 4. FORMAT
Return the output as **raw HTML code** ready for Canvas LMS.
- Structure: Title, Introduction, Content, Rubric/Answer Key.
- Styling: Use inline CSS for a clean, modern look.
- Embeds: Include this tool: <iframe src='{{tool_url}}'...></iframe>

HTML Formatting:
When generating the HTML file, wrap the iframe in a styled div:
<div style="background: #f4f4f9; padding: 15px; border-left: 5px solid #0D9488; margin: 20px 0;">
    <h4 style="margin-top:0;'>Interactive Tool</h4>
    <p>{{tool_caption}}</p>
    <iframe src="{{tool_url}}" width="100%" height="{iframe_height}" style="border:none;"></iframe>
</div>

Do NOT include <html>, <head>, or <body> tags. Just the content div.
Use inline CSS for styling to ensure it looks good in Canvas.
{pedagogy_section}
{source_material_section}
    """
    return prompt

def construct_unit_prompt(topic, num_assignments, num_quizzes, grade_level, is_sped, is_ml, language, subject, strategy, source_text=""):
    # Build Context Strings
    sped_context = "Include specific accommodations for Special Education (SPED) students." if is_sped else ""
    ml_context = f"Include language supports for Multilingual Learners (primary language: {language})." if is_ml else ""
    
    prompt = f"""
### 1. ROLE
Act as an expert Curriculum Designer for **Grade {grade_level}**.

### 2. CONTEXT
I am planning a comprehensive unit on "{topic}".
Subject: {subject}
Student Profile: Mixed ability. {sped_context} {ml_context}

### 3. TASK
Create a detailed Unit Plan and Outline.
Structure the unit to include {num_assignments} distinct Assignments and {num_quizzes} Quizzes.
Instructional Strategy: {strategy}

### 4. REQUIREMENTS
For each Assignment:
- Provide a creative Title.
- Briefly describe the student task.
- Suggest a specific digital tool or resource to use.

For each Quiz:
- Provide a Title.
- Describe the focus/learning targets being assessed.

### 5. OUTPUT FORMAT
Return the output as a structured Markdown document.
Use clear headings for "Unit Overview", "Assignment Sequence", and "Assessment Plan".
"""
    return prompt



# --- UI ---

st.title("✨ Universal Canvas Builder")
st.markdown("Generate Canvas Assignments, Quizzes, and Full Units with AI.")

# Sidebar
with st.sidebar:
    st.header("Global Settings")
    

    
    # Unified Content Type Selection
    content_type = st.selectbox("Content Type", ["Assignment", "Quiz", "Unit"])
    
    # File Uploader
    uploaded_file = st.file_uploader("📂 Attach Source Material (PDF, DOCX, TXT)", type=['pdf', 'docx', 'txt'])
    source_text = ""
    if uploaded_file:
        with st.spinner("Extracting text..."):
            source_text = extract_text_from_file(uploaded_file)
            st.success("File processed!")
            
    subject = st.selectbox("Subject Focus", ["Science", "Math", "English", "Business & Economics", "Humanities & Arts", "Technology & CS", "General"])
    topic = st.text_input("Topic", "Photosynthesis")
    
    # Standard Input (Needed for Auto-Detection)
    standard = st.text_area("Standard", "NGSS HS-LS1-5", height=100)
    
    # Grade Level
    grade_level = st.selectbox("Grade Level", ['K', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', 'Higher Ed / Collegiate'], index=10)
    
    # Instructional Strategy
    instructional_strategy = st.selectbox(
        "🧠 Instructional Strategy",
        ["None / Standard", "Blended Learning (Station Rotation)", "Project-Based Learning (PBL)", "Flipped Classroom", "Inquiry-Based Learning", "Socratic Seminar / Fishbowl", "Gamification", "Direct Instruction"]
    )
    
    # Media Expansion Packs
    media_packs = st.multiselect(
        "🎨 Media Expansion Packs",
        ['Nano Banana (Image Generation)', 'Veo (Video Generation)']
    )
    
    # Conditional Inputs based on Content Type
    subtopic = ""
    num_assignments = 5
    num_quizzes = 2
    
    if content_type == 'Unit':
        st.info("Unit Mode: Generates a comprehensive plan.")
        num_assignments = st.number_input("Number of Assignments", 1, 10, 5)
        num_quizzes = st.number_input("Number of Quizzes", 1, 5, 2)
    else:
        subtopic = st.text_input("Subtopic", "Light-dependent reactions")

    with st.expander("♿ Student Needs & Differentiation"):
        is_sped = st.toggle("Include SPED Accommodations")
        is_ml = st.toggle("Include Multilingual Learner Support")
        
        language = "Spanish"
        if is_ml:
            language = st.selectbox("Target Language", ["Spanish", "French", "Portuguese", "Arabic", "Chinese", "Vietnamese", "Tagalog"])
        
    with st.expander("⚙️ Logistics & Scoring"):
        due_date = st.date_input("Due Date", datetime.date.today() + datetime.timedelta(days=7))
        due_time = st.time_input("Due Time", datetime.time(23, 59))
        
        # Logic for Points/Quiz config
        show_assignment_settings = (content_type == 'Assignment')
        show_quiz_settings = (content_type == 'Quiz')
        
        points = 100
        if show_assignment_settings or content_type == 'Unit':
            points = st.number_input("Total Points (Assignments)", value=100)
            
        points_per_question = 1
        question_types = ['Multiple Choice']
        if show_quiz_settings or content_type == 'Unit':
            points_per_question = st.number_input("Points per Question", value=1)
            question_types = st.multiselect("Question Types", options=['Multiple Choice', 'True/False', 'Short Answer', 'Essay', 'Matching', 'Multiple Select'], default=['Multiple Choice'])

    st.header("Tools")
    
    # Auto-Detection Logic
    if 'selected_tool_name' not in st.session_state:
        st.session_state.selected_tool_name = "None"

    if st.button("🪄 Auto-Select Best Tool"):
        with st.spinner("Finding the best tool..."):
            recommended = recommend_tool(topic, standard)
            # We check if the recommended tool is valid in general, 
            # but we also need to handle if it's not in the CURRENT subject list.
            if recommended in STEM_TOOLS:
                st.session_state.selected_tool_name = recommended
                st.toast(f"Found match: {recommended}", icon="✅")
            else:
                st.toast("No perfect match found.", icon="⚠️")

    tool_options = ["None"] + list(STEM_TOOLS.keys())
    
    # Filter tools based on Subject
    if subject == "Business & Economics":
        tool_options = ["None", "EconGraphs: Competitive Market", "Desmos: Supply & Demand Shifters", "Marginal Revolution: Elasticity Practice", "Omni Margin Calculator"]
    elif subject == "Humanities & Arts":
        tool_options = ["None", "AutoDraw", "Sketchpad", "Color Wheel", "Google Arts & Culture"]
    elif subject == "Technology & CS":
        tool_options = ["None", "Python Online Compiler", "Scratch"]
    elif subject == "Science":
        # Filter for Science tools + General
        tool_options = ["None"] + [k for k in STEM_TOOLS.keys() if "PhET" in k or "Science" in k or "National Geographic" in k or k in ["YouTube: Crash Course", "YouTube: Khan Academy", "Wikipedia", "Google Slides", "Canva"]]
    elif subject == "Math":
        # Filter for Math tools + General
        tool_options = ["None"] + [k for k in STEM_TOOLS.keys() if "Desmos" in k or "GeoGebra" in k or k in ["YouTube: Khan Academy", "Wikipedia", "Google Slides", "Canva"]]
    
    # Validation: Ensure the currently selected tool is actually in the filtered list.
    # If not, reset to "None".
    if st.session_state.selected_tool_name not in tool_options:
        st.session_state.selected_tool_name = "None"
    
    selected_tool = st.selectbox(
        "Embed Interactive Tool",
        options=tool_options,
        key="selected_tool_name"
    )

# Main Area

if content_type == "Assignment":
    st.header("Assignment Builder")
    include_lesson_plan = st.checkbox("Include PDF Lesson Plan?")
    include_slides = st.checkbox("Include PowerPoint Slides?")
    
    if st.button("Draft My Mega-Prompt"):
        # 1. Generate Main Prompt
        st.session_state['generated_prompt'] = construct_assignment_prompt(topic, subtopic, selected_tool, due_date, due_time, points, grade_level, is_sped, is_ml, language, subject, instructional_strategy, source_text)
        
        # 2. Generate PDF (if checked)
        lp_text = ""
        if include_lesson_plan:
            with st.spinner("Generating Lesson Plan PDF..."):
                st.session_state['lesson_plan_pdf'], lp_text = generate_lesson_plan_pdf(topic, standard, grade_level, instructional_strategy)
        else:
            st.session_state['lesson_plan_pdf'] = None

        # 3. Generate Slides (if checked)
        if include_slides:
            with st.spinner("Generating PowerPoint Slides..."):
                # Chain: Pass the Lesson Plan text if available
                st.session_state['slide_deck_pptx'] = generate_slide_deck(topic, grade_level, instructional_strategy, source_text=lp_text)
        else:
            st.session_state['slide_deck_pptx'] = None
        
        st.session_state['is_generated'] = True

elif content_type == "Quiz":
    st.header("Quiz Builder")
    question_count = st.number_input("Number of Questions", 1, 50, 5)
    
    if st.button("Draft My Mega-Prompt"):
        # 1. Construct Prompt
        prompt_content = construct_quiz_prompt(topic, subtopic, question_count, due_date, due_time, points_per_question, question_types, grade_level, is_sped, is_ml, language, source_text)
        st.session_state['generated_prompt'] = prompt_content
        
        # 2. Generate JSON & Zip (Background)
        # We use the batched function now
        quiz_data = generate_quiz_data_batched(topic, subtopic, question_count, due_date, due_time, points_per_question, question_types, grade_level, is_sped, is_ml, language, source_text)
        
        if quiz_data:
            zip_bytes = generate_qti_zip(quiz_data, title=f"{topic} Quiz")
            st.session_state['quiz_zip'] = zip_bytes
        else:
            st.session_state['quiz_zip'] = None

        st.session_state['is_generated'] = True
        # Reset other artifacts
        st.session_state['lesson_plan_pdf'] = None
        st.session_state['slide_deck_pptx'] = None

elif content_type == "Unit":
    st.header("Unit Planner")
    
    if st.button("Draft My Mega-Prompt"):
        st.session_state['generated_prompt'] = construct_unit_prompt(topic, num_assignments, num_quizzes, grade_level, is_sped, is_ml, language, subject, instructional_strategy, source_text)
        st.session_state['is_generated'] = True
        # Reset other artifacts
        st.session_state['lesson_plan_pdf'] = None
        st.session_state['slide_deck_pptx'] = None

# Display Results (Persistent)
if st.session_state['is_generated']:
    st.code(st.session_state['generated_prompt'], language='markdown')
    
    # Media Prompts (Explicit Logic)
    if media_packs:
        st.markdown("---")
        
        if "Nano Banana (Image Generation)" in media_packs:
            st.subheader("🍌 Nano Banana Prompt")
            image_prompt = f"Create a 4K educational poster for {topic}. Style: Photorealistic/Diagram. Key elements: [Insert Standard Details]."
            st.code(image_prompt, language='text')
            
        if "Veo (Video Generation)" in media_packs:
            st.subheader("🎥 Veo Video Prompt")
            video_prompt = f"Cinematic 60s video clip. Subject: {topic}. Action: [Describe motion]. Style: Documentary."
            st.code(video_prompt, language='text')
    
    # Download Buttons
    if st.session_state.get('lesson_plan_pdf'):
        st.download_button(
            label="📄 Download Lesson Plan PDF",
            data=st.session_state['lesson_plan_pdf'],
            file_name=f"Lesson_Plan_{topic.replace(' ', '_')}.pdf",
            mime="application/pdf"
        )
    
    if st.session_state.get('slide_deck_pptx'):
        st.download_button(
            label="📊 Download PowerPoint Slides",
            data=st.session_state['slide_deck_pptx'],
            file_name=f"Slides_{topic.replace(' ', '_')}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        
    if st.session_state.get('quiz_zip'):
        st.download_button(
            label="📦 Download Ready-to-Import Quiz (.zip)",
            data=st.session_state['quiz_zip'],
            file_name=f"{topic.replace(' ', '_')}_Quiz.zip",
            mime="application/zip",
            type="primary"
        )
