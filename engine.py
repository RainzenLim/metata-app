import json
from google.genai import types

def run_metadata_extraction(ai_client, supabase, img_bytes, filename, user_is_paid):
    try:
        # 1. FETCH DYNAMIC MODELS
        # Fetch the 'Scout' (Router) model
        scout_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", 'scout').single().execute()
        SCOUT_MODEL = scout_cfg.data['model_id']

        # Fetch the 'Librarian' (Extraction) model based on user tier
        tier = 'paid' if user_is_paid else 'free'
        ext_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", tier).single().execute()
        EXT_MODEL = ext_cfg.data['model_id']

        # 2. STEP 1: DISCOVERY (Using SCOUT_MODEL)
        router_p = "Identify: {'label': (modern_book/film_poster), 'lang': (en/zh/mi), 'is_valid': bool}. JSON only."
        res1 = ai_client.models.generate_content(
            model=SCOUT_MODEL, 
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), router_p]
        )
        discovery = json.loads(res1.text.strip().replace('```json', '').replace('```', ''))

        if not discovery.get('is_valid'):
            return {"error": "Invalid library item", "filename": filename}

        # 3. MODULAR PROMPT FETCH
        task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
        lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
        
        # 4. STEP 2: EXTRACTION (Using EXT_MODEL)
        final_p = f"{task.data['prompt_text']} {lang.data['formatting_instruction']}"
        res2 = ai_client.models.generate_content(
            model=EXT_MODEL,
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), final_p]
        )
        
        meta = json.loads(res2.text.strip().replace('```json', '').replace('```', ''))
        meta['scout_engine'] = SCOUT_MODEL
        meta['extraction_engine'] = EXT_MODEL
        return meta

    except Exception as e:
        return {"error": str(e)}
