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

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY]):
    st.error("Missing Environment Variables. Please check Railway settings.")
    st.stop()

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
    with t2:
        ne = st.text_input("Email", key="s_e")
        np = st.text_input("Password", type="password", key="s_p")
        if st.button("Create Account"):
            try:
                supabase.auth.sign_up({"email": ne, "password": np})
                st.info("Check your email for confirmation!")
            except Exception as err: st.error(f"Signup Failed: {err}")
    st.stop()

# --- 3. PERMISSIONS & SIDEBAR ---
prof_res = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof_res.data[0] if prof_res.data else {"is_paid": False}
is_paid = user_data.get('is_paid', False)

with st.sidebar:
    st.title("⚙️ Engine Settings")
    st.write(f"Logged in: **{st.session_state.user.email}**")
    skip_auto_rot = st.checkbox("Skip Auto-Orientation", value=False)
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# --- 4. MAIN INTERFACE ---
tab_batch, tab_history = st.tabs(["🚀 New Batch", "📜 Scan History"])

with tab_batch:
    st.title("Metata Smart Batch Engine")
    TARGET_MODEL = "gemini-2.0-pro" if is_paid else "gemini-2.0-pro"
    
    col1, col2 = st.columns(2)
    with col1:
        files = st.file_uploader("📁 Upload Images", accept_multiple_files=True, type=['jpg','png','jpeg'])
    with col2:
        url_input = st.text_input("🌐 Image URLs", placeholder="URL1 | URL2")

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
                    # Load Image
                    img_data = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                    pil_img = Image.open(io.BytesIO(img_data))
                    
                    if not skip_auto_rot:
                        with st.spinner("Detecting..."):
                            check_img = pil_img.copy()
                            check_img.thumbnail((800, 800))
                            buf_check = io.BytesIO()
                            check_img.save(buf_check, format="JPEG")
                            
                            detect_res = ai_client.models.generate_content(
                                model="gemini-2.0-flash",
                                contents=[types.Part.from_bytes(data=buf_check.getvalue(), mime_type="image/jpeg"), 
                                          "Return ONLY JSON: {'rotate_degrees': 0, 90, 180, or 270}."]
                            )
                            auto_rot = json.loads(detect_res.text.strip().replace('```json', '').replace('```', '')).get('rotate_degrees', 0)
                            if auto_rot != 0:
                                pil_img = pil_img.rotate(-auto_rot, expand=True)
                                st.caption(f"✨ Auto-corrected {auto_rot}°")

                    # Manual Fine-tune & Image Display
                    m_rot = st.selectbox(f"Rotate {item['name']}", [0, 90, 180, 270], key=f"rot_{i}")
                    if m_rot != 0: pil_img = pil_img.rotate(-m_rot, expand=True)
                    st.image(pil_img, use_container_width=True)
                    
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG")
                    ready_for_ai.append({"name": item['name'], "bytes": buf.getvalue()})
                except Exception as e:
                    st.error(f"Error loading {item['name']}")

        if st.button("🚀 Process Corrected Batch"):
            if not is_paid and len(ready_for_ai) > 1:
                st.error("Free Tier limit: 1 image at a time.")
            else:
                results = []
                for img in ready_for_ai:
                    with st.status(f"Extracting Metadata for {img['name']}..."):
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
                
                st.success("Batch Analysis Complete!")
                st.dataframe(pd.DataFrame(results))

with tab_history:
    st.header("Archival History")
    hist_res = supabase.table("catalog_history").select("*").eq("user_id", st.session_state.user.id).order("created_at", desc=True).execute()
    if hist_res.data:
        for entry in hist_res.data:
            with st.expander(f"{entry['created_at'][:10]} | {entry['filename']}"):
                st.json(entry['metadata'])
