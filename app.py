import streamlit as st
import os, io, requests
import pandas as pd
from PIL import Image
from supabase import create_client
from google import genai
from engine import run_metadata_extraction

# --- 1. CONFIG ---
st.set_page_config(page_title="Metata AI Pro", page_icon="📚", layout="wide")

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- 2. AUTH & PERMISSIONS ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("Metata | Library Intelligence")
    # ... [Auth Tabs Logic] ...
    st.stop()

prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof.data[0] if prof.data else {"is_paid": False, "role": "librarian"}
is_paid, user_role = user_data.get('is_paid', False), user_data.get('role', 'librarian')

# --- 3. MAIN UI ---
tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 Scan History", "⚙️ Prompt Manager"])

with tab_batch:
    # --- MODEL STATUS INDICATOR ---
    tier = 'paid' if is_paid else 'free'
    model_setting = supabase.table("model_settings").select("model_id").eq("tier_name", tier).single().execute()
    current_model = model_setting.data['model_id']
    
    st.info(f"🤖 **Engine Online:** Using `{current_model}` ({'Pro' if is_paid else 'Standard'} Logic)")

    # --- UNIFIED INPUT ---
    with st.container(border=True):
        st.subheader("📥 Add Images")
        c1, c2 = st.columns(2)
        with c1:
            files = st.file_uploader("Upload", accept_multiple_files=True, type=['jpg','png','jpeg'])
        with c2:
            url_in = st.text_input("URLs (pipe separated)", placeholder="URL1 | URL2")

    # --- PREVIEW & ROTATE ---
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
                rot = st.selectbox(f"Rotate", [0, 90, 180, 270], key=f"r_{i}")
                if rot != 0: pil_img = pil_img.rotate(-rot, expand=True)
                st.image(pil_img, use_container_width=True)
                
                buf = io.BytesIO()
                pil_img.save(buf, format="JPEG")
                ready.append({"name": item['name'], "bytes": buf.getvalue()})

    # --- ACTION ---
    if st.button("🚀 Run Analysis", use_container_width=True):
        if not is_paid and len(ready) > 1:
            st.error("Free users: 1 image per batch.")
        elif ready:
            results = []
            for img in ready:
                with st.status(f"Processing {img['name']}..."):
                    data = run_metadata_extraction(ai_client, supabase, img['bytes'], img['name'], is_paid)
                    if "error" not in data:
                        supabase.table("catalog_history").insert({"user_id": st.session_state.user.id, "filename": img['name'], "metadata": data}).execute()
                        results.append(data)
            if results: st.dataframe(pd.DataFrame(results))

# ... [Include tab_history and tab_prompts as before] ...
