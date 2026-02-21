import streamlit as st
import os, io, requests, pandas as pd
from PIL import Image
from supabase import create_client
from google import genai
from engine import run_metadata_extraction, convert_llm_json_to_marc

st.set_page_config(page_title="Metata Pro", layout="wide", page_icon="📚")

# --- DATABASE & AI SETUP ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- AUTH GATEKEEPER ---
if 'user' not in st.session_state: st.session_state.user = None

if st.session_state.user is None:
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        st.title("📚 Metata Login")
        e = st.text_input("Email")
        p = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user
                st.rerun()
            except: st.error("Authentication failed.")
    st.stop()

# --- APP LOADED ---
prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof.data[0] if prof.data else {"is_paid": False, "role": "librarian"}
is_paid = user_data.get('is_paid', False)

tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 History", "⚙️ Prompts"])

with tab_batch:
    st.title("Metata Smart Batch")
    
    with st.container(border=True):
        st.subheader("📥 Input Images")
        files = st.file_uploader("Drop Files", accept_multiple_files=True, type=['jpg','png','jpeg'])
        urls_raw = st.text_area("Or Paste URLs (pipe | separated)")

    # Queue Build
    raw_q = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in urls_raw.replace('\n', '|').split("|") if u.strip()][:3]
    for u in urls: raw_q.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    ready = []
    if raw_q:
        st.success(f"📋 **Worklist:** {len(raw_q)} items loaded.")
        cols = st.columns(len(raw_q))
        for i, item in enumerate(raw_q):
            with cols[i]:
                try:
                    d = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                    img = Image.open(io.BytesIO(d))
                    r = st.selectbox(f"Rotate {i}", [0,90,180,270], key=f"rot{i}")
                    if r != 0: img = img.rotate(-r, expand=True)
                    st.image(img, use_container_width=True)
                    buf = io.BytesIO(); img.save(buf, format="JPEG")
                    ready.append({"name": item['name'], "bytes": buf.getvalue()})
                except: st.error("Load failed")

    if st.button("🚀 Run Analysis", use_container_width=True):
        results = []
        for item in ready:
            with st.container(border=True):
                st.write(f"### 🔎 Analyzing: {item['name']}")
                with st.status("AI Engines Working...") as status:
                    # Capture Tuple
                    discovery, meta = run_metadata_extraction(ai_client, supabase, item['bytes'], item['name'], is_paid)
                    
                    # Display Step 1
                    st.write("**Step 1: Discovery**")
                    c1, c2 = st.columns(2)
                    c1.info(f"🏷️ Label: {discovery.get('label')}")
                    c2.info(f"🌍 Lang: {discovery.get('lang')}")
                    
                    if "error" in meta:
                        st.error(f"Step 2 Failed: {meta['error']}")
                    else:
                        st.success("Step 2: Metadata Extracted")
                        meta['_filename'] = item['name']
                        results.append(meta) # Append the dict only
                status.update(label="Scanning Complete", state="complete")
        
        if results:
            st.session_state.current_results = results
            st.rerun()

    if 'current_results' in st.session_state:
        res = st.session_state.current_results
        t_tab, t_marc = st.tabs(["📊 Table", "📑 MARC View"])
        with t_tab: st.dataframe(pd.DataFrame(res))
        with t_marc:
            for entry in res:
                lines = [f"{k} ## {v}" for k, v in entry.items() if k.isdigit()]
                st.code("\n".join(lines))
            st.download_button("Download .mrc", convert_llm_json_to_marc(res), "batch.mrc")
