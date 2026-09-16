import json
import os
import sys
import traceback

# Ensure backend directory is in sys.path for cloud deployment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from extractor import extract_and_parse_key, extract_and_parse_paper
from matcher import match_questions, match_two_series
from scorer import calculate_score

app = FastAPI(title="Exam Answer Matcher API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Server is running!"}

@app.post("/api/extract-paper")
async def extract_paper(file: UploadFile = File(...)):
    try:
        content = await file.read()
        filename = file.filename or "paper.pdf"
        questions = await extract_and_parse_paper(content, filename)
        return {"success": True, "questions": questions, "total": len(questions)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Extraction error: {str(e)}")

@app.post("/api/match-series")
async def match_series(
    paper_a: UploadFile = File(...),
    paper_b: UploadFile = File(None),
    answer_key: UploadFile = File(None),
):
    """
    Matches Series A with Series D/Master Paper and optional Answer Key.
    """
    try:
        bytes_a = await paper_a.read()
        name_a = paper_a.filename or "series_a.pdf"
        print(f"Extracting Paper A: {name_a}")
        questions_a = await extract_and_parse_paper(bytes_a, name_a)

        key_map = {}
        # If Answer Key provided, parse it
        if answer_key and answer_key.filename:
            bytes_key = await answer_key.read()
            name_key = answer_key.filename or "ans.pdf"
            print(f"Extracting Answer Key: {name_key}")
            key_data = await extract_and_parse_key(bytes_key, name_key)
            for item in key_data.get("data", []):
                key_map[str(item.get("q_no"))] = str(item.get("correct_answer", "")).upper()

        questions_b = []
        if paper_b and paper_b.filename:
            bytes_b = await paper_b.read()
            name_b = paper_b.filename or "series_d.pdf"
            print(f"Extracting Paper B (Series D): {name_b}")
            questions_b = await extract_and_parse_paper(bytes_b, name_b)

        # Match questions between Series A and Series B
        if questions_b:
            matched_table = await match_two_series(questions_a, questions_b, key_map)
        else:
            # Direct mapping if only Paper A and Key provided
            matched_table = []
            for q in questions_a:
                qno = str(q.get("q_no"))
                matched_table.append({
                    "series_a_q_no": qno,
                    "question": q.get("question", ""),
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
        raise HTTPException(status_code=500, detail=f"Match error: {str(e)}")

@app.post("/api/match-score")
async def match_score(
    answer_key: UploadFile = File(...),
    paper_questions: str = Form(...),
    student_answers: str = Form(...),
    negative_marking: float = Form(0.0),
    marks_per_question: float = Form(1.0),
):
    try:
        paper_qs = json.loads(paper_questions)
        student_ans = json.loads(student_answers)

        key_bytes = await answer_key.read()
        key_filename = answer_key.filename or "answer_key.pdf"

        key_data = await extract_and_parse_key(key_bytes, key_filename)
        matches = await match_questions(paper_qs, key_data)
        result = calculate_score(paper_qs, matches, student_ans, negative_marking, marks_per_question)

        return {"success": True, **result}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Score error: {str(e)}")

# ─────────────────────── Serve Frontend ───────────────────────
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
