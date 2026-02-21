import streamlit as st
import os, io, requests, json
import pandas as pd
from PIL import Image
from supabase import create_client
from google import genai
from engine import run_metadata_extraction, convert_llm_json_to_marc

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="Metata Pro", layout="wide", page_icon="📚")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. THE LOGIN GATEKEEPER ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        st.title("📚 Metata | Library Login")
        tab_login, tab_signup = st.tabs(["🔐 Login", "📝 Create Account"])
        with tab_login:
            email = st.text_input("Email", key="l_e")
            pwd = st.text_input("Password", type="password", key="l_p")
            if st.button("Sign In", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                    st.session_state.user = res.user
                    st.rerun()
                except: st.error("Login Failed.")
    st.stop()

# --- 3. AUTHORIZED APP ---
prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof.data[0] if prof.data else {"is_paid": False, "role": "librarian"}
is_paid, user_role = user_data.get('is_paid', False), user_data.get('role', 'librarian')

with st.sidebar:
    st.title("Metata Control")
    st.write(f"Logged in: **{st.session_state.user.email}**")
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# --- TABS NAVIGATION ---
tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 History", "⚙️ Prompt Manager"])

# --- TAB: NEW BATCH ---
with tab_batch:
    st.title("Metata Smart Batch Engine")
    
    # Unified Input Area
    with st.container(border=True):
        st.subheader("📥 Add Images (Files or URLs)")
        files = st.file_uploader("Upload local images", accept_multiple_files=True, type=['jpg','png','jpeg'])
        url_input = st.text_area("Paste Image URLs (one per line or separated by | )")

    # Queue Logic
    raw_q = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_input.replace('\n', '|').split("|") if u.strip()][:3]
    for u in urls:
        raw_q.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    # --- NEW: BATCH STATUS BAR ---
    if raw_q:
        q_count = len(raw_q)
        st.write("") # Spacer
        st.success(f"📋 **Worklist Status:** {q_count} item(s) ready for orientation.")
        
        st.divider()
        st.subheader("🖼️ Preview & Manual Orientation")
        
        ready = []
        cols = st.columns(len(raw_q))
        for i, item in enumerate(raw_q):
            with cols[i]:
                try:
                    img_data = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                    pil_img = Image.open(io.BytesIO(img_data))
                    
                    rot = st.selectbox(f"Rotate {item['name']}", [0, 90, 180, 270], key=f"r_{i}")
                    if rot != 0:
                        pil_img = pil_img.rotate(-rot, expand=True)
                    
                    st.image(pil_img, use_container_width=True)
                    
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG")
                    ready.append({"name": item['name'], "bytes": buf.getvalue()})
                except:
                    st.error(f"Failed: {item['name']}")

        # --- EXECUTION ---
        if st.button("🚀 Run Analysis on Worklist", use_container_width=True):
            results = []
            for img in ready:
                with st.status(f"Scanning {img['name']}..."):
                    res = run_metadata_extraction(ai_client, supabase, img['bytes'], img['name'], is_paid)
                    if "error" not in res:
                        supabase.table("catalog_history").insert({
                            "user_id": st.session_state.user.id,
                            "filename": img['name'],
                            "metadata": res
                        }).execute()
                        results.append(res)
            
            if results:
                st.session_state.current_results = results
                st.rerun()

    # --- RESULT DISPLAY & EXPORT ---
    if 'current_results' in st.session_state:
        res = st.session_state.current_results
        t_view, t_marc = st.tabs(["📊 Metadata Table", "📑 MARC View"])
        
        with t_view:
            st.dataframe(pd.DataFrame(res))
        
        with t_marc:
            for entry in res:
                st.code("\n".join([f"{k} ## {v}" for k, v in entry.items() if k.isdigit()]))
            
            m_bin = convert_llm_json_to_marc(res)
            st.download_button("Download Binary MARC (.mrc)", m_bin, "metata_batch.mrc")

# --- TAB: HISTORY ---
with tab_history:
    st.header("Archival History")
    hist = supabase.table("catalog_history").select("*").eq("user_id", st.session_state.user.id).order("created_at", desc=True).execute()
    if hist.data:
        for entry in hist.data:
            with st.expander(f"{entry['created_at'][:10]} | {entry['filename']}"):
                st.json(entry['metadata'])

# --- TAB: PROMPT MANAGER ---
with tab_prompts:
    st.header("Metata Engine Logic")
    if user_role != 'admin':
        st.warning("Locked: Admin only.")
    else:
        # Include your model selection and prompt editing UI here
        st.info("Manage your DB-driven models and modular prompts here.")
