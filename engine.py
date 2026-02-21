import json
from google.genai import types

def run_metadata_extraction(ai_client, supabase, img_bytes, filename, user_is_paid):
    try:
        # 1. FETCH DYNAMIC MODELS
        scout_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", 'scout').single().execute()
        SCOUT_MODEL = scout_cfg.data['model_id']
        
        tier = 'paid' if user_is_paid else 'free'
        ext_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", tier).single().execute()
        EXT_MODEL = ext_cfg.data['model_id']

        # --- NEW: FETCH VALID LABELS AND LANGUAGES FROM DB ---
        item_keys = supabase.table("item_prompts").select("label").execute()
        lang_keys = supabase.table("language_prompts").select("lang_code").execute()
        
        valid_labels = [item['label'] for item in item_keys.data]
        valid_langs = [l['lang_code'] for l in lang_keys.data]

        # 2. STEP 1: DISCOVERY (Dynamic Router)
        # We tell the AI exactly which keys are allowed based on your DB rows
        router_p = f"""
        Identify the item in this image. 
        Return ONLY JSON: 
        {{
            "label": "Choose one from: {valid_labels}", 
            "lang": "Choose one from: {valid_langs}", 
            "is_valid": bool
        }}
        If the item doesn't match a label, set is_valid to false.
        """
        
        res1 = ai_client.models.generate_content(
            model=SCOUT_MODEL, 
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), router_p]
        )
        
        # Robust JSON extraction
        clean_text = res1.text.strip().replace('```json', '').replace('```', '')
        discovery = json.loads(clean_text)

        if not discovery.get('is_valid'):
            return {"error": f"AI determined item is invalid for labels: {valid_labels}", "filename": filename}
        
        print(discovery)
        
        # 3. MODULAR PROMPT FETCH (Based on AI's choice)
        task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
        lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
        
        # 4. STEP 2: EXTRACTION
        final_p = f"{task.data['prompt_text']} {lang.data['formatting_instruction']}"
        res2 = ai_client.models.generate_content(
            model=EXT_MODEL,
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), final_p]
        )
        
        meta = json.loads(res2.text.strip().replace('```json', '').replace('```', ''))
        meta['engine_scout'] = SCOUT_MODEL
        meta['engine_ext'] = EXT_MODEL
        meta['detected_label'] = discovery['label']
        return meta

    except Exception as e:
        return {"error": str(e), "filename": filename}




