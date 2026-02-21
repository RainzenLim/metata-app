import json, io
from google.genai import types
from pymarc import Record, Field, Subfield  # Added Subfield import

def run_metadata_extraction(ai_client, supabase, img_bytes, filename, user_is_paid):
    try:
        # 1. FETCH DYNAMIC MODELS
        scout_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", 'scout').single().execute()
        SCOUT_MODEL = scout_cfg.data['model_id']
        
        tier = 'paid' if user_is_paid else 'free'
        ext_cfg = supabase.table("model_settings").select("model_id").eq("tier_name", tier).single().execute()
        EXT_MODEL = ext_cfg.data['model_id']

        # FETCH VALID KEYS
        item_keys = supabase.table("item_prompts").select("label").execute()
        lang_keys = supabase.table("language_prompts").select("lang_code").execute()
        valid_labels = [item['label'] for item in item_keys.data]
        valid_langs = [l['lang_code'] for l in lang_keys.data]

        # 2. STEP 1: DISCOVERY
        router_p = f"Identify the item. Return ONLY JSON: {{'label': '{valid_labels}', 'lang': '{valid_langs}', 'is_valid': bool}}"
        res1 = ai_client.models.generate_content(
            model=SCOUT_MODEL, 
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), router_p]
        )
        discovery = json.loads(res1.text.strip().replace('```json', '').replace('```', ''))

        if not discovery.get('is_valid'):
            return {"error": "Item not recognized as a library category."}

        # 3. MODULAR PROMPT FETCH
        task = supabase.table("item_prompts").select("prompt_text").eq("label", discovery['label']).single().execute()
        lang = supabase.table("language_prompts").select("formatting_instruction").eq("lang_code", discovery['lang']).single().execute()
        
        # 4. STEP 2: EXTRACTION (MARC JSON FOCUS)
        final_p = f"{task.data['prompt_text']} {lang.data['formatting_instruction']} Output MUST be MARC 21 JSON tags."
        res2 = ai_client.models.generate_content(
            model=EXT_MODEL,
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), final_p]
        )
        
        meta = json.loads(res2.text.strip().replace('```json', '').replace('```', ''))
        meta['_filename'] = filename # Internal tracking
        return meta
    except Exception as e:
        return {"error": str(e)}

def convert_llm_json_to_marc(llm_results):
    """
    Converts LLM JSON to binary MARC21.
    Fixed for pymarc v5+ using Subfield objects.
    """
    memory_file = io.BytesIO()
    
    for entry in llm_results:
        record = Record()
        
        for tag, data in entry.items():
            # Skip metadata keys (like '_filename')
            if not tag.isdigit():
                continue
            
            try:
                subfields_list = []
                
                # Case A: LLM gave nested subfields {"a": "Title", "c": "Author"}
                if isinstance(data, dict):
                    for code, val in data.items():
                        # Create a Subfield object for each entry
                        subfields_list.append(Subfield(code=code, value=str(val)))
                
                # Case B: LLM gave a simple string "Title"
                else:
                    subfields_list.append(Subfield(code='a', value=str(data)))

                # Add the field to the record using the new list of Subfield objects
                record.add_ordered_field(
                    Field(
                        tag=tag,
                        indicators=[' ', ' '],
                        subfields=subfields_list
                    )
                )
            except Exception as e:
                print(f"Skipping tag {tag} due to error: {e}")

        memory_file.write(record.as_marc())
    
    return memory_file.getvalue()

