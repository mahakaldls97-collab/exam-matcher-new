import os
import base64
import json
import re
import io
import time
import requests
import pypdfium2 as pdfium
from dotenv import load_dotenv

load_dotenv(override=True)

API_KEY  = os.getenv("GEMINI_API_KEY", "")
MODEL    = "gemini-3.1-flash-lite"
BASE_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL}:generateContent"
HEADERS  = {"x-goog-api-key": API_KEY, "Content-Type": "application/json"}

CHUNK_PROMPT = """You are an expert at parsing Indian competitive exam papers.
Extract ALL multiple-choice questions (MCQs) visible across these pages into a JSON array.

Return ONLY this JSON structure:
[
  {
    "q_no": "1",
    "question": "Hindi text\nEnglish text",
    "options": {
      "A": "...",
      "B": "...",
      "C": "...",
      "D": "...",
      "E": "..."
    }
  }
]

Rules:
1. BILINGUAL SUPPORT: If a question is in both Hindi and English, include BOTH in "question" separated by newline (\n).
2. If only Hindi, keep Hindi. If only English, keep English.
3. Keep all options (A, B, C, D, E).
4. Do NOT skip any questions on these pages.
"""

ANSWER_KEY_PROMPT = """You are an expert at parsing official exam answer keys.
Extract ALL question numbers and their corresponding official answers from this document.

Return ONLY this JSON:
{
  "type": "answers_only",
  "data": [
    {"q_no": "1", "correct_answer": "B"}
  ]
}

Rules:
- Extract all questions from question 1 to the last question.
- correct_answer should be A, B, C, D, or E (or Delete).
"""

def clean_json(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()

def get_mime_type(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
        "gif": "image/gif", "bmp": "image/bmp",
        "pdf": "application/pdf",
    }.get(ext, "application/octet-stream")

def call_gemini(parts: list, timeout: int = 70) -> str:
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }
    
    # Retry with exponential backoff if 429 occurs
    for attempt in range(4):
        r = requests.post(BASE_URL, headers=HEADERS, json=body, timeout=timeout)
        if r.status_code == 429:
            wait_time = 4 + attempt * 3
            print(f"Rate limited (429), waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            continue
        if r.status_code != 200:
            err = r.text[:250]
            try:
                err = r.json().get("error", {}).get("message", err)
            except Exception:
                pass
            raise ValueError(f"Gemini API error ({r.status_code}): {err}")

        res_json = r.json()
        candidates = res_json.get("candidates", [])
        if not candidates:
            raise ValueError("No response candidates from Gemini.")

        for p in candidates[0].get("content", {}).get("parts", []):
            if "text" in p and p["text"]:
                return p["text"]
        raise ValueError("Empty text response from Gemini.")

    raise ValueError("Gemini API rate limit exceeded after retries.")

def render_pages_to_jpegs(pdf, page_indices, scale: float = 1.0):
    parts = []
    for idx in page_indices:
        if idx >= len(pdf):
            continue
        bmp = pdf[idx].render(scale=scale)
        img = bmp.to_pil()
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65)
        enc = base64.b64encode(buf.getvalue()).decode()
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": enc}})
    return parts

async def extract_and_parse_paper(file_bytes: bytes, filename: str) -> list:
    if filename.lower().endswith(".pdf"):
        pdf = pdfium.PdfDocument(file_bytes)
        total_pages = len(pdf)
        print(f"Processing PDF ({filename}): {total_pages} pages.")

        if total_pages <= 4:
            chunks = [list(range(total_pages))]
        else:
            chunks = []
            chunk_size = 4
            # Start from page 1 if booklet has cover page (page 0)
            start_p = 1 if total_pages > 4 else 0
            for start in range(start_p, total_pages, chunk_size):
                chunks.append(list(range(start, min(start + chunk_size, total_pages))))

        all_questions = []
        for c_idx, chunk in enumerate(chunks):
            print(f"Extracting pages {chunk[0]+1} to {chunk[-1]+1} (Chunk {c_idx+1}/{len(chunks)})...")
            img_parts = render_pages_to_jpegs(pdf, chunk, scale=1.0)
            if not img_parts:
                continue
            img_parts.append({"text": CHUNK_PROMPT})
            try:
                raw = call_gemini(img_parts, timeout=75)
                items = json.loads(clean_json(raw))
                if isinstance(items, list):
                    all_questions.extend(items)
                elif isinstance(items, dict) and "questions" in items:
                    all_questions.extend(items["questions"])
            except Exception as e:
                print(f"Warning on chunk {chunk}: {e}")
            # Small pause between chunks to stay well within rate limits
            time.sleep(1.0)

        # Deduplicate and sort
        seen = set()
        unique = []
        for q in all_questions:
            qno_raw = str(q.get("q_no", "")).strip()
            qno = re.sub(r"[^\d]", "", qno_raw) or qno_raw
            if qno and qno not in seen:
                seen.add(qno)
                q["q_no"] = qno
                unique.append(q)

        def sort_key(item):
            try:
                return int(item["q_no"])
            except ValueError:
                return 9999

        unique.sort(key=sort_key)
        print(f"Finished: {len(unique)} questions extracted from {filename}.")
        return unique

    else:
        # Image file
        mime = get_mime_type(filename)
        enc = base64.b64encode(file_bytes).decode()
        parts = [
            {"inlineData": {"mimeType": mime, "data": enc}},
            {"text": CHUNK_PROMPT}
        ]
        raw = call_gemini(parts, timeout=75)
        items = json.loads(clean_json(raw))
        if isinstance(items, dict) and "questions" in items:
            items = items["questions"]
        return items if isinstance(items, list) else []

async def extract_and_parse_key(file_bytes: bytes, filename: str) -> dict:
    if filename.lower().endswith(".pdf"):
        pdf = pdfium.PdfDocument(file_bytes)
        img_parts = render_pages_to_jpegs(pdf, list(range(len(pdf))), scale=1.5)
        img_parts.append({"text": ANSWER_KEY_PROMPT})
        raw = call_gemini(img_parts, timeout=75)
    else:
        mime = get_mime_type(filename)
        enc = base64.b64encode(file_bytes).decode()
        raw = call_gemini([
            {"inlineData": {"mimeType": mime, "data": enc}},
            {"text": ANSWER_KEY_PROMPT}
        ], timeout=75)

    data = json.loads(clean_json(raw))
    if isinstance(data, list):
        data = {"type": "answers_only", "data": data}
    return data
