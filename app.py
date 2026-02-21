import streamlit as st
import os, json, requests, io
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types
from PIL import Image

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Metata AI Pro", page_icon="📚", layout="wide")

# Connection Secrets
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. AUTHENTICATION & PERMISSIONS ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("Metata | Library Access")
    # ... (Standard Login/Signup Tabs) ...
    st.stop()

prof_res = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof_res.data[0] if prof_res.data else {"is_paid": False}
is_paid = user_data.get('is_paid', False)

# --- 3. SIDEBAR CONTROLS ---
with st.sidebar:
    st.title("⚙️ Engine Settings")
    st.write(f"Logged in: **{st.session_state.user.email}**")
    
    # THE SKIP TOGGLE
    skip_auto_rot = st.checkbox("Skip Auto-Orientation", value=False, help="Enable this if your images are already upright or if you are getting processing errors.")
    
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# --- 4. MAIN INTERFACE ---
tab_batch, tab_history = st.tabs(["🚀 New Batch", "📜 Scan History"])

with tab_batch:
    st.title("Metata Smart Batch Engine")
    TARGET_MODEL = "gemini-2.0-pro" if is_paid else "gemini-2.0-flash"
    
    col1, col2 = st.columns(2)
    with col1:
        files = st.file_uploader("📁 Upload Images", accept_multiple_files=True, type=['jpg','png','jpeg'])
    with col2:
        url_input = st.text_input("🌐 Image URLs", placeholder="Paste links separated by |")

    raw_queue = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_input.split("|") if u.strip()][:3]
    for u in urls: raw_queue.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    if raw_queue:
        st.divider()
        st.subheader("🖼️ Preview & Processing")
        
        ready_for_ai = []
        grid_cols = st.columns(len(raw_queue))
        
        for i, item in enumerate(raw_queue):
            with grid_cols[i]:
                try:
                    # 1. Load Image
                    if item['is_url']:
                        img_data = requests.get(item['source']).content
                    else:
                        img_data = item['source'].getvalue()
                    
                    pil_img = Image.open(io.BytesIO(img_data))
                    
                    # 2. Conditional Auto-Orientation
                    if not skip_auto_rot:
                        with st.spinner("Detecting orientation..."):
                            # Create a thumbnail for the scout to avoid size-errors
                            check_img = pil_img.copy()
                            check_img.thumbnail((800, 800))
                            buf_check = io.BytesIO()
                            check_img.save(buf_check, format="JPEG")
                            
                            detect_prompt = "Return ONLY JSON: {'rotate_degrees': 0, 90, 180, or 270}."
                            detect_res = ai_client.models.generate_content(
                                model="gemini-2.0-flash",
                                contents=[types.Part.from_bytes(data=buf_check.getvalue(), mime_type="image/jpeg"), detect_prompt]
                            )
                            # Robust JSON parsing
                            clean_text = detect_res.text.strip().replace('```json', '').replace('```', '')
                            auto_rot = json.loads(clean_text).get('rotate_degrees', 0)
                            
                            if auto_rot != 0:
                                pil_img = pil_img.rotate(-auto_rot, expand=True)
                                st.caption(f"✨ Auto-corrected by {auto_rot}°")

                    # 3. Manual Fine-tune UI
                    manual_rot = st.selectbox(f"Rotate {item['name']}", [0, 90, 180, 270], key=f"rot_{i}")
                    if manual_rot != 0:
                        pil_img = pil_img.rotate(-manual_rot, expand=True)
                    
                    st.image(pil_img, use_container_width=True)
                    
                    # Prepare bytes for final analysis
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG")
                    ready_for_ai.append({"name": item['name'], "bytes": buf.getvalue()})
                    
                except Exception as e:
                    st.error(f"Error processing {item['name']}: Check file format or size.")

        # --- RUN ANALYSIS ---
        if st.button("🚀 Process Corrected Batch"):
            # (Processing loop remains the same, using TARGET_MODEL)
            # ... results logic ...
