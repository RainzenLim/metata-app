import streamlit as st
import os, io, requests, pandas as pd
from PIL import Image
from supabase import create_client
from google import genai
from engine import run_metadata_extraction, convert_llm_json_to_marc

# --- CONFIG ---
st.set_page_config(page_title="Metata Pro", layout="wide")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- AUTH (Simplified for logic flow) ---
if 'user' not in st.session_state: st.session_state.user = None
if not st.session_state.user:
    st.title("Metata Login")
    # ... [Your Auth Logic here] ...
    st.stop()

# Permissions
prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof.data[0] if prof.data else {"is_paid": False, "role": "admin"}
is_paid, user_role = user_data.get('is_paid', False), user_data.get('role', 'librarian')

tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 History", "⚙️ Prompts"])

with tab_batch:
    # --- UNIFIED INPUT BOX ---
    with st.container(border=True):
        st.subheader("📥 Add Images (Files or URLs)")
        files = st.file_uploader("Upload local images", accept_multiple_files=True, type=['jpg','png'])
        url_input = st.text_area("Paste Image URLs (One per line or pipe separated)", placeholder="http://image1.jpg | http://image2.jpg")

    # Combine sources
    raw_q = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_input.replace('\n', '|').split("|") if u.strip()][:3]
    for u in urls: raw_q.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    # --- PREVIEW & ROTATE ---
    ready = []
    if raw_q:
        st.divider()
        cols = st.columns(len(raw_q))
        for i, item in enumerate(raw_q):
            with cols[i]:
                try:
                    data = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                    img = Image.open(io.BytesIO(data))
                    rot = st.selectbox(f"Rotate {i}", [0, 90, 180, 270], key=f"r{i}")
                    if rot != 0: img = img.rotate(-rot, expand=True)
                    st.image(img, use_container_width=True)
                    buf = io.BytesIO(); img.save(buf, format="JPEG")
                    ready.append({"name": item['name'], "bytes": buf.getvalue()})
                except: st.error("Load failed.")

    # --- EXECUTION ---
    if st.button("🚀 Run Analysis", use_container_width=True):
        results = []
        for img in ready:
            with st.status(f"Scanning {img['name']}..."):
                res = run_metadata_extraction(ai_client, supabase, img['bytes'], img['name'], is_paid)
                if "error" not in res: results.append(res)
        
        if results:
            st.session_state.current_results = results
            st.rerun()

    # --- DISPLAY & EXPORT ---
    if 'current_results' in st.session_state:
        res = st.session_state.current_results
        t1, t2 = st.tabs(["📑 MARC View", "📊 Table"])
        with t1:
            for entry in res:
                st.code("\n".join([f"{k} ## {v}" for k, v in entry.items() if k.isdigit()]))
            
            m_bin = convert_llm_json_to_marc(res)
            st.download_button("Download MARC Binary (.mrc)", m_bin, "export.mrc")
        with t2:
            st.dataframe(pd.DataFrame(res))
