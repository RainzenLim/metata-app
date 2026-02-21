import streamlit as st
import os, json, requests, io
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Metata AI", page_icon="📚", layout="wide")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. AUTH & SESSION STATE ---
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

# --- 3. PERMISSIONS ---
prof_res = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof_res.data[0] if prof_res.data else {"is_paid": False, "role": "librarian"}
is_paid, user_role = user_data.get('is_paid', False), user_data.get('role', 'librarian')

# --- 4. SIDEBAR ---
with st.sidebar:
    st.write(f"Logged in: **{st.session_state.user.email}**")
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# --- 5. MAIN NAVIGATION ---
tab_batch, tab_history = st.tabs(["🚀 New Batch", "📜 Scan History"])

with tab_batch:
    st.title("Metata Batch Engine")
    TARGET_MODEL = "gemini-2.0-pro" if is_paid else "gemini-2.0-flash"
    
    col1, col2 = st.columns(2)
    with col1:
        files = st.file_uploader("📁 Upload Images (Max 3)", accept_multiple_files=True, type=['jpg','png','jpeg'])
    with col2:
        url_input = st.text_input("🌐 Image URLs (URL1 | URL2 | URL3)", placeholder="Paste links separated by |")

    # --- INSTANT PREVIEW SECTION (Before the button) ---
    queue = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_input.split("|") if u.strip()][:3]
    for u in urls: queue.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    if queue:
        st.divider()
        st.subheader("🖼️ Preview Gallery")
        preview_cols = st.columns(len(queue))
        ready_images = [] # Store bytes here so we don't have to re-fetch on click

        for i, item in enumerate(queue):
            with preview_cols[i]:
                try:
                    if item['is_url']:
                        img_bytes = requests.get(item['source']).content
                    else:
                        img_bytes = item['source'].getvalue()
                    
                    st.image(img_bytes, caption=item['name'], use_container_width=True)
                    ready_images.append({"name": item['name'], "bytes": img_bytes})
                except:
                    st.error(f"Could not load {item['name']}")

        # --- ACTION BUTTON ---
        if st.button("🚀 Run Batch Analysis"):
            if not is_paid and len(ready_images) > 1:
                st.error("Free users are limited to 1 scan per batch. Upgrade for 3+3 support.")
            else:
                results = []
                for img in ready_images:
                    with st.status(f"Processing {img['name']}..."):
                        prompt = "Return JSON ONLY: {title, author, year, language, isbn, summary, item_type}."
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
                
                st.success("Batch Complete!")
                st.table(pd.DataFrame(results))

with tab_history:
    st.header("Archival History")
    hist_res = supabase.table("catalog_history").select("*").eq("user_id", st.session_state.user.id).order("created_at", desc=True).execute()
    if hist_res.data:
        for entry in hist_res.data:
            with st.expander(f"{entry['created_at'][:10]} | {entry['filename']}"):
                st.json(entry['metadata'])

