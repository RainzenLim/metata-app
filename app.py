import streamlit as st
import os, io, requests, json
import pandas as pd
from PIL import Image
from supabase import create_client
from google import genai
from engine import run_metadata_extraction

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="Metata AI Pro", page_icon="📚", layout="wide")

# Ensure these are in Railway Variables
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- 2. AUTHENTICATION ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("Metata | Access Control")
    t1, t2 = st.tabs(["Login", "Sign Up"])
    with t1:
        e = st.text_input("Email", key="l_e")
        p = st.text_input("Password", type="password", key="l_p")
        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({"email": e, "password": p})
            st.session_state.user = res.user
            st.rerun()
    st.stop()

# Permissions
prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof.data[0] if prof.data else {"is_paid": False, "role": "librarian"}
is_paid, user_role = user_data.get('is_paid', False), user_data.get('role', 'librarian')

# --- 3. MAIN UI ---
tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 Scan History", "⚙️ Prompt Manager"])

# --- TAB 1: BATCH PROCESSING ---
with tab_batch:
    st.title("Metata Smart Batch Engine")
    
    # Live Status Indicator
    tier = 'paid' if is_paid else 'free'
    scout_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", 'scout').single().execute()
    ext_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", tier).single().execute()
    st.info(f"🤖 **Status:** Scout (`{scout_cfg.data['model_id']}`) | Librarian (`{ext_cfg.data['model_id']}`)")

    # Unified Input
    with st.container(border=True):
        st.subheader("📥 Add Images")
        c1, c2 = st.columns(2)
        with c1: files = st.file_uploader("Upload files", accept_multiple_files=True, type=['jpg','png','jpeg'])
        with c2: url_in = st.text_input("Or paste URLs", placeholder="URL1 | URL2")

    # Preview & Rotation
    raw_q = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_in.split("|") if u.strip()][:3]
    for u in urls: raw_q.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    ready = []
    if raw_q:
        st.divider()
        cols = st.columns(len(raw_q))
        for i, item in enumerate(raw_q):
            with cols[i]:
                img_data = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                pil_img = Image.open(io.BytesIO(img_data))
                rot = st.selectbox(f"Rotate {item['name']}", [0, 90, 180, 270], key=f"r_{i}")
                if rot != 0: pil_img = pil_img.rotate(-rot, expand=True)
                st.image(pil_img, use_container_width=True)
                buf = io.BytesIO(); pil_img.save(buf, format="JPEG")
                ready.append({"name": item['name'], "bytes": buf.getvalue()})

    if st.button("🚀 Run Analysis", use_container_width=True):
        if not is_paid and len(ready) > 1: st.error("Free users: 1 image limit.")
        elif ready:
            results = []
            for img in ready:
                with st.status(f"Processing {img['name']}..."):
                    data = run_metadata_extraction(ai_client, supabase, img['bytes'], img['name'], is_paid)
                    if "error" not in data:
                        supabase.table("catalog_history").insert({"user_id": st.session_state.user.id, "filename": img['name'], "metadata": data}).execute()
                        results.append(data)
            if results: st.dataframe(pd.DataFrame(results))

# --- TAB 2: HISTORY ---
with tab_history:
    st.header("Archival Records")
    hist = supabase.table("catalog_history").select("*").eq("user_id", st.session_state.user.id).order("created_at", desc=True).execute()
    for entry in (hist.data if hist.data else []):
        with st.expander(f"{entry['created_at'][:10]} | {entry['filename']}"):
            st.json(entry['metadata'])

# --- TAB 3: PROMPT & MODEL MANAGER ---
with tab_prompts:
    st.header("Metata Engine Management")
    if user_role != 'admin':
        st.warning("Admin access only.")
    else:
        # Model Control
        st.subheader("🤖 Global Model Management")
        models = supabase.table("model_settings").select("*").execute()
        for m in models.data:
            c_t, c_m = st.columns([1, 2])
            new_m = c_m.selectbox(f"Set {m['tier_name'].title()}", ["gemini-2.0-flash", "gemini-2.0-pro"], index=0 if "flash" in m['model_id'] else 1, key=f"m_{m['id']}")
            if new_m != m['model_id']:
                supabase.table("model_settings").update({"model_id": new_m}).eq("id", m['id']).execute()
                st.rerun()
        
        # Prompt Control
        st.divider()
        st.subheader("📝 Instruction Management")
        items = supabase.table("item_prompts").select("*").execute()
        for i in items.data:
            with st.expander(f"Task: {i['label']}"):
                txt = st.text_area("Prompt", value=i['prompt_text'], key=f"i_{i['id']}")
                if st.button("Save", key=f"bi_{i['id']}"):
                    supabase.table("item_prompts").update({"prompt_text": txt}).eq("id", i['id']).execute()
                    st.rerun()
