import streamlit as st
import os
import io
import base64
from PIL import Image

# Import AI Libraries
from google import genai
from google.genai import types
from groq import Groq
from openai import OpenAI

# 1. PAGE CONFIGURATION
st.set_page_config(page_title="Metata AI", page_icon="📚", layout="wide")

# 2. SIDEBAR - MODEL SELECTION & API KEYS
st.sidebar.title("Metata Control Panel")
engine = st.sidebar.selectbox("Select AI Engine", ["Gemini 2.0 Flash", "Groq (Llama 3.2)", "GPT-4o"])

# Helper function for Base64 (needed for OpenAI/Groq)
def to_base64(img_bytes):
    return base64.b64encode(img_bytes).decode('utf-8')

# 3. MAIN UI
st.title("Metata: Professional Library Cataloging")
st.write(f"Currently using: **{engine}**")

uploaded_file = st.file_uploader("Upload Book Cover or Title Page", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    # Display the image immediately
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Source Image")
        st.image(uploaded_file, use_container_width=True)
    
    with col2:
        st.subheader("Metadata Results")
        if st.button("Generate Catalog Entry"):
            img_bytes = uploaded_file.getvalue()
            prompt = "Extract book metadata: Title, Author, ISBN, Publisher, and Subject. Return as JSON."

            try:
                # --- ENGINE 1: GEMINI ---
                if "Gemini" in engine:
                    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), prompt]
                    )
                    st.json(response.text)

                # --- ENGINE 2: GROQ ---
                elif "Groq" in engine:
                    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                    b64_img = to_base64(img_bytes)
                    chat_completion = client.chat.completions.create(
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]}],
                        model="llama-3.2-11b-vision-preview",
                    )
                    st.write(chat_completion.choices[0].message.content)

                # --- ENGINE 3: OPENAI ---
                elif "GPT-4o" in engine:
                    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                    b64_img = to_base64(img_bytes)
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}]}],
                    )
                    st.write(response.choices[0].message.content)

            except Exception as e:
                st.error(f"Engine Error: {e}. Please check your API keys in Railway.")