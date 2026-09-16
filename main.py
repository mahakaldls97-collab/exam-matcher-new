import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Ensure imports work whether run from root or backend
CURRENT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(CURRENT_DIR))

from extractor import extract_all_questions, extract_text_from_pdf
from matcher import match_questions, match_two_series
from scorer import calculate_score

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

# FRONTEND DIRECTORY - works whether files are in root or frontend folder
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
    answer_key: UploadFile = File(...)
):
    try:
        bytes_a = await paper_a.read()
        bytes_key = await answer_key.read()

        if not bytes_a or not bytes_key:
            raise HTTPException(status_code=400, detail="Paper A and Answer Key cannot be empty.")

        questions_a = extract_all_questions(bytes_a)
        if not questions_a:
            raise HTTPException(status_code=400, detail="Could not extract questions from Paper A.")

        key_text = extract_text_from_pdf(bytes_key)
        if not key_text:
            raise HTTPException(status_code=400, detail="Could not extract text from Answer Key.")

        key_mapping = match_questions(questions_a, key_text)

        if paper_b:
            bytes_b = await paper_b.read()
            if bytes_b:
                questions_b = extract_all_questions(bytes_b)
                if questions_b:
                    series_results = match_two_series(questions_a, questions_b, key_mapping)
                    return JSONResponse(content={
                        "mode": "two_series",
                        "results": series_results
                    })

        single_results = []
        for q in questions_a:
            q_num = q.get("question_number")
            correct_ans = key_mapping.get(str(q_num), key_mapping.get(q_num, ""))
            single_results.append({
                "series_a_num": q_num,
                "question_text": q.get("question_text", ""),
                "options": q.get("options", {}),
                "correct_answer": correct_ans
            })

        return JSONResponse(content={
            "mode": "single_series",
            "results": single_results
        })

    except Exception as e:
        print(f"Error in match_series_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount frontend files at root
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
