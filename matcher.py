import json
import re
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

API_KEY  = os.getenv("GEMINI_API_KEY", "")
MODEL    = "gemini-3.1-flash-lite"
BASE_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL}:generateContent"
HEADERS  = {"x-goog-api-key": API_KEY, "Content-Type": "application/json"}

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
    r = requests.post(BASE_URL, headers=HEADERS, json=body, timeout=75)
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

async def match_two_series(paper_a: list, paper_b: list, key_map: dict = None) -> list:
    """
    Matches Series A questions with Series D / Master Paper questions.
    Returns matched table with Series A Q.No, Question, Series D Q.No, and Answer.
    """
    if key_map is None:
        key_map = {}

    batch_size = 30
    all_matches = []

    # Map paper B by q_no for fast lookup
    b_map = {str(q.get("q_no")): q for q in paper_b}

    for i in range(0, len(paper_a), batch_size):
        chunk_a = paper_a[i:i + batch_size]
        a_repr = json.dumps(
            [{"no": str(q["q_no"]), "q": str(q.get("question", ""))[:180]} for q in chunk_a],
            ensure_ascii=False
        )
        b_repr = json.dumps(
            [{"no": str(q["q_no"]), "q": str(q.get("question", ""))[:180]} for q in paper_b],
            ensure_ascii=False
        )

        prompt = f"""You are matching questions between two different sets/series of the same exam.
PAPER 1 (SERIES A): {a_repr}
PAPER 2 (SERIES D / MASTER): {b_repr}

Match each question of Paper 1 to the corresponding question in Paper 2 based on question meaning/content (in Hindi or English).

Return a JSON array:
[
  {{"paper_a_q_no": "1", "matched_b_q_no": "14"}}
]
If no match is found, set matched_b_q_no to null.
"""
        try:
            raw = _call_gemini(prompt)
            matches = json.loads(_clean_json(raw))
            if isinstance(matches, list):
                all_matches.extend(matches)
        except Exception as e:
            print(f"Match chunk error: {e}")
            for q in chunk_a:
                all_matches.append({"paper_a_q_no": str(q["q_no"]), "matched_b_q_no": None})

    # Build final mapped list
    match_lookup = {str(m.get("paper_a_q_no")): m.get("matched_b_q_no") for m in all_matches}
    results = []
    for q in paper_a:
        qno_a = str(q.get("q_no"))
        qno_b = match_lookup.get(qno_a)
        
        # Get correct answer from answer key (keyed by series D or series A)
        ans = key_map.get(str(qno_b)) or key_map.get(str(qno_a)) or "?"
        
        results.append({
            "series_a_q_no": qno_a,
            "question": q.get("question", ""),
            "options": q.get("options", {}),
            "series_b_q_no": qno_b or "—",
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

async def match_questions(paper_questions: list, key_data: dict) -> list:
    key_items = key_data.get("data", [])
    key_answer_map = {str(item["q_no"]): (item.get("correct_answer") or "").upper() for item in key_items}

    return [
        {
            "paper_q_no": str(q["q_no"]),
            "key_q_no": str(q["q_no"]),
            "correct_answer": key_answer_map.get(str(q["q_no"])),
            "matched_by": "direct"
        }
        for q in paper_questions
    ]
