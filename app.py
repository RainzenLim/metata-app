import streamlit as st
from PIL import Image
import io

# 1. Page Configuration
st.set_page_config(page_title="Metata AI", page_icon="📚")
st.title("Metata: AI Library Cataloging")
st.markdown("Upload a book cover to generate library metadata automatically.")

# 2. The Sidebar (Optional but looks professional)
st.sidebar.header("Settings")
model_type = st.sidebar.selectbox("Choose AI Model", ["Fast-Scan", "Deep-Analysis"])

# 3. Image Uploader
uploaded_file = st.file_uploader("Choose an image...", type=['jpg', 'jpeg', 'png'])

if uploaded_file is not None:
    # --- THIS PART DISPLAYS THE IMAGE ---
    # We display the image immediately after it's uploaded
    st.image(uploaded_file, caption='Uploaded Book Cover', use_container_width=True)
    
    # 4. Processing Button
    if st.button('Generate Metadata'):
        with st.spinner('AI is analyzing the image...'):
            # Convert to BytesIO for AI processing
            image_bytes = uploaded_file.getvalue()
            
            # --- SIMULATED AI RESULT ---
            # This is where your AI logic (Gemini/Ollama) would return data
            st.success("Metadata Extracted!")
            
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Title", value="The Great Gatsby")
                st.text_input("Author", value="F. Scott Fitzgerald")
            with col2:
                st.text_input("ISBN", value="978-0743273565")
                st.text_input("Language", value="English")