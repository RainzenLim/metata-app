import streamlit as st
import os, json, requests, io
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types
from PIL import Image

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Metata AI Pro", page_icon="📚", layout="wide")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- 2. AUTHENTICATION (Simplified) ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("Metata | Library Access")
    # ... [Login/Signup Logic remains the same] ...
    st.stop()

# Permissions
prof_res = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute()
user_data = prof_res.data[0] if prof_res.data else {"is_paid": False}
is_paid = user_data.get('is_paid', False)

# --- 3. MAIN INTERFACE ---
tab_batch, tab_history = st.tabs(["🚀 New Batch", "📜 Scan History"])

with tab_batch:
    st.title("Metata Modular Engine")
    # Paywall: Paid users get Pro for the extraction step
    EXTRACTION_MODEL = "gemini-2.5-pro" if is_paid else "gemini-2.5-pro"
    
    col1, col2 = st.columns(2)
    with col1:
        files = st.file_uploader("📁 Upload Images", accept_multiple_files=True, type=['jpg','png','jpeg'])
    with col2:
        url_input = st.text_input("🌐 Image URLs", placeholder="URL1 | URL2")

    # 4. PREVIEW & ROTATION LOGIC
    raw_queue = [{"name": f.name, "source": f, "is_url": False} for f in (files[:3] if files else [])]
    urls = [u.strip() for u in url_input.split("|") if u.strip()][:3]
    for u in urls: raw_queue.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    ready_for_ai = []
    if raw_queue:
        st.divider()
        st.subheader("🖼️ Preview & Manual Orientation")
        grid_cols = st.columns(len(raw_queue))
        
        for i, item in enumerate(raw_queue):
            with grid_cols[i]:
                try:
                    img_data = requests.get(item['source']).content if item['is_url'] else item['source'].getvalue()
                    pil_img = Image.open(io.BytesIO(img_data))
                    
                    # User-controlled rotation
                    m_rot = st.selectbox(f"Rotate {item['name']}", [0, 90, 180, 270], key=f"rot_{i}")
                    if m_rot != 0: pil_img = pil_img.rotate(-m_rot, expand=True)
                    st.image(pil_img, use_container_width=True)
                    
                    # Convert to bytes for AI
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG")
                    ready_for_ai.append({"name": item['name'], "bytes": buf.getvalue()})
                except: st.error(f"Error loading {item['name']}")

    # 5. MODULAR ANALYSIS LOGIC
    if st.button("🚀 Run Analysis"):
        if not is_paid and len(ready_for_ai) > 1:
            st.error("Free Tier limit: 1 image per batch.")
            st.stop()

        if not ready_for_ai:
            st.warning("Please provide an image.")
        else:
            results = []
            for img in ready_for_ai:
                with st.status(f"Scanning {img['name']}...") as status:
                    try:
                        # AI Step 1: Discover (Router)
                        router_prompt = "Identify: {'label': (modern_book/film_poster), 'lang': (en/zh/mi), 'is_valid': bool}. JSON only."
                        res1 = ai_client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=[types.Part.from_bytes(data=img['bytes'], mime_type="image/jpeg"), router_prompt]
                        )
                        discovery = json.loads(res1.text.replace('```json', '').replace('```', ''))

                        if not discovery.get('is_valid'):
                            st.error(f"Skipped {img['name']}: Not a library item.")
                            continue

                        # Fetch Modular Prompts from Supabase
                        task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
                        lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
                        
                        # AI Step 2: Extraction (Using tiered model)
                        final_prompt = f"{task.data['prompt_text']} {lang.data['formatting_instruction']}"
                        res2 = ai_client.models.generate_content(
                            model=EXTRACTION_MODEL,
                            contents=[types.Part.from_bytes(data=img['bytes'], mime_type="image/jpeg"), final_prompt]
                        )
                        metadata = json.loads(res2.text.replace('```json', '').replace('```', ''))
                        metadata['source'] = img['name']
                        
                        # Save to History
                        supabase.table("catalog_history").insert({
                            "user_id": st.session_state.user.id,
                            "filename": img['name'],
                            "metadata": metadata
                        }).execute()
                        
                        results.append(metadata)
                        status.update(label=f"Done: {img['name']}", state="complete")

                    except Exception as e:
                        st.error(f"Error on {img['name']}: {e}")

            if results:
                st.divider()
                df = pd.DataFrame(results)
                st.dataframe(df)
                st.download_button("📥 Download Results (CSV)", df.to_csv(index=False), "metata_results.csv")


