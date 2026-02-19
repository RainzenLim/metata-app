import streamlit as st
import os, json, requests, io
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types
from pymarc import Record, Field

# --- 1. INITIALIZATION ---
# These must be set in Railway's "Variables" tab
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

st.set_page_config(page_title="Metata AI", page_icon="📚", layout="wide")

# --- 2. UTILITY FUNCTIONS ---
def generate_marc(data):
    """Maps JSON keys to MARC 21 tags."""
    record = Record()
    mapping = {'title': '245', 'author': '100', 'isbn': '020'}
    for key, tag in mapping.items():
        if data.get(key):
            record.add_ordered_field(Field(tag=tag, indicators=['1','0'], subfields=['a', str(data[key])]))
    return record.as_marc()

def get_image_bytes(source, is_url=False):
    """Standardizes input into bytes for the AI."""
    if is_url:
        res = requests.get(source, timeout=10)
        return res.content
    return source.getvalue()

# --- 3. UI LAYOUT ---
st.title("Metata: Professional Library Intelligence")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.subheader("📁 File Uploads (Max 3)")
    uploaded_files = st.file_uploader("Drop images here", accept_multiple_files=True, type=['jpg','png','jpeg'])
    files = uploaded_files[:3] if uploaded_files else []

with col2:
    st.subheader("🌐 Image URLs (Max 3)")
    url_input = st.text_input("Paste links separated by '|'", placeholder="url1 | url2 | url3")
    urls = [u.strip() for u in url_input.split("|") if u.strip()][:3] if url_input else []

# --- 4. THE BATCH ENGINE ---
if st.button("🚀 Run Batch Analysis"):
    batch_queue = []
    for f in files: batch_queue.append({"name": f.name, "source": f, "is_url": False})
    for u in urls: batch_queue.append({"name": u.split('/')[-1], "source": u, "is_url": True})

    if not batch_queue:
        st.warning("Please provide at least one image or URL.")
    else:
        results_list = []
        for item in batch_queue:
            with st.status(f"Analyzing {item['name']}...", expanded=True) as status:
                try:
                    img_data = get_image_bytes(item['source'], item['is_url'])
                    
                    # CALL 1: DISCOVERY (Type, Language, & Validation)
                    router_prompt = "Identify: {'label': (modern_book/film_poster), 'lang': (en/zh/es/fr), 'is_valid': bool}. Return JSON."
                    res1 = ai_client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[types.Part.from_bytes(data=img_data, mime_type="image/jpeg"), router_prompt]
                    )
                    
                    discovery = json.loads(res1.text.replace('```json', '').replace('```', ''))
                    
                    if not discovery.get('is_valid'):
                        st.error(f"❌ {item['name']} is not a library item.")
                        continue

                    # DATABASE STITCHING
                    label, lang = discovery['label'], discovery['lang']
                    task = supabase.table("item_prompts").select("prompt_text").eq("label", label).single().execute()
                    lang_instr = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", lang).single().execute()
                    
                    combined_prompt = f"{task.data['prompt_text']} {lang_instr.data['formatting_instruction']}"
                    
                    # CALL 2: DEEP EXTRACTION
                    res2 = ai_client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[types.Part.from_bytes(data=img_data, mime_type="image/jpeg"), combined_prompt]
                    )
                    
                    metadata = json.loads(res2.text.replace('```json', '').replace('```', ''))
                    metadata.update({'item_type': label, 'language': lang, 'filename': item['name']})
                    results_list.append(metadata)
                    
                    status.update(label=f"Completed: {item['name']}", state="complete")
                    
                except Exception as e:
                    st.error(f"Error processing {item['name']}: {e}")

        # --- 5. EXPORT SECTION ---
        if results_list:
            st.divider()
            df = pd.DataFrame(results_list)
            st.dataframe(df)

            ex1, ex2 = st.columns(2)
            with ex1:
                st.download_button("📥 CSV Export", df.to_csv(index=False), "metata_batch.csv", "text/csv")
            with ex2:
                marc_binary = b"".join([generate_marc(row) for row in results_list])
                st.download_button("📥 MARC Export (.mrc)", marc_binary, "metata_records.mrc", "application/marc")