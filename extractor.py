import os
import io
import time
import base64
import json
import requests
from pypdfium2 import PdfDocument
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "gemini-3.1-flash-lite"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def get_headers():
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": os.getenv("GEMINI_API_KEY", "")
    }

def render_pages_to_jpeg_bytes(pdf_bytes: bytes, start_page: int, end_page: int) -> list[bytes]:
    """Renders PDF pages to JPEG bytes quickly with optimized quality."""
    doc = PdfDocument(pdf_bytes)
    total_pages = len(doc)
    images = []
    
    end_page = min(end_page, total_pages)
    for page_num in range(start_page, end_page):
        page = doc[page_num]
        image = page.render(scale=1.2).to_pil()
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=70)
        images.append(buf.getvalue())
        
    return images

def extract_questions_from_page_chunk(image_bytes_list: list[bytes]) -> list[dict]:
    """Sends page images to Gemini REST API to extract MCQs quickly."""
    headers = get_headers()
    
    parts = []
    for img_bytes in image_bytes_list:
        b64_data = base64.b64encode(img_bytes).decode("utf-8")
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": b64_data
            }
        })
        
    prompt = """Extract all multiple-choice questions (MCQs) visible in these exam pages.
Return JSON array of objects:
[
  {
    "question_number": 1,
    "question_text": "Hindi and English question text",
    "options": {"A": "opt1", "B": "opt2", "C": "opt3", "D": "opt4"}
  }
]
"""
    parts.append({"text": prompt})
    
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }
    
    for attempt in range(2):
        try:
            res = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            elif res.status_code == 429:
                time.sleep(2)
        except Exception as e:
            print(f"Extraction chunk failed: {e}")
            time.sleep(1)
            
    return []

def extract_all_questions(pdf_bytes: bytes) -> list[dict]:
    """Renders PDF to images and extracts all MCQs in larger 6-page chunks to avoid 502 timeouts."""
    doc = PdfDocument(pdf_bytes)
    total_pages = len(doc)
    print(f"Processing PDF with {total_pages} pages...")
    
    all_questions = []
    chunk_size = 6  # 6 pages per chunk makes it 2x faster
    
    for start in range(0, total_pages, chunk_size):
        end = min(start + chunk_size, total_pages)
        print(f"Scanning pages {start+1} to {end}...")
        img_bytes_list = render_pages_to_jpeg_bytes(pdf_bytes, start, end)
        questions = extract_questions_from_page_chunk(img_bytes_list)
        if isinstance(questions, list):
            all_questions.extend(questions)
        time.sleep(0.5)
        
    all_questions.sort(key=lambda x: x.get("question_number", 0))
    return all_questions

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts text from answer key PDF quickly."""
    img_list = render_pages_to_jpeg_bytes(pdf_bytes, 0, 4)
    headers = get_headers()
    
    parts = []
    for img_bytes in img_list:
        b64_data = base64.b64encode(img_bytes).decode("utf-8")
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": b64_data
            }
        })
        
    prompt = """Extract all Question Numbers and Correct Options (A, B, C, D, or Delete/*) from this official answer key.
Format each line strictly like:
1: A
2: C
3: B
"""
    parts.append({"text": prompt})
    
    payload = {
        "contents": [{"parts": parts}]
    }
    
    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=45)
        if res.status_code == 200:
            data = res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Answer key extraction failed: {e}")
    return ""
