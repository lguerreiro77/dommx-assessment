# theory_detail.py
# Ultra optimized DOMMx theory enrichment

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI
from PyPDF2 import PdfReader

# =========================================================
# CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
THEORY_DIR = BASE_DIR / "data" / "global" / "theory"
PDF_DIR = THEORY_DIR / "PDFs"

THEORY_INDEX_PATH = THEORY_DIR / "theory_index.json"
THEORY_DETAIL_PATH = THEORY_DIR / "theory_detail.json"

load_dotenv(BASE_DIR / ".env")
client = OpenAI()

import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

MAX_WORKERS = 4  # para API externa nao pode ser muito

# =========================================================
# HELPERS
# =========================================================

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip())

def detect_framework(text):
    t = text.upper()
    if "DCAM" in t: return "DCAM"
    if "CMMI" in t: return "CMMI"
    if "GDPR" in t: return "GDPR"
    if "IDGC" in t: return "IDGC"
    if "DMBOK" in t or "DAMA" in t: return "DAMA"
    return "OTHER"

# =========================================================
# LOAD PDF TEXT CACHE
# =========================================================

_pdf_cache = {}

def load_pdf(framework):
    if framework in _pdf_cache:
        return _pdf_cache[framework]

    path = PDF_DIR / f"{framework}.pdf"
    if not path.exists():
        return None

    reader = PdfReader(str(path))
    text = "\n".join([p.extract_text() or "" for p in reader.pages])
    _pdf_cache[framework] = text
    return text

# =========================================================
# COLLECT DISTINCT SUBJECTS
# =========================================================

def collect_subjects(index_data):
    subjects = {}

    for domain in index_data.values():
        for q in domain.get("questions", {}).values():
            for score in q.get("score_action_mapping", {}).values():

                theory = score.get("theory", {})
                cross = theory.get("decision_tree_cross_reference", [])

                for ref in cross:
                    if isinstance(ref, dict):
                        ref_text = ref.get("reference")
                    else:
                        ref_text = ref

                    if not ref_text:
                        continue

                    ref_norm = normalize(ref_text)
                    fw = detect_framework(ref_norm)
                    subjects.setdefault(fw, set()).add(ref_norm)

                for p in score.get("procedures", {}).values():
                    t = p.get("theory", {})
                    for field in ("recommendations_subject", "notes_subject"):
                        val = t.get(field)
                        if val:
                            val = normalize(val)
                            fw = detect_framework(val)
                            subjects.setdefault(fw, set()).add(val)

    return subjects

# =========================================================
# GPT BATCH PER FRAMEWORK
# =========================================================

import time
import json
import re
from openai import APITimeoutError

MAX_RETRIES = 3
MAX_BATCH_SIZE = 50


def call_gpt_batch(framework, topics, pdf_text):

    # -----------------------------
    # HARD LIMIT BATCH SIZE
    # -----------------------------
    if len(topics) > MAX_BATCH_SIZE:
        results = {}
        for i in range(0, len(topics), MAX_BATCH_SIZE):
            chunk = topics[i:i + MAX_BATCH_SIZE]
            chunk_result = call_gpt_batch(framework, chunk, pdf_text)
            results.update(chunk_result)
        return results

    joined_topics = "\n".join(f"- {t}" for t in topics)

    context = ""
    if pdf_text:
        context = pdf_text[:1500]

    prompt = f"""
Framework: {framework}

Topics:
{joined_topics}

Return ONLY valid JSON.
No explanations.
No commentary.
No markdown.
No code blocks.
Strict JSON format:

{{ "topic": "summary" }}

If unsure, still return valid JSON.
"""

    if context:
        prompt += f"\n\nContext:\n{context}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"→ {framework} attempt {attempt} ({len(topics)} topics)", flush=True)

            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                timeout=90,
                messages=[
                    {
                        "role": "system",
                        "content": "Return ONLY valid JSON. No explanations. No extra text. Strict JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    },
                ],
            )

            raw = resp.choices[0].message.content.strip()

            # -----------------------------
            # SAFE JSON PARSE
            # -----------------------------
            try:
                return json.loads(raw)
            except:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group())
                    except:
                        pass

            print("⚠ Invalid JSON returned. Retrying...", flush=True)

        except APITimeoutError:
            print(f"⚠ Timeout on {framework} attempt {attempt}", flush=True)

        except Exception as e:
            print(f"⚠ Error on {framework} attempt {attempt}: {e}", flush=True)

        time.sleep(2 * attempt)

    # If still failing
    print(f"❌ Skipping batch for {framework}", flush=True)
    return {}
    

