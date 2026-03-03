"""
DOMMx YAML Translator EN → PT-BR
POWER OPENAI VERSION

✔ preserve YAML layout
✔ batch translation
✔ persistent cache
✔ preserve acronyms
✔ skip cross_reference
✔ same filename output
"""


import os
import re
import sys
import json
from ruamel.yaml import YAML
from openai import OpenAI

from pathlib import Path

# =========================================================
# OpenAI config
# =========================================================

from dotenv import load_dotenv
load_dotenv()

client = OpenAI()


# =========================================================
# Todas linguagens que deseja
# =========================================================

PATCH_MODE = False

LANG = None
CACHE = {}

LANG_PROMPTS = {
    "it": "neutral corporate Italian",
    "pt": "neutral corporate Brazilian Portuguese",
    "es": "neutral corporate Spanish",
    "de": "neutral corporate German",
    "fr": "neutral corporate French"
}

# =========================================================
# BASE DIR / PATHS (alinhado com extract_theory.py)
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOMAINS_DIR = BASE_DIR / "data" / "domains"


# =============================
# CONFIG
# =============================

INPUT_FOLDER = DOMAINS_DIR / "us"  

OUTPUT_ROOT = BASE_DIR / "utils" / "yaml-translator" / "output"

CACHE_DIR = BASE_DIR / "utils" / "yaml-translator" / "_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

yaml = YAML()
yaml.preserve_quotes = True
yaml.allow_duplicate_keys = True

client = OpenAI()

ACRONYM_REGEX = re.compile(r"\b[A-Z0-9]{2,}\b")

# =============================
# CACHE
# =============================

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(CACHE, f, ensure_ascii=False, indent=2)

# =============================
# ACRONYM HANDLING
# =============================

def preserve_acronyms(text):
    acronyms = ACRONYM_REGEX.findall(text)
    mapping = {}

    for i, ac in enumerate(acronyms):
        token = f"__ACR{i}__"
        mapping[token] = ac
        text = text.replace(ac, token)

    return text, mapping

def restore_acronyms(text, mapping):
    for token, ac in mapping.items():
        text = text.replace(token, ac)
    return text

# =============================
# COLLECT STRINGS
# =============================

def collect_strings(obj, bucket=None):
    if bucket is None:
        bucket = set()

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "cross_reference":
                continue
            collect_strings(v, bucket)

    elif isinstance(obj, list):
        for x in obj:
            collect_strings(x, bucket)

    elif isinstance(obj, str):
        if obj.strip():
            bucket.add(obj)

    return bucket
    
    
def collect_json_strings(obj, bucket=None):

    if bucket is None:
        bucket = set()

    if isinstance(obj, dict):
        for v in obj.values():
            collect_json_strings(v, bucket)

    elif isinstance(obj, list):
        for x in obj:
            collect_json_strings(x, bucket)

    elif isinstance(obj, str):
        if obj.strip():
            bucket.add(obj)

    return bucket

# =============================
# JSON Translate
# =============================
    
def apply_json_translation(obj):

    if isinstance(obj, dict):
        return {k: apply_json_translation(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [apply_json_translation(x) for x in obj]

    if isinstance(obj, str):
        return CACHE.get(obj, obj)

    return obj    

# =============================
# OPENAI BATCH TRANSLATION
# =============================
def batch_translate(strings):

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    import time
    import json
    import re

    to_translate = [s for s in strings if s not in CACHE]

    if not to_translate:
        return

    print(f"OpenAI translating {len(to_translate)} strings...")

    # =====================================================
    # Intelligent batching
    # =====================================================

    if PATCH_MODE:
        MAX_CHARS = 25000
    else:
        MAX_CHARS = 60000

    chunks = []
    current_chunk = []
    current_size = 0

    for text in to_translate:
        size = len(text)

        if current_size + size > MAX_CHARS and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

        current_chunk.append(text)
        current_size += size

    if current_chunk:
        chunks.append(current_chunk)

    print(f"Total chunks: {len(chunks)}")

    # =====================================================
    # Thread-safe cache lock
    # =====================================================

    cache_lock = threading.Lock()

    # =====================================================
    # Worker function
    # =====================================================

    def process_chunk(i, chunk):

        idx = i + 1
        total = len(chunks)
        approx_chars = sum(len(x) for x in chunk)

        print(f"Sending chunk {idx}/{total} (~{approx_chars} chars)")

        prepared = []
        acronym_maps = []

        for text in chunk:
            t, m = preserve_acronyms(text)
            prepared.append(t)
            acronym_maps.append(m)

        target_lang = LANG_PROMPTS.get(LANG, "target language")

        # =====================================================
        # PATCH MODE → indexed mode
        # =====================================================

        if PATCH_MODE:

            numbered = []
            for n, txt in enumerate(prepared, 1):
                numbered.append(f"[{n}]\n{txt}")

            joined = "\n\n".join(numbered)

            prompt = f"""
Translate into {target_lang}.

Rules:
- preserve placeholders __ACR*
- preserve acronyms
- preserve governance terminology
- keep numbering exactly as provided
- do not remove or alter the [n] markers
- do not add commentary

Texts:
{joined}
"""

        # =====================================================
        # YAML MODE → JSON list mode
        # =====================================================

        else:

            prompt = f"""
Translate into {target_lang}.

Mandatory rules:
- do not translate placeholders __ACR*
- do not translate acronyms or proper names
- preserve data governance terminology
- do not alter formatting
- output must be a JSON list of strings in the same order

Strings:
{json.dumps(prepared, ensure_ascii=False)}
"""

        # =====================================================
        # Retry logic
        # =====================================================

        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional corporate translator."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0
                )
                break
            except Exception:
                print(f"Retry chunk {idx} ({attempt+1}/3)")
                time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"Failed chunk {idx} after retries")

        raw = response.choices[0].message.content.strip()

        print(f"Finished chunk {idx}/{total}")

        # =====================================================
        # PATCH parse
        # =====================================================

        if PATCH_MODE:

            pattern = r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)"
            matches = re.findall(pattern, raw, re.DOTALL)

            translated_map = {}

            for num, content in matches:
                translated_map[int(num)] = content.strip()

            translated = []
            for n in range(1, len(chunk) + 1):
                translated.append(translated_map.get(n, chunk[n - 1]))

        # =====================================================
        # YAML parse
        # =====================================================

        else:

            start = raw.find("[")
            end = raw.rfind("]")

            if start == -1 or end == -1:
                print("RAW RESPONSE:")
                print(raw)
                raise ValueError("No JSON array found")

            json_part = raw[start:end+1]
            translated = json.loads(json_part)

        # =====================================================
        # Safe cache write
        # =====================================================

        with cache_lock:
            for original, tr, m in zip(chunk, translated, acronym_maps):
                CACHE[original] = restore_acronyms(tr, m)

    # =====================================================
    # Parallel execution
    # =====================================================

    MAX_WORKERS = 4

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(process_chunk, i, chunk)
            for i, chunk in enumerate(chunks)
        ]

        for future in as_completed(futures):
            future.result()

    save_cache()

