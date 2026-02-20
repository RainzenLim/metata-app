import streamlit as st
import os
from supabase import create_client, Client

# --- INITIALIZATION ---
supabase: Client = create_client(os.getenv(SUPABASE_URL), os.getenv(SUPABASE_KEY))

# --- USER MANAGEMENT FUNCTIONS ---
def sign_in(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = res.user
        st.success("Welcome back!")
        st.rerun()
    except Exception as e:
        st.error(f"Login failed: {e}")

def sign_up(email, password):
    try:
        supabase.auth.sign_up({"email": email, "password": password})
        st.info("Check your email for a confirmation link!")
    except Exception as e:
        st.error(f"Signup failed: {e}")

def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.rerun()

# --- AUTH UI LOGIC ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pwd")
        if st.button("Login"):
            sign_in(email, password)
            
    with tab2:
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_pwd")
        if st.button("Create Account"):
            sign_up(new_email, new_password)
else:
    # --- LOGGED IN: SHOW THE APP ---
    st.sidebar.write(f"Logged in as: {st.session_state.user.email}")
    if st.sidebar.button("Logout"):
        logout()
    
    # YOUR ORIGINAL APP LOGIC GOES HERE (The 3+3 Batch Engine)
    # Important: When saving to DB, use st.session_state.user.id to tag the record!