def summarize_framework_batch(framework, topics, pdf_text):
    if not topics:
        return {}

    return call_gpt_batch(framework, topics, pdf_text)

# =========================================================
# MAIN
# =========================================================

def generate():

    with open(THEORY_INDEX_PATH, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    subjects_by_fw = collect_subjects(index_data)

    total_topics = sum(len(v) for v in subjects_by_fw.values())
    print(f"Total DISTINCT topics: {total_topics}")

    enriched = {}
    processed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        futures = {}

        for fw, topics in subjects_by_fw.items():
            pdf_text = load_pdf(fw)
            futures[executor.submit(
                summarize_framework_batch,
                fw,
                list(topics),
                pdf_text
            )] = fw
            print(f"Starting framework {fw} with {len(topics)} topics", flush=True)

        try:
            for future in as_completed(futures):
                fw = futures[future]
                print(f"Finished GPT batch for {fw}", flush=True)

                result = future.result()

                for topic, summary in result.items():
                    theory_key = f"{fw}|{normalize(topic)}"

                    enriched[theory_key] = {
                        "theory_key": theory_key,
                        "framework": fw,
                        "summary_for_audit": summary
                    }

                    processed += 1
                    if processed % 10 == 0 or processed == total_topics:
                        pct = int((processed / total_topics) * 100)
                        print(f"[{pct:3}%]  {processed}/{total_topics} processed", flush=True)

        except KeyboardInterrupt:
            print("\n⛔ Interrupted by user. Cancelling tasks...", flush=True)
            executor.shutdown(wait=False, cancel_futures=True)
            raise

            for topic, summary in result.items():
                theory_key = f"{fw}|{normalize(topic)}"

                enriched[theory_key] = {
                    "theory_key": theory_key,
                    "framework": fw,
                    "summary_for_audit": summary
                }

                processed += 1
                pct = int((processed / total_topics) * 100)
                if processed % 5 == 0 or processed == total_topics:
                    pct = int((processed / total_topics) * 100)
                    print(f"[{pct:3}%]  {processed}/{total_topics} processed", flush=True)

    # rebuild tree
    final = {}

    for domain_id, domain in index_data.items():
        final[domain_id] = {"questions": {}}

        for q_id, q in domain.get("questions", {}).items():
            out_q = {
                "cross_reference": {},
                "score_action_mapping": {}
            }

            for score_lvl, score in q.get("score_action_mapping", {}).items():

                out_score = {
                    "action_code": score.get("action_code"),
                    "procedures": {}
                }

                theory = score.get("theory", {})
                cross = theory.get("decision_tree_cross_reference", [])

                for ref in cross:

                    if isinstance(ref, dict):
                        ref_text = ref.get("reference")
                        theory_key = ref.get("theory_key")
                    else:
                        ref_text = ref
                        fw = detect_framework(ref_text)
                        theory_key = f"{fw}|{normalize(ref_text)}"

                    if theory_key in enriched:
                        fw = detect_framework(ref_text)
                        out_q["cross_reference"].setdefault(fw, {})
                        out_q["cross_reference"][fw][ref_text] = enriched[theory_key]

                for p_id, p in score.get("procedures", {}).items():
                    out_proc = {}
                    t = p.get("theory", {})

                    for field in ("recommendations_subject", "notes_subject"):
                        val = t.get(field)
                        if val:
                            fw = detect_framework(val)
                            key = f"{fw}|{normalize(val)}"
                            if key in enriched:
                                out_proc[field] = enriched[key]

                    out_score["procedures"][p_id] = out_proc

                out_q["score_action_mapping"][score_lvl] = out_score

            final[domain_id]["questions"][q_id] = out_q

    with open(THEORY_DETAIL_PATH, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)

    print("\nDone.")


if __name__ == "__main__":
    generate()