# =============================
# APPLY
# =============================

def apply_translation(obj):

    if isinstance(obj, dict):
        return {k:(v if k=="cross_reference" else apply_translation(v)) for k,v in obj.items()}

    if isinstance(obj, list):
        return [apply_translation(x) for x in obj]

    if isinstance(obj, str):
        return CACHE.get(obj, obj)

    return obj
    



def process_patch():

    print("Running PATCH mode")

    PATCH_INPUT_FOLDER = BASE_DIR / "utils" / "yaml-translator" / "input_en"

    files = [
        f for f in os.listdir(PATCH_INPUT_FOLDER)
        if f.endswith("_theory_demo_output_PATCHED.json")
    ]

    if not files:
        print("No PATCH files found.")
        return

    all_strings = set()
    docs = {}

    for f in files:
        with open(os.path.join(PATCH_INPUT_FOLDER, f), "r", encoding="utf-8") as fh:
            data = json.load(fh)

        docs[f] = data
        collect_json_strings(data, all_strings)

    print(f"Unique patch strings: {len(all_strings)}")

    batch_translate(all_strings)

    for f, data in docs.items():

        translated = apply_json_translation(data)

        with open(os.path.join(OUTPUT_FOLDER, f), "w", encoding="utf-8") as fh:
            json.dump(translated, fh, ensure_ascii=False, indent=2)

        print(f"Saved {f}")

    print("PATCH DONE")    

# =============================
# MAIN
# =============================

def process():

    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith(".yaml")]

    all_strings = set()
    docs = {}

    for f in files:
        with open(os.path.join(INPUT_FOLDER, f), "r", encoding="utf-8") as fh:
            data = yaml.load(fh)

        docs[f] = data
        collect_strings(data, all_strings)

    print(f"Unique strings: {len(all_strings)}")

    batch_translate(all_strings)

    for f, data in docs.items():
        translated = apply_translation(data)

        with open(os.path.join(OUTPUT_FOLDER, f), "w", encoding="utf-8") as fh:
            yaml.dump(translated, fh)

        print(f"Saved {f}")

    print("DONE")
    

# =============================
# RUN WITH CLI PARAM
# =============================

if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python translator.py <language> [--patch]")
        print("Example: python translator.py pt")
        print("Example: python translator.py pt --patch")
        print("Example: python translator.py all --patch")
        sys.exit(1)

    arg = sys.argv[1].lower()

    if "--patch" in sys.argv:
        PATCH_MODE = True

    # =============================
    # ALL LANGUAGES MODE
    # =============================

    if arg == "all":

        for lang in LANG_PROMPTS.keys():

            print(f"\n=== Processing {lang} ===")

            LANG = lang

            OUTPUT_FOLDER = OUTPUT_ROOT / LANG
            OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

            CACHE_FILE = CACHE_DIR / f"translation_{LANG}_cache.json"

            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    CACHE = json.load(f)
            else:
                CACHE = {}

            if PATCH_MODE:
                process_patch()
            else:
                process()

        print("\n=== ALL LANGUAGES COMPLETED ===")
        sys.exit(0)

    # =============================
    # SINGLE LANGUAGE MODE
    # =============================

    if arg not in LANG_PROMPTS:
        print(f"Unsupported language: {arg}")
        print("Available:", ", ".join(LANG_PROMPTS.keys()))
        sys.exit(1)

    LANG = arg

    OUTPUT_FOLDER = OUTPUT_ROOT / LANG
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    CACHE_FILE = CACHE_DIR / f"translation_{LANG}_cache.json"

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            CACHE = json.load(f)
    else:
        CACHE = {}

    if PATCH_MODE:
        process_patch()
    else:
        process()