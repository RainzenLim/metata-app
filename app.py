import streamlit as st
import os, io, requests, pandas as pd
from PIL import Image
from supabase import create_client
from google import genai
from engine import run_metadata_extraction, convert_llm_json_to_marc

st.set_page_config(page_title="Metata Pro", layout="wide", page_icon="📚")

# --- DATABASE & AI ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- 1. SECURE LOGIN ---
if 'user' not in st.session_state: st.session_state.user = None

if st.session_state.user is None:
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        st.title("📚 Metata Login")
        e = st.text_input("Email", key="l_email")
        p = st.text_input("Password", type="password", key="l_pass")
        if st.button("Login", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user
                st.rerun()
            except: st.error("Access Denied.")
    st.stop()

# --- 2. AUTHORIZED DASHBOARD ---
prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
is_paid = prof.data[0].get('is_paid', False) if prof.data else False

tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 History", "⚙️ Prompts"])

with tab_batch:
    # UNIFIED INPUT BOX
    with st.container(border=True):
        st.subheader("📥 Load Worklist")
        files = st.file_uploader("Files", accept_multiple_files=True, type=['jpg','png','jpeg'])
        urls_raw = st.text_area("URLs (pipe | or newline separated)")

    # Queue Build
    raw_q = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in urls_raw.replace('\n', '|').split("|") if u.strip()][:3]
    for u in urls: raw_q.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    ready = []
    if raw_q:
        st.success(f"📋 {len(raw_q)} items in worklist.")
        cols = st.columns(len(raw_q))
        for i, item in enumerate(raw_q):
            with cols[i]:
                try:
                    d = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                    img = Image.open(io.BytesIO(d))
                    r = st.selectbox(f"Rotate {i}", [0,90,180,270], key=f"r{i}")
                    if r != 0: img = img.rotate(-r, expand=True)
                    st.image(img, use_container_width=True)
                    buf = io.BytesIO(); img.save(buf, format="JPEG")
                    ready.append({"name": item['name'], "bytes": buf.getvalue()})
                except: st.error("Load failed")

    # EXECUTION WITH REAL-TIME STEP DISPLAY
    if st.button("🚀 Run AI Analysis", use_container_width=True):
        results = []
        for item in ready:
            with st.container(border=True):
                st.write(f"### 🔎 Analyzing: {item['name']}")
                with st.status("Engaging Engines...") as status:
                    # Unpack the tuple from engine
                    discovery, meta = run_metadata_extraction(ai_client, supabase, item['bytes'], item['name'], is_paid)
                    
                    # Display Step 1 Results
                    st.write("**Step 1: Scout Discovery**")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Base", discovery.get('base', 'N/A'))
                    c2.metric("Type", discovery.get('label', 'N/A'))
                    c3.metric("Lang", discovery.get('lang', 'N/A'))
                    
                    if "error" in meta:
                        st.error(f"Step 2 Failed: {meta['error']}")
                    else:
                        st.success("Step 2: MARC Metadata Extracted")
                        meta['_filename'] = item['name']
                        results.append(meta)
                status.update(label="Scanning Complete", state="complete")
        
        if results:
            st.session_state.current_results = results
            st.rerun()

    # OUTPUT EXPORTS
    if 'current_results' in st.session_state:
        res = st.session_state.current_results
        t_tab, t_marc = st.tabs(["📊 Table", "📑 MARC View"])
        with t_tab: st.dataframe(pd.DataFrame(res))
        with t_marc:
            for entry in res:
                lines = [f"{k} ## {v}" for k, v in entry.items() if k.isdigit()]
                st.code("\n".join(lines))
            st.download_button("Download MARC Binary (.mrc)", convert_llm_json_to_marc(res), "batch.mrc")
