import streamlit as st
import os, json, requests, io
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Metata AI", page_icon="📚", layout="wide")

# Connection Secrets (Set these in Railway.app)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY]):
    st.error("Missing Environment Variables. Please check Railway settings.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. AUTHENTICATION & SESSION STATE ---
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
                st.info("Check your email for a confirmation link!")
            except Exception as err: st.error(f"Signup Failed: {err}")
    st.stop()

# --- 3. PERMISSIONS FETCH ---
# Safer fetch to avoid PGRST116 error if profile is missing
prof_res = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof_res.data[0] if prof_res.data else {"is_paid": False, "role": "librarian"}
is_paid = user_data.get('is_paid', False)
user_role = user_data.get('role', 'librarian')

# --- 4. SIDEBAR & ADMIN CONTROLS ---
with st.sidebar:
    st.title("Metata Admin")
    st.write(f"Logged in: **{st.session_state.user.email}**")
    st.write(f"Tier: {'✅ PRO' if is_paid else '🆓 FREE'}")
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    if user_role == 'admin':
        st.divider()
        if st.checkbox("🛠️ Manage Users"):
            st.subheader("Global User List")
            all_u = supabase.table("profiles").select("*").execute()
            for u in all_u.data:
                col_u, col_p = st.columns([2, 1])
                col_u.write(f"{u['email']}")
                btn_label = "Free" if u['is_paid'] else "Paid"
                if col_p.button(f"Make {btn_label}", key=f"p_{u['id']}"):
                    supabase.table("profiles").update({"is_paid": not u['is_paid']}).eq("id", u['id']).execute()
                    st.rerun()

# --- 5. MAIN NAVIGATION ---
tab_batch, tab_history = st.tabs(["🚀 New Batch", "📜 Scan History"])

with tab_batch:
    st.title("Metata Batch Engine")
    
    # Decide model based on payment status
    TARGET_MODEL = "gemini-2.0-pro" if is_paid else "gemini-2.0-flash"
    st.caption(f"Engine: {TARGET_MODEL}")

    col1, col2 = st.columns(2)
    with col1:
        files = st.file_uploader("📁 Upload (Max 3)", accept_multiple_files=True, type=['jpg','png','jpeg'])
    with col2:
        url_input = st.text_input("🌐 URLs (URL1 | URL2 | URL3)", placeholder="Paste links separated by |")

    if st.button("🚀 Run Batch Analysis"):
        # 3+3 Guardrail
        queue = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
        urls = [u.strip() for u in url_input.split("|") if u.strip()][:3]
        for u in urls: queue.append({"name": u.split('/')[-1], "source": u, "is_url": True})

        if not is_paid and len(queue) > 1:
            st.error("Free users are limited to 1 scan per batch. Upgrade for full 3+3 batch support.")
            st.stop()

        if not queue:
            st.warning("Please provide an image.")
        else:
            results = []
            for item in queue:
                with st.status(f"Scanning {item['name']}...") as status:
                    try:
                        # Load and Display with Zoom Support
                        if item['is_url']:
                            img_bytes = requests.get(item['source']).content
                        else:
                            img_bytes = item['source'].getvalue()
                        
                        # Real-time Display
                        st.image(img_bytes, width=300, caption=f"Processing {item['name']}")
                        with st.expander("🔍 Click to view full resolution"):
                            st.image(img_bytes, use_container_width=True)

                        # AI Logic
                        prompt = "Return JSON ONLY: {title, author, year, language, isbn, summary, item_type}."
                        res = ai_client.models.generate_content(
                            model=TARGET_MODEL,
                            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), prompt]
                        )
                        
                        metadata = json.loads(res.text.replace('```json', '').replace('```', ''))
                        metadata['filename'] = item['name']
                        
                        # Save to History
                        supabase.table("catalog_history").insert({
                            "user_id": st.session_state.user.id,
                            "filename": item['name'],
                            "metadata": metadata,
                            "model_used": TARGET_MODEL
                        }).execute()
                        
                        results.append(metadata)
                        status.update(label=f"Completed: {item['name']}", state="complete")
                    except Exception as e:
                        st.error(f"Error {item['name']}: {e}")

            if results:
                st.divider()
                df = pd.DataFrame(results)
                st.subheader("Batch Summary")
                st.table(df)
                st.download_button("📥 Download Records (CSV)", df.to_csv(index=False), "metata_results.csv")

with tab_history:
    st.header("Archival History")
    hist_res = supabase.table("catalog_history").select("*").eq("user_id", st.session_state.user.id).order("created_at", desc=True).execute()
    
    if hist_res.data:
        search = st.text_input("🔍 Filter by filename...")
        for entry in hist_res.data:
            if not search or search.lower() in entry['filename'].lower():
                with st.expander(f"{entry['created_at'][:10]} | {entry['filename']}"):
                    st.json(entry['metadata'])
                    st.caption(f"Model used: {entry['model_used']}")
    else:
        st.info("No scan history found.")
