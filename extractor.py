import os
import io
import time
import base64
import json
import requests
from pypdfium2 import PdfDocument
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.1-flash-lite"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def get_headers():
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": os.getenv("GEMINI_API_KEY", "")
    }

def render_pages_to_jpeg_bytes(pdf_bytes: bytes, start_page: int, end_page: int) -> list[bytes]:
    """Renders PDF pages to JPEG bytes using pypdfium2."""
    doc = PdfDocument(pdf_bytes)
    total_pages = len(doc)
    images = []
    
    end_page = min(end_page, total_pages)
    for page_num in range(start_page, end_page):
        page = doc[page_num]
        image = page.render(scale=1.5).to_pil()
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=80)
        images.append(buf.getvalue())
        
    return images

def extract_questions_from_page_chunk(image_bytes_list: list[bytes], chunk_id: int) -> list[dict]:
    """Sends page images to Gemini REST API to extract questions and options."""
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
        
    prompt = """
    Extract all multiple-choice questions (MCQs) visible in these exam pages.
    These questions are bilingual (Hindi and English). Keep both Hindi and English text if present.
    Return JSON array of objects with:
    - question_number: integer (e.g. 1, 2, 3...)
    - question_text: string (full text of question)
    - options: dictionary with keys "A", "B", "C", "D" and optionally "E"
    """
    
    parts.append({"text": prompt})
    
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            elif res.status_code == 429:
                time.sleep(4 * (attempt + 1))
            else:
                print(f"API Error {res.status_code}: {res.text}")
                break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
            
    return []

def extract_all_questions(pdf_bytes: bytes) -> list[dict]:
    """Renders PDF to images and extracts all MCQs sequentially."""
    doc = PdfDocument(pdf_bytes)
    total_pages = len(doc)
    print(f"Processing PDF with {total_pages} pages...")
    
    all_questions = []
    chunk_size = 4
    
    for start in range(0, total_pages, chunk_size):
        end = min(start + chunk_size, total_pages)
        print(f"Rendering and scanning pages {start+1} to {end}...")
        img_bytes_list = render_pages_to_jpeg_bytes(pdf_bytes, start, end)
        questions = extract_questions_from_page_chunk(img_bytes_list, start // chunk_size)
        all_questions.extend(questions)
        time.sleep(1.0)
        
    # Sort by question_number
    all_questions.sort(key=lambda x: x.get("question_number", 0))
    return all_questions

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts text from answer key PDF using visual OCR via Gemini."""
    img_list = render_pages_to_jpeg_bytes(pdf_bytes, 0, 5)
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
        
    prompt = """
    Extract all Question Numbers and their Correct Options (A, B, C, D, or Delete/*) from this official answer key.
    Return plain text with each line like:
    1: A
    2: C
    3: B
    """
    parts.append({"text": prompt})
    
    payload = {
        "contents": [{"parts": parts}]
    }
    
    res = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    if res.status_code == 200:
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    return ""
