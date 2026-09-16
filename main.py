import os
import sys
import traceback
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CURRENT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(CURRENT_DIR))

from extractor import extract_all_questions, extract_text_from_pdf
from matcher import match_questions, match_two_series

load_dotenv()

app = FastAPI(title="Exam Answer Key Matcher API")

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if (CURRENT_DIR / "frontend").exists():
    FRONTEND_DIR = CURRENT_DIR / "frontend"
else:
    FRONTEND_DIR = CURRENT_DIR

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/match-series")
async def match_series_endpoint(
    paper_a: UploadFile = File(...),
    paper_b: UploadFile = File(None),
    answer_key: UploadFile = File(None)
):
    try:
        bytes_a = await paper_a.read()
        if not bytes_a:
            raise HTTPException(status_code=400, detail="Paper A cannot be empty.")

        print("Extracting Paper A...")
        questions_a = extract_all_questions(bytes_a)
        if not questions_a:
            raise HTTPException(status_code=400, detail="Could not extract questions from Paper A.")

        key_map = {}
        if answer_key and answer_key.filename:
            bytes_key = await answer_key.read()
            if bytes_key:
                print("Extracting Answer Key...")
                key_text = extract_text_from_pdf(bytes_key)
                if key_text:
                    key_map = match_questions(questions_a, key_text)

        questions_b = []
        if paper_b and paper_b.filename:
            bytes_b = await paper_b.read()
            if bytes_b:
                print("Extracting Paper B...")
                questions_b = extract_all_questions(bytes_b)

        if questions_b:
            print("Matching two series...")
            matched_table = match_two_series(questions_a, questions_b, key_map)
            # If match_two_series is async/coroutine, await it
            if hasattr(matched_table, "__await__"):
                matched_table = await matched_table
        else:
            matched_table = []
            for q in questions_a:
                qno = str(q.get("question_number", q.get("q_no", "")))
                matched_table.append({
                    "series_a_q_no": qno,
                    "question": q.get("question_text", q.get("question", "")),
                    "options": q.get("options", {}),
                    "series_b_q_no": qno,
                    "correct_answer": key_map.get(qno, "?"),
                    "matched_by": "direct"
                })

        return {
            "success": True,
            "total_questions": len(matched_table),
            "matched_table": matched_table,
            "questions_a": questions_a,
            "questions_b_count": len(questions_b),
            "has_key": bool(key_map)
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
