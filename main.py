import os
import sys
import uuid
import traceback
import threading
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
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

# In-memory task storage
tasks = {}

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

def process_task(task_id, bytes_a, bytes_b, bytes_key):
    """Background worker that processes papers and stores result."""
    try:
        tasks[task_id]["status"] = "extracting_paper_a"
        print(f"[{task_id}] Extracting Paper A...")
        questions_a = extract_all_questions(bytes_a)
        if not questions_a:
            tasks[task_id] = {"status": "error", "error": "Paper A se koi question nahi nikla."}
            return

        key_map = {}
        if bytes_key:
            tasks[task_id]["status"] = "extracting_answer_key"
            print(f"[{task_id}] Extracting Answer Key...")
            key_text = extract_text_from_pdf(bytes_key)
            if key_text:
                key_map = match_questions(questions_a, key_text)

        questions_b = []
        if bytes_b:
            tasks[task_id]["status"] = "extracting_paper_b"
            print(f"[{task_id}] Extracting Paper B...")
            questions_b = extract_all_questions(bytes_b)

        if questions_b:
            tasks[task_id]["status"] = "matching_series"
            print(f"[{task_id}] Matching two series...")
            matched_table = match_two_series(questions_a, questions_b, key_map)
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

        tasks[task_id] = {
            "status": "done",
            "result": {
                "success": True,
                "total_questions": len(matched_table),
                "matched_table": matched_table,
                "questions_a": questions_a,
                "questions_b_count": len(questions_b),
                "has_key": bool(key_map)
            }
        }
        print(f"[{task_id}] Done! {len(matched_table)} questions matched.")

    except Exception as e:
        traceback.print_exc()
        tasks[task_id] = {"status": "error", "error": str(e)}

@app.post("/api/match-series")
async def match_series_endpoint(
    paper_a: UploadFile = File(...),
    paper_b: UploadFile = File(None),
    answer_key: UploadFile = File(None)
):
    """Accepts files, starts background processing, returns task_id instantly."""
    bytes_a = await paper_a.read()
    if not bytes_a:
        raise HTTPException(status_code=400, detail="Paper A cannot be empty.")

    bytes_b = None
    if paper_b and paper_b.filename:
        bytes_b = await paper_b.read()

    bytes_key = None
    if answer_key and answer_key.filename:
        bytes_key = await answer_key.read()

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {"status": "starting"}

    thread = threading.Thread(target=process_task, args=(task_id, bytes_a, bytes_b, bytes_key))
    thread.start()

    return {"task_id": task_id, "status": "starting"}

@app.get("/api/task/{task_id}")
def get_task_status(task_id: str):
    """Frontend polls this endpoint to check if processing is done."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
