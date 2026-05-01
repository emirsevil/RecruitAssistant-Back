from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
import crud.quiz as crud
import schemas.quiz as schemas
from routers.auth import get_current_user
import models

router = APIRouter(
    prefix="/quizzes",
    tags=["Quizzes"]
)

@router.get("/{quiz_id}", response_model=schemas.QuizGroupResponse)
def read_quiz_set(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Fetch a specific quiz set with its questions and attempt count."""
    db_quiz = crud.get_quiz(db, quiz_id=quiz_id)
    if db_quiz is None:
        raise HTTPException(status_code=404, detail="Quiz bulunamadı")
    
    # Check if this quiz set belongs to a workspace owned by the user
    if db_quiz.workspace and db_quiz.workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu quize erişim yetkiniz yok")

    attempts = crud.count_quiz_attempts(db, quiz_id, current_user.id)
    
    return schemas.QuizGroupResponse(
        id=db_quiz.id,
        title=db_quiz.title,
        difficulty=db_quiz.difficulty,
        questions=db_quiz.questions,
        attempts_count=attempts
    )

@router.get("/{quiz_id}/can-start")
def check_can_start(quiz_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Check if the user can still take this quiz (limit: 3 attempts)."""
    db_quiz = crud.get_quiz(db, quiz_id=quiz_id)
    if not db_quiz:
        raise HTTPException(status_code=404, detail="Quiz bulunamadı")
    
    attempts = crud.count_quiz_attempts(db, quiz_id, current_user.id)
    can_start = attempts < 3
    
    return {"can_start": can_start, "attempts_made": attempts, "remaining": max(0, 3 - attempts)}

@router.post("/submit", response_model=schemas.QuizSubmitResponse)
def submit_quiz(
    submission: schemas.QuizSubmit, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Handle quiz submission. Calculates score, tracks attempt number, and enforces 3-attempt limit.
    """
    db_quiz = crud.get_quiz(db, quiz_id=submission.quiz_id)
    if not db_quiz:
        raise HTTPException(status_code=404, detail="Quiz bulunamadı")
    
    # Final safety check for ownership
    if db_quiz.workspace and db_quiz.workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu quize erişim yetkiniz yok")

    # Final safety check for attempt limit
    attempts = crud.count_quiz_attempts(db, submission.quiz_id, current_user.id)
    if attempts >= 3:
        raise HTTPException(status_code=400, detail="Bu quiz için maksimum deneme sayısına ulaştınız (3).")

    results = []
    correct_count = 0
    
    # Map questions to their IDs for easier lookup
    questions_map = {q.id: q for q in db_quiz.questions}

    for answer in submission.answers:
        q_obj = questions_map.get(answer.question_id)
        if not q_obj:
            continue

        is_correct = (answer.selected_answer == q_obj.correct_answer)
        if is_correct:
            correct_count += 1

        results.append(schemas.QuestionResult(
            question_id=q_obj.id,
            question=q_obj.question,
            selected_answer=answer.selected_answer,
            correct_answer=q_obj.correct_answer,
            is_correct=is_correct,
        ))

    total = len(db_quiz.questions)
    score_pct = round((correct_count / total) * 100) if total > 0 else 0

    # Save score to DB
    db_score = crud.create_quiz_score(
        db=db,
        user_id=current_user.id,
        quiz_id=submission.quiz_id,
        score=score_pct,
        total_questions=total,
        correct_answers=correct_count,
    )

    if not db_score: # Redundant check but safe
        raise HTTPException(status_code=400, detail="Skor kaydedilemedi veya limit aşıldı.")

    return schemas.QuizSubmitResponse(
        quiz_id=db_quiz.id,
        score=score_pct,
        correct_count=correct_count,
        total_questions=total,
        results=results,
        score_id=db_score.id,
        attempt_number=db_score.attempt_number
    )

@router.get("/scores/me", response_model=list[schemas.QuizScoreResponse])
def get_user_scores(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fetch all quiz results for the authenticated user."""
    scores = crud.get_scores_by_user(db=db, user_id=current_user.id)
    
    response = []
    for s in scores:
        response.append(schemas.QuizScoreResponse(
            id=s.id,
            user_id=s.user_id,
            quiz_id=s.quiz_id,
            quiz_title=s.quiz.title if s.quiz else "Technical Quiz",
            difficulty=s.quiz.difficulty if s.quiz else "Medium",
            score=s.score,
            total_questions=s.total_questions,
            correct_answers=s.correct_answers,
            attempt_number=s.attempt_number,
            completed_at=s.completed_at
        ))
    return response
