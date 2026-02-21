import streamlit as st
import os, io, requests, pandas as pd
from PIL import Image
from supabase import create_client
from google import genai
from engine import run_metadata_extraction, convert_llm_json_to_marc

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="Metata Pro", layout="wide", page_icon="📚")

# Ensure these are in your Railway Environment Variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. THE LOGIN GATEKEEPER ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    # THIS IS THE ONLY THING UNAUTHORIZED USERS SEE
    st.container()
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        st.title("📚 Metata | Library Login")
        st.markdown("Please sign in to access the AI Cataloging Engine.")
        
        tab_login, tab_signup = st.tabs(["🔐 Login", "📝 Create Account"])
        
        with tab_login:
            email = st.text_input("Email Address", key="login_email")
            password = st.text_input("Password", type="password", key="login_pwd")
            if st.button("Sign In", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.success("Access Granted!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Authentication Failed: {str(e)}")
        
        with tab_signup:
            new_email = st.text_input("Work Email", key="signup_email")
            new_password = st.text_input("New Password", type="password", key="signup_pwd")
            if st.button("Request Access", use_container_width=True):
                try:
                    supabase.auth.sign_up({"email": new_email, "password": new_password})
                    st.info("Check your inbox for a verification email!")
                except Exception as e:
                    st.error(f"Signup Failed: {str(e)}")
    
    # Stop execution here so no other app parts load
    st.stop()

# --- 3. AUTHORIZED APP (Only reachable after login) ---

# Fetch Permissions
prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof.data[0] if prof.data else {"is_paid": False, "role": "librarian"}
is_paid = user_data.get('is_paid', False)
user_role = user_data.get('role', 'librarian')

# Sidebar for Logout & Tier Info
with st.sidebar:
    st.title("Metata Control")
    st.write(f"User: **{st.session_state.user.email}**")
    st.write(f"Tier: {'✅ PRO' if is_paid else '🆓 FREE'}")
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# Tabs for Main App Functions
tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 History", "⚙️ Prompt Manager"])

# ... [The rest of your tab_batch, tab_history, and tab_prompts logic follows] ...
