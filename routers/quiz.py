from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import crud.quiz as crud
import schemas.quiz as schemas

router = APIRouter(
    prefix="/quizzes",
    tags=["Quizzes"]
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.QuizResponse)
def create_quiz(quiz: schemas.QuizCreate, db: Session = Depends(get_db)):
    return crud.create_quiz(db=db, quiz=quiz)

@router.get("/{quiz_id}", response_model=schemas.QuizResponse)
def read_quiz(quiz_id: int, db: Session = Depends(get_db)):
    db_quiz = crud.get_quiz(db, quiz_id=quiz_id)
    if db_quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return db_quiz

@router.get("/", response_model=list[schemas.QuizResponse])
def list_quizzes(skip: int = 0, limit: int = 100, workspace_id: int | None = None, db: Session = Depends(get_db)):
    return crud.list_quizzes(db=db, skip=skip, limit=limit, workspace_id=workspace_id)

@router.put("/{quiz_id}", response_model=schemas.QuizResponse)
def update_quiz(quiz_id: int, quiz: schemas.QuizUpdate, db: Session = Depends(get_db)):
    db_quiz = crud.update_quiz(db=db, quiz_id=quiz_id, quiz_update=quiz)
    if db_quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return db_quiz

@router.delete("/{quiz_id}", response_model=schemas.QuizResponse)
def delete_quiz(quiz_id: int, db: Session = Depends(get_db)):
    db_quiz = crud.delete_quiz(db=db, quiz_id=quiz_id)
    if db_quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return db_quiz


# --- Quiz Submit & Score Endpoints ---

@router.post("/submit", response_model=schemas.QuizSubmitResponse)
def submit_quiz(submission: schemas.QuizSubmit, db: Session = Depends(get_db)):
    """
    Kullanıcı quiz'i bitirdiğinde cevaplarını gönderir.
    Backend doğru cevapları DB'den kontrol eder, skoru hesaplar ve kaydeder.
    """
    results = []
    correct_count = 0

    for answer in submission.answers:
        # Soruyu DB'den çek (correct_answer dahil)
        db_quiz = crud.get_quiz(db, quiz_id=answer.quiz_id)
        if db_quiz is None:
            raise HTTPException(
                status_code=404,
                detail=f"Quiz question with id {answer.quiz_id} not found"
            )

        is_correct = answer.selected_answer == db_quiz.correct_answer
        if is_correct:
            correct_count += 1

        results.append(schemas.QuestionResult(
            quiz_id=db_quiz.id,
            question=db_quiz.question,
            selected_answer=answer.selected_answer,
            correct_answer=db_quiz.correct_answer,
            is_correct=is_correct,
        ))

    total = len(submission.answers)
    score_pct = round((correct_count / total) * 100) if total > 0 else 0

    # Skoru DB'ye kaydet
    db_score = crud.create_quiz_score(
        db=db,
        user_id=submission.user_id,
        workspace_id=submission.workspace_id,
        quiz_title=submission.quiz_title,
        difficulty=submission.difficulty,
        score=score_pct,
        total_questions=total,
        correct_answers=correct_count,
    )

    return schemas.QuizSubmitResponse(
        quiz_title=submission.quiz_title,
        score=score_pct,
        correct_count=correct_count,
        total_questions=total,
        results=results,
        score_id=db_score.id,
    )

@router.get("/scores/user/{user_id}", response_model=list[schemas.QuizScoreResponse])
def get_user_scores(user_id: int, db: Session = Depends(get_db)):
    """Bir kullanıcının tüm quiz skorlarını getir."""
    return crud.get_scores_by_user(db=db, user_id=user_id)

@router.get("/scores/workspace/{workspace_id}", response_model=list[schemas.QuizScoreResponse])
def get_workspace_scores(workspace_id: int, user_id: int | None = None, db: Session = Depends(get_db)):
    """Bir workspace'e ait quiz skorlarını getir. Opsiyonel olarak user_id ile filtrele."""
    return crud.get_scores_by_workspace(db=db, workspace_id=workspace_id, user_id=user_id)

