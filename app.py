import streamlit as st
import os, json, requests, io
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types
from PIL import Image

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Metata AI Pro", page_icon="📚", layout="wide")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. AUTHENTICATION ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("Metata | Library Access")
    t1, t2 = st.tabs(["Login", "Sign Up"])
    with t1:
        e = st.text_input("Email", key="l_e")
        p = st.text_input("Password", type="password", key="l_p")
        if st.button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user
                st.rerun()
            except Exception as err: st.error(f"Login Failed: {err}")
    st.stop()

# --- 3. PERMISSIONS ---
prof_res = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof_res.data[0] if prof_res.data else {"is_paid": False}
is_paid = user_data.get('is_paid', False)

# --- 4. MAIN INTERFACE ---
tab_batch, tab_history = st.tabs(["🚀 New Batch", "📜 Scan History"])

with tab_batch:
    st.title("Metata Smart Batch Engine")
    TARGET_MODEL = "gemini-2.0-pro" if is_paid else "gemini-2.0-pro"
    
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
        st.subheader("🖼️ Preview & Auto-Detection")
        
        ready_for_ai = []
        grid_cols = st.columns(len(raw_queue))
        
        for i, item in enumerate(raw_queue):
            with grid_cols[i]:
                try:
                    if item['is_url']:
                        img_data = requests.get(item['source']).content
                    else:
                        img_data = item['source'].getvalue()
                    
                    pil_img = Image.open(io.BytesIO(img_data))
                    
                    # --- STEP 1: AUTO-ORIENTATION DETECT ---
                    with st.spinner("Detecting orientation..."):
                        # We use the faster Flash model for the quick check
                        detect_prompt = "Is this image oriented correctly for reading text? If not, how many degrees clockwise should I rotate it to make it upright? Return JSON: {'rotate_degrees': 0/90/180/270}."
                        detect_res = ai_client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=[types.Part.from_bytes(data=img_data, mime_type="image/jpeg"), detect_prompt]
                        )
                        # Remove markdown and parse
                        rotation_data = json.loads(detect_res.text.replace('```json', '').replace('```', ''))
                        auto_rot = rotation_data.get('rotate_degrees', 0)

                    # Apply Auto-Rotation
                    if auto_rot != 0:
                        pil_img = pil_img.rotate(-auto_rot, expand=True)
                        st.caption(f"✨ Auto-corrected by {auto_rot}°")

                    # Allow manual fine-tuning
                    manual_rot = st.selectbox(f"Fine-tune {item['name']}", [0, 90, 180, 270], key=f"rot_{i}")
                    if manual_rot != 0:
                        pil_img = pil_img.rotate(-manual_rot, expand=True)
                    
                    st.image(pil_img, use_container_width=True)
                    
                    # Prepare for final extraction
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG")
                    ready_for_ai.append({"name": item['name'], "bytes": buf.getvalue()})
                    
                except Exception as e:
                    st.error(f"Error: {item['name']}")

        # --- RUN ANALYSIS ---
        if st.button("🚀 Process Corrected Batch"):
            if not is_paid and len(ready_for_ai) > 1:
                st.error("Free Tier limit: 1 image at a time.")
            else:
                results = []
                for img in ready_for_ai:
                    with st.status(f"Extracting Metadata for {img['name']}..."):
                        # STEP 2: DEEP METADATA EXTRACTION
                        prompt = "Generate library metadata in JSON: {title, author, year, language, summary, item_type}."
                        res = ai_client.models.generate_content(
                            model=TARGET_MODEL,
                            contents=[types.Part.from_bytes(data=img['bytes'], mime_type="image/jpeg"), prompt]
                        )
                        metadata = json.loads(res.text.replace('```json', '').replace('```', ''))
                        metadata['filename'] = img['name']
                        
                        supabase.table("catalog_history").insert({
                            "user_id": st.session_state.user.id,
                            "filename": img['name'],
                            "metadata": metadata,
                            "model_used": TARGET_MODEL
                        }).execute()
                        results.append(metadata)
                
                st.success("Analysis Complete!")
                st.table(pd.DataFrame(results))

with tab_history:
    st.header("Archival History")
    # (Same history logic from previous scripts)


