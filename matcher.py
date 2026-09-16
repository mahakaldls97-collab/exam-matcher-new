import json
import re
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

MODEL = "gemini-3.1-flash-lite"
BASE_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL}:generateContent"

def get_headers():
    return {
        "x-goog-api-key": os.getenv("GEMINI_API_KEY", ""),
        "Content-Type": "application/json"
    }

def _clean_json(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()

def _call_gemini(prompt: str) -> str:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }
    r = requests.post(BASE_URL, headers=get_headers(), json=body, timeout=75)
    if r.status_code != 200:
        err = r.text[:200]
        try:
            err = r.json().get("error", {}).get("message", err)
        except Exception:
            pass
        raise ValueError(f"Gemini API error ({r.status_code}): {err}")

    res_json = r.json()
    candidates = res_json.get("candidates", [])
    if candidates:
        for p in candidates[0].get("content", {}).get("parts", []):
            if "text" in p and p["text"]:
                return p["text"]
    raise ValueError("Empty response from AI matcher.")

def get_q_num(q: dict) -> str:
    val = q.get("q_no") or q.get("question_number") or q.get("no") or ""
    return str(val).strip()

def get_q_text(q: dict) -> str:
    return str(q.get("question") or q.get("question_text") or "").strip()

def match_questions(paper_questions: list, key_text_or_data) -> dict:
    """Parses answer key into a mapping of q_num -> correct_option"""
    key_map = {}
    if isinstance(key_text_or_data, str):
        # Parse lines like "1: A" or "1. A" or "1 - A"
        for line in key_text_or_data.splitlines():
            line = line.strip()
            m = re.search(r"(\d+)\s*[:\.\-\s]\s*([A-Ea-e\*]|Delete)", line)
            if m:
                key_map[str(m.group(1))] = m.group(2).upper()
    elif isinstance(key_text_or_data, dict):
        items = key_text_or_data.get("data", [])
        for it in items:
            q_num = it.get("q_no") or it.get("question_number")
            if q_num:
                key_map[str(q_num)] = str(it.get("correct_answer", "")).upper()
    return key_map

def match_two_series(paper_a: list, paper_b: list, key_map: dict = None) -> list:
    """Matches Series A questions with Series D/Master questions."""
    if key_map is None:
        key_map = {}

    batch_size = 30
    all_matches = []

    for i in range(0, len(paper_a), batch_size):
        chunk_a = paper_a[i:i + batch_size]
        a_repr = json.dumps(
            [{"no": get_q_num(q), "q": get_q_text(q)[:180]} for q in chunk_a],
            ensure_ascii=False
        )
        b_repr = json.dumps(
            [{"no": get_q_num(q), "q": get_q_text(q)[:180]} for q in paper_b],
            ensure_ascii=False
        )

        prompt = f"""You are matching questions between two different series/sets of an exam.
PAPER 1: {a_repr}
PAPER 2: {b_repr}

Match each question of Paper 1 to the corresponding question in Paper 2 based on question meaning (Hindi or English).
Return JSON array:
[
  {{"paper_a_q_no": "1", "matched_b_q_no": "14"}}
]
If no match found, set matched_b_q_no to null.
"""
        try:
            raw = _call_gemini(prompt)
            matches = json.loads(_clean_json(raw))
            if isinstance(matches, list):
                all_matches.extend(matches)
        except Exception as e:
            print(f"Match chunk error: {e}")
            for q in chunk_a:
                all_matches.append({"paper_a_q_no": get_q_num(q), "matched_b_q_no": None})

    match_lookup = {str(m.get("paper_a_q_no")): m.get("matched_b_q_no") for m in all_matches}
    results = []

    for q in paper_a:
        qno_a = get_q_num(q)
        qno_b = match_lookup.get(qno_a)
        
        # Get answer from answer key (keyed by series D or series A)
        ans = key_map.get(str(qno_b)) or key_map.get(str(qno_a)) or "?"
        
        results.append({
            "series_a_q_no": qno_a,
            "question": get_q_text(q),
            "options": q.get("options", {}),
            "series_b_q_no": str(qno_b) if qno_b else "—",
            "correct_answer": ans,
            "matched_by": "ai" if qno_b else "direct"
        })

    def sort_key(item):
        try:
            return int(item["series_a_q_no"])
        except ValueError:
            return 9999

    results.sort(key=sort_key)
    return results
