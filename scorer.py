def calculate_score(
    paper_questions: list,
    matches: list,
    student_answers: dict,
    negative_marking: float = 0.0,
    marks_per_question: float = 1.0,
) -> dict:
    """
    Calculate final score and return detailed results table + summary.
    
    Args:
        paper_questions: List of {q_no, question, options}
        matches: List of {paper_q_no, key_q_no, correct_answer, matched_by}
        student_answers: Dict {q_no: "A"|"B"|"C"|"D"}
        negative_marking: Marks deducted per wrong answer (e.g. 0.25)
        marks_per_question: Marks per correct answer (e.g. 1.0 or 2.0)
    """
    paper_q_map = {str(q["q_no"]): q for q in paper_questions}
    match_map = {str(m["paper_q_no"]): m for m in matches}

    results = []
    total_correct = 0
    total_wrong = 0
    total_unattempted = 0
    total_score = 0.0

    for q_no, q in paper_q_map.items():
        match = match_map.get(q_no, {})
        student_answer = student_answers.get(q_no, "").upper().strip()
        correct_answer = (match.get("correct_answer") or "").upper().strip()

        if not student_answer or (student_answer == "E" and correct_answer != "E"):
            status = "unattempted"
            total_unattempted += 1
            score_change = 0.0
        elif correct_answer and student_answer == correct_answer:
            status = "correct"
            total_correct += 1
            score_change = marks_per_question
        elif not correct_answer:
            # Correct answer unknown (match failed)
            status = "unknown"
            score_change = 0.0
        else:
            status = "wrong"
            total_wrong += 1
            score_change = -negative_marking

        total_score += score_change

        results.append(
            {
                "paper_q_no": q_no,
                "question": q.get("question", ""),
                "options": q.get("options", {}),
                "key_q_no": match.get("key_q_no"),
                "correct_answer": correct_answer or "?",
                "student_answer": student_answer or "-",
                "status": status,
                "score_change": round(score_change, 2),
                "matched_by": match.get("matched_by", "unknown"),
            }
        )

    # Sort by numeric question number
    def _sort_key(r):
        try:
            return (0, int(r["paper_q_no"]))
        except ValueError:
            return (1, r["paper_q_no"])

    results.sort(key=_sort_key)

    total_questions = len(results)
    max_score = total_questions * marks_per_question

    return {
        "results": results,
        "summary": {
            "total_questions": total_questions,
            "correct": total_correct,
            "wrong": total_wrong,
            "unattempted": total_unattempted,
            "score": round(total_score, 2),
            "max_score": round(max_score, 2),
            "percentage": round((total_score / max_score * 100) if max_score > 0 else 0, 2),
            "negative_marking": negative_marking,
            "marks_per_question": marks_per_question,
        },
    }
