import streamlit as st
import os, json, requests
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types
from pymarc import Record, Field

# --- 1. INITIALIZATION & SECRETS ---
st.set_page_config(page_title="Metata Pro", page_icon="📚", layout="wide")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY]):
    st.error("Environment variables missing. Please check Railway settings.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. SESSION STATE MANAGEMENT ---
if 'user' not in st.session_state:
    st.session_state.user = None

# --- 3. AUTHENTICATION UI ---
if st.session_state.user is None:
    st.title("Metata | Login")
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        email = st.text_input("Email", key="l_email")
        password = st.text_input("Password", type="password", key="l_pass")
        if st.button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                st.rerun()
            except Exception as e:
                st.error(f"Login Error: {e}")
    
    with tab2:
        new_email = st.text_input("Email", key="s_email")
        new_pass = st.text_input("Password", type="password", key="s_pass")
        if st.button("Create Account"):
            try:
                supabase.auth.sign_up({"email": new_email, "password": new_pass})
                st.info("Account created! Please check your email for confirmation.")
            except Exception as e:
                st.error(f"Signup Error: {e}")
    st.stop()

# --- 4. THE CORE APP (LOGGED IN) ---
st.sidebar.write(f"Logged in: **{st.session_state.user.email}**")
if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    st.session_state.user = None
    st.rerun()

st.title("Metata: Professional Library Intelligence")

# --- 5. SUBSCRIPTION CHECK ---
response = supabase.table("profiles").select("is_paid").eq("id", st.session_state.user.id).execute()

# Check if we actually found a row
if response.data and len(response.data) > 0:
    is_paid = response.data[0].get('is_paid', False)
else:
    # If no profile exists, default to free and maybe show a warning
    is_paid = False
    st.sidebar.warning("Profile not initialized. Please try logging out and back in.")

if not is_paid:
    st.warning("💳 **Free Tier Active**: You are limited to 1 item per scan. Upgrade to Pro for 3+3 Batch processing.")

# --- 6. INPUT SECTION ---
col1, col2 = st.columns(2)
with col1:
    files = st.file_uploader("📁 Upload Images (Max 3)", accept_multiple_files=True, type=['jpg','png','jpeg'])
with col2:
    url_input = st.text_input("🌐 Image URLs (URL1 | URL2 | URL3)", placeholder="URL1 | URL2")

# --- 7. BATCH ENGINE ---
if st.button("🚀 Run Analysis"):
    # Unified Queue
    queue = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_input.split("|") if u.strip()][:3]
    for u in urls:
        queue.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    # ENFORCE PAYWALL
    if not is_paid and len(queue) > 1:
        st.error(f"Limit exceeded. Free users can process 1 item. You requested {len(queue)}.")
        st.stop()

    if not queue:
        st.warning("Please provide an image.")
    else:
        results = []
        for item in queue:
            with st.status(f"Scanning {item['name']}...") as status:
                try:
                    # Get Bytes
                    if item['is_url']:
                        img_data = requests.get(item['source']).content
                    else:
                        img_data = item['source'].getvalue()

                    # AI Step 1: Discover
                    router_prompt = "Identify: {'label': (modern_book/film_poster), 'lang': (en/zh), 'is_valid': bool}. JSON only."
                    res1 = ai_client.models.generate_content(
                        model="gemini-2.5-pro",
                        contents=[types.Part.from_bytes(data=img_data, mime_type="image/jpeg"), router_prompt]
                    )
                    discovery = json.loads(res1.text.replace('```json', '').replace('```', ''))

                    if not discovery.get('is_valid'):
                        st.error(f"Skipped {item['name']}: Not a library item.")
                        continue

                    # Fetch Modular Prompts
                    task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
                    lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
                    
                    # AI Step 2: Extraction
                    final_prompt = f"{task.data['prompt_text']} {lang.data['formatting_instruction']}"
                    res2 = ai_client.models.generate_content(
                        model="gemini-2.5-pro",
                        contents=[types.Part.from_bytes(data=img_data, mime_type="image/jpeg"), final_prompt]
                    )
                    metadata = json.loads(res2.text.replace('```json', '').replace('```', ''))
                    metadata['source'] = item['name']
                    results.append(metadata)
                    status.update(label=f"Done: {item['name']}", state="complete")

                except Exception as e:
                    st.error(f"Error on {item['name']}: {e}")

        if results:
            st.divider()
            df = pd.DataFrame(results)
            st.dataframe(df)
            st.download_button("📥 Download Results (CSV)", df.to_csv(index=False), "metata_results.csv")




