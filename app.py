import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import json
import os
import zipfile
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import re
import time

# --- Configuration ---
st.set_page_config(page_title="AI Curriculum Factory", page_icon="🏭", layout="wide")

# Load Secrets
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    GMAIL_USER = st.secrets["GMAIL_USER"]
    GMAIL_APP_PASSWORD = st.secrets["GMAIL_APP_PASSWORD"]
except FileNotFoundError:
    st.error("Secrets not found. Please set GEMINI_API_KEY, GMAIL_USER, and GMAIL_APP_PASSWORD in .streamlit/secrets.toml")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# --- Helper Functions ---
def clean_json(text):
    """Cleans JSON string from Markdown code blocks and fixes escapes."""
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    
    # Fix invalid escape sequences (like \Delta -> \\Delta)
    text = re.sub(r'\\(?![/u"\\bfnrt])', r'\\\\', text)
    
    return text.strip()

def connect_to_sheets(service_account_file, sheet_name):
    """Connects to Google Sheets using service account."""
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json.load(service_account_file), scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).sheet1
    return sheet

def send_email(to_email, subject, body, attachment_path):
    """Sends an email with attachment via Gmail SMTP."""
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    with open(attachment_path, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename= {os.path.basename(attachment_path)}",
    )
    msg.attach(part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    text = msg.as_string()
    server.sendmail(GMAIL_USER, to_email, text)
    server.quit()

# --- The Unit Architect Engine ---
def build_unit_chain(order, client, status_container):
    """Orchestrates the 5-day unit generation chain."""
    topic = order['Topic']
    subject = order['Subject']
    grade = order['Grade']
    standard = order['Standards']
    
    model = client.models.GenerativeModel('gemini-2.0-flash')
    
    # --- Phase A: The Blueprint ---
    status_container.write("🏗️ Phase A: Drafting Blueprint...")
    blueprint_prompt = f"""
    You are a Curriculum Director for {subject}, Grade {grade}.
    Create a 5-day Unit Plan for the topic: {topic}.
    Standard: {standard}.
    
    Return a JSON object with a key "days" containing a list of 5 objects.
    Each object must have:
    - "day": Integer (1-5)
    - "title": Lesson title
    - "activity_type": One of ['Lecture', 'Assignment', 'Quiz']
    - "objective": Learning objective
    """
    response = model.generate_content(blueprint_prompt)
    blueprint = json.loads(clean_json(response.text))
    
    # --- Phase B: The Content Factory ---
    status_container.write("🏭 Phase B: Manufacturing Content...")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        
        # Save Blueprint
        zf.writestr("Lesson_Plans/Unit_Blueprint.json", json.dumps(blueprint, indent=2))
        
        media_prompts = []
        
        for day in blueprint['days']:
            day_num = day['day']
            day_title = day['title']
            activity = day['activity_type']
            
            status_container.write(f"   - Processing Day {day_num}: {day_title} ({activity})")
            
            if activity == 'Lecture':
                slide_prompt = f"""
                Create content for a lecture on: {day_title}.
                Target: {grade} {subject}.
                Format: Text file with slide titles and bullet points.
                """
                resp = model.generate_content(slide_prompt)
                zf.writestr(f"Lesson_Plans/Day_{day_num}_Slides.txt", resp.text)
                
            elif activity == 'Assignment':
                assign_prompt = f"""
                Create a Canvas Assignment HTML for: {day_title}.
                Topic: {topic}. Grade: {grade}.
                Include a description, instructions, and a rubric.
                Return ONLY the HTML code.
                """
                resp = model.generate_content(assign_prompt)
                # Simple cleanup if it returns markdown
                html_content = clean_json(resp.text) # Reuse clean_json to strip markdown blocks if present
                zf.writestr(f"Assignments/Day_{day_num}_Assignment.html", html_content)
                
            elif activity == 'Quiz':
                quiz_prompt = f"""
                Create a QTI v1.2 XML Quiz for: {day_title}.
                Topic: {topic}. Grade: {grade}.
                5 Multiple Choice Questions.
                Use CDATA for question text.
                Return ONLY the XML code.
                """
                resp = model.generate_content(quiz_prompt)
                xml_content = clean_json(resp.text)
                zf.writestr(f"Quizzes/Day_{day_num}_Quiz.xml", xml_content)
            
            # --- Phase C: Media Studio (Accumulate Prompts) ---
            media_prompts.append(f"Day {day_num} ({day_title}): Educational illustration showing {day_title} for {grade} students.")
            
        # Save Media Prompts
        status_container.write("🎨 Phase C: Generating Media Prompts...")
        zf.writestr("Media/Media_Prompts.txt", "\n".join(media_prompts))
        
    # --- Phase D: Packaging ---
    status_container.write("📦 Phase D: Packaging & Shipping...")
    zip_filename = f"{topic.replace(' ', '_')}_Unit_Bundle.zip"
    
    # We need to write the buffer to a file to send it via email function which expects a path
    with open(zip_filename, "wb") as f:
        f.write(zip_buffer.getvalue())
        
    return zip_filename

# --- Sidebar ---
st.sidebar.title("🏭 Factory Settings")
uploaded_key = st.sidebar.file_uploader("Upload service_account.json", type="json")
sheet_name = st.sidebar.text_input("Orders Spreadsheet Name", value="AI_Education_Orders")

if uploaded_key:
    st.sidebar.success("🔑 Key Uploaded")
else:
    st.sidebar.warning("⚠️ Waiting for Key")

# --- Main Dashboard ---
st.title("🏭 AI Curriculum Factory")

if uploaded_key and sheet_name:
    try:
        sheet = connect_to_sheets(uploaded_key, sheet_name)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Filter Pending Orders
        if 'Status' in df.columns:
            pending_orders = df[df['Status'] != 'Shipped']
        else:
            st.error("Sheet must have a 'Status' column.")
            st.stop()
        
        st.subheader(f"Pending Orders ({len(pending_orders)})")
        
        # Display Orders as Cards
        for index, row in pending_orders.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"### {row['Topic']}")
                    st.caption(f"{row['Subject']} • Grade {row['Grade']}")
                with col2:
                    st.write(f"**Standard:** {row['Standards']}")
                    st.write(f"**Client:** {row['Client Email']}")
                with col3:
                    if st.button("🚀 Build Unit", key=f"btn_{index}", type="primary", use_container_width=True):
                        with st.status("🚀 Starting Factory Engine...", expanded=True) as status:
                            try:
                                client = genai
                                zip_path = build_unit_chain(row, client, status)
                                
                                status.write("📨 Sending Email...")
                                email_body = f"Hi,\n\nPlease find attached the complete 5-day Unit Plan for '{row['Topic']}'.\n\nIncludes:\n- Daily Lesson Plans\n- Assignment HTML\n- Quiz XML\n- Media Prompts\n\nBest,\nAI Curriculum Factory"
                                send_email(row['Client Email'], f"Unit Delivery: {row['Topic']}", email_body, zip_path)
                                
                                status.write("✅ Updating Database...")
                                # Update Sheet
                                # Find row index (1-based, +1 for header)
                                # Note: This simple index logic assumes dataframe index matches sheet rows. 
                                # Better to find by Order ID if possible, but for now we rely on index.
                                sheet_row = index + 2 
                                sheet.update_cell(sheet_row, df.columns.get_loc('Status') + 1, 'Shipped')
                                
                                status.update(label="✅ Unit Built & Shipped!", state="complete", expanded=False)
                                st.success(f"Unit for '{row['Topic']}' has been shipped!")
                                
                                # Cleanup
                                os.remove(zip_path)
                                time.sleep(2)
                                st.rerun()
                                
                            except Exception as e:
                                status.update(label="❌ Factory Error", state="error")
                                st.error(f"Production failed: {str(e)}")

    except Exception as e:
        st.error(f"Connection Error: {str(e)}")
else:
    st.info("Please upload your Google Service Account Key to power up the factory.")
