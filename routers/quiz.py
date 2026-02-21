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
