import json, io
from google.genai import types
from pymarc import Record, Field, Subfield 

def clean_json_output(raw_text):
    """Ensures AI output is a dictionary, even if returned as a list."""
    try:
        data = json.loads(raw_text.strip().replace('```json', '').replace('```', ''))
        if isinstance(data, list):
            return data[0] if data else {}
        return data
    except:
        return {"error": "Invalid JSON format"}

def run_metadata_extraction(ai_client, supabase, img_bytes, filename, user_is_paid):
    """
    Runs Scout Discovery and Deep Extraction.
    Returns a tuple: (discovery_dict, metadata_dict)
    """
    try:
        # --- STEP 1: SCOUT DISCOVERY ---
        scout_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", 'scout').single().execute()
        item_keys = supabase.table("item_prompts").select("label").execute()
        lang_keys = supabase.table("language_prompts").select("lang_code").execute()
        
        valid_labels = [item['label'] for item in item_keys.data]
        valid_langs = [l['lang_code'] for l in lang_keys.data]

        router_p = f"Identify: {{'label': {valid_labels}, 'lang': {valid_langs}, 'is_valid': bool}}. JSON only."
        
        res1 = ai_client.models.generate_content(
            model=scout_cfg.data['model_id'], 
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), router_p]
        )
        discovery = clean_json_output(res1.text)

        if not discovery.get('is_valid', False):
            return discovery, {"error": "Item rejected by Scout."}

        # --- STEP 2: DEEP EXTRACTION ---
        tier = 'paid' if user_is_paid else 'free'
        ext_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", tier).single().execute()
        
        task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
        lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
        
        final_p = f"{task.data['prompt_text']} {lang.data['formatting_instruction']} Output MUST be MARC 21 JSON tags."
        
        res2 = ai_client.models.generate_content(
            model=ext_cfg.data['model_id'],
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), final_p]
        )
        
        meta = clean_json_output(res2.text)
        return discovery, meta

    except Exception as e:
        return {"error": "Discovery failed"}, {"error": str(e)}

def convert_llm_json_to_marc(llm_results):
    """Converts a list of dicts to binary MARC21 (pymarc v5+ style)"""
    memory_file = io.BytesIO()
    for entry in llm_results:
        record = Record()
        for tag, data in entry.items():
            if tag.isdigit():
                subfields = []
                if isinstance(data, dict):
                    for k, v in data.items():
                        subfields.append(Subfield(code=str(k), value=str(v)))
                else:
                    subfields.append(Subfield(code='a', value=str(data)))
                record.add_ordered_field(Field(tag=tag, indicators=['0','0'], subfields=subfields))
        memory_file.write(record.as_marc())
    return memory_file.getvalue()
