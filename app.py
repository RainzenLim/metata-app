import streamlit as st
import os, json, requests, io
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types
from PIL import Image

# --- 1. CONFIGURATION & SECRETS ---
st.set_page_config(page_title="Metata AI Pro", page_icon="📚", layout="wide")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY]):
    st.error("Missing Environment Variables. Please check Railway settings.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. SESSION STATE & AUTH ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("Metata | Library Intelligence")
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
                st.info("Account created! Check your email for confirmation.")
            except Exception as err: st.error(f"Signup Failed: {err}")
    st.stop()

# --- 3. PERMISSIONS & SIDEBAR ---
prof_res = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof_res.data[0] if prof_res.data else {"is_paid": False, "role": "librarian"}
is_paid, user_role = user_data.get('is_paid', False), user_data.get('role', 'librarian')

with st.sidebar:
    st.title("Metata Control")
    st.write(f"Logged in: **{st.session_state.user.email}**")
    st.write(f"Tier: {'✅ PRO' if is_paid else '🆓 FREE'}")
    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# --- 4. MAIN NAVIGATION ---
tab_batch, tab_history, tab_prompts = st.tabs(["🚀 New Batch", "📜 Scan History", "⚙️ Prompt Manager"])

# --- TAB 1: BATCH PROCESSING ---
with tab_batch:
    st.title("Metata Modular Engine")
    EXTRACTION_MODEL = "gemini-2.5-pro" if is_paid else "gemini-2.5-pro"
    
    col_u, col_l = st.columns(2)
    with col_u:
        files = st.file_uploader("📁 Upload Images (Max 3)", accept_multiple_files=True, type=['jpg','png','jpeg'])
    with col_l:
        url_input = st.text_input("🌐 Image URLs", placeholder="URL1 | URL2")

    raw_queue = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_input.split("|") if u.strip()][:3]
    for u in urls: raw_queue.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    ready_for_ai = []
    if raw_queue:
        st.divider()
        st.subheader("🖼️ Preview & Manual Orientation")
        grid = st.columns(len(raw_queue))
        for i, item in enumerate(raw_queue):
            with grid[i]:
                try:
                    img_data = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                    pil_img = Image.open(io.BytesIO(img_data))
                    m_rot = st.selectbox(f"Rotate {item['name']}", [0, 90, 180, 270], key=f"rot_{i}")
                    if m_rot != 0: pil_img = pil_img.rotate(-m_rot, expand=True)
                    st.image(pil_img, use_container_width=True)
                    
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG")
                    ready_for_ai.append({"name": item['name'], "bytes": buf.getvalue()})
                except: st.error(f"Load Error: {item['name']}")

    if st.button("🚀 Run Analysis"):
        if not is_paid and len(ready_for_ai) > 1:
            st.error("Free Tier limit: 1 image per batch.")
            st.stop()

        if not ready_for_ai:
            st.warning("Please provide an image.")
        else:
            results = []
            for img in ready_for_ai:
                with st.status(f"Processing {img['name']}...") as status:
                    try:
                        # Step 1: Discover
                        router_prompt = "Identify: {'label': (modern_book/film_poster), 'lang': (en/zh/mi), 'is_valid': bool}. JSON only."
                        res1 = ai_client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=[types.Part.from_bytes(data=img['bytes'], mime_type="image/jpeg"), router_prompt]
                        )
                        discovery = json.loads(res1.text.strip().replace('```json', '').replace('```', ''))

                        if not discovery.get('is_valid'):
                            st.error(f"Skipped {img['name']}: Not a library item.")
                            continue

                        # Step 2: Fetch Modular Prompts
                        task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
                        lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
                        
                        # Step 3: Extraction
                        final_prompt = f"{task.data['prompt_text']} {lang.data['formatting_instruction']}"
                        res2 = ai_client.models.generate_content(
                            model=EXTRACTION_MODEL,
                            contents=[types.Part.from_bytes(data=img['bytes'], mime_type="image/jpeg"), final_prompt]
                        )
                        metadata = json.loads(res2.text.strip().replace('```json', '').replace('```', ''))
                        metadata['source'] = img['name']
                        
                        supabase.table("catalog_history").insert({
                            "user_id": st.session_state.user.id, "filename": img['name'], "metadata": metadata
                        }).execute()
                        results.append(metadata)
                        status.update(label=f"Done: {img['name']}", state="complete")
                    except Exception as e: st.error(f"Error on {img['name']}: {e}")

            if results:
                st.divider()
                df = pd.DataFrame(results)
                st.dataframe(df)
                st.download_button("📥 Download Results (CSV)", df.to_csv(index=False), "metata_results.csv")

# --- TAB 2: HISTORY ---
with tab_history:
    st.header("Archival History")
    hist_res = supabase.table("catalog_history").select("*").eq("user_id", st.session_state.user.id).order("created_at", desc=True).execute()
    if hist_res.data:
        search = st.text_input("🔍 Search filenames...")
        for entry in hist_res.data:
            if not search or search.lower() in entry['filename'].lower():
                with st.expander(f"{entry['created_at'][:10]} | {entry['filename']}"):
                    st.json(entry['metadata'])
    else: st.info("No scan history found.")

# --- TAB 3: PROMPT MANAGER ---
with tab_prompts:
    st.header("Metata Engine Logic")
    if user_role != 'admin':
        st.warning("Only Administrators can modify prompts.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Item Logic")
            item_p = supabase.table("item_prompts").select("*").execute()
            for item in item_p.data:
                with st.expander(f"Task: {item['label'].upper()}"):
                    new_p = st.text_area("Extraction Instructions", value=item['prompt_text'], key=f"ip_{item['id']}")
                    if st.button("Save", key=f"btn_ip_{item['id']}"):
                        supabase.table("item_prompts").update({"prompt_text": new_p}).eq("id", item['id']).execute()
                        st.success("Updated!")
        with c2:
            st.subheader("Language Logic")
            lang_p = supabase.table("language_prompts").select("*").execute()
            for lp in lang_p.data:
                with st.expander(f"Language: {lp['lang_code'].upper()}"):
                    new_f = st.text_area("Format Instructions", value=lp['formatting_instruction'], key=f"lp_{lp['id']}")
                    if st.button("Save", key=f"btn_lp_{lp['id']}"):
                        supabase.table("language_prompts").update({"formatting_instruction": new_f}).eq("id", lp['id']).execute()
                        st.success("Updated!")
