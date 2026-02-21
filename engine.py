import json, io
from google.genai import types
from pymarc import Record, Field, Subfield # Updated for pymarc v5+

# --- STEP 1: THE SCOUT ---
def run_scout_discovery(ai_client, supabase, img_bytes):
    """
    Identifies the item type and language from the database keys.
    Returns the discovery JSON for the UI to display.
    """
    try:
        # 1. Fetch Dynamic Scout Model
        scout_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", 'scout').single().execute()
        SCOUT_MODEL = scout_cfg.data['model_id']
        
        # 2. Fetch valid keys from DB to guide the AI
        item_keys = supabase.table("item_prompts").select("label").execute()
        lang_keys = supabase.table("language_prompts").select("lang_code").execute()
        
        valid_labels = [item['label'] for item in item_keys.data]
        valid_langs = [l['lang_code'] for l in lang_keys.data]

        # 3. Call Scout
        router_p = f"""
        Identify the item. Return ONLY JSON: 
        {{
            "label": "Choose from: {valid_labels}", 
            "lang": "Choose from: {valid_langs}", 
            "is_valid": bool
        }}
        """
        res1 = ai_client.models.generate_content(
            model=SCOUT_MODEL, 
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), router_p]
        )
        
        discovery = json.loads(res1.text.strip().replace('```json', '').replace('```', ''))
        return discovery
    except Exception as e:
        return {"error": str(e)}

# --- STEP 2: THE LIBRARIAN ---
def run_deep_extraction(ai_client, supabase, img_bytes, discovery, user_is_paid):
    """
    Uses the labels from Step 1 to fetch the correct modular prompts.
    """
    try:
        # 1. Model Selection
        tier = 'paid' if user_is_paid else 'free'
        ext_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", tier).single().execute()
        EXT_MODEL = ext_cfg.data['model_id']

        # 2. Prompt Fetching
        task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
        lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
        
        # 3. Final Deep Extraction
        final_p = f"{task.data['prompt_text']} {lang.data['formatting_instruction']} Output MUST be MARC 21 JSON tags."
        res2 = ai_client.models.generate_content(
            model=EXT_MODEL,
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), final_p]
        )
        
        return json.loads(res2.text.strip().replace('```json', '').replace('```', ''))
    except Exception as e:
        return {"error": str(e)}

# --- UTILITY: MARC CONVERTER ---
def convert_llm_json_to_marc(llm_results):
    """
    Converts LLM JSON to binary MARC21.
    Uses Subfield objects to satisfy pymarc v5+ requirements.
    """
    memory_file = io.BytesIO()
    for entry in llm_results:
        record = Record()
        for tag, data in entry.items():
            if tag.isdigit():
                subfields_list = []
                if isinstance(data, dict):
                    for k, v in data.items():
                        subfields_list.append(Subfield(code=str(k), value=str(v)))
                else:
                    subfields_list.append(Subfield(code='a', value=str(data)))
                
                record.add_ordered_field(
                    Field(tag=tag, indicators=['0','0'], subfields=subfields_list)
                )
        memory_file.write(record.as_marc())
    return memory_file.getvalue()
