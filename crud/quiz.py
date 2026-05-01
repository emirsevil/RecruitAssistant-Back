from sqlalchemy.orm import Session
import models
from schemas import quiz as quiz_schema
from typing import List, Optional

# --- Quiz Group CRUD ---
def get_quiz(db: Session, quiz_id: int):
    return db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()

def list_quizzes(db: Session, skip: int = 0, limit: int = 100, workspace_id: Optional[int] = None) -> List[models.Quiz]:
    query = db.query(models.Quiz)
    if workspace_id is not None:
        query = query.filter(models.Quiz.workspace_id == workspace_id)
    return query.order_by(models.Quiz.created_at.desc()).offset(skip).limit(limit).all()

def create_quiz(db: Session, quiz: quiz_schema.QuizBase):
    db_quiz = models.Quiz(
        workspace_id=quiz.workspace_id,
        title=quiz.title,
        difficulty=quiz.difficulty,
    )
    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)
    return db_quiz

# --- Question CRUD ---
def get_question(db: Session, question_id: int):
    return db.query(models.Question).filter(models.Question.id == question_id).first()

def create_question(db: Session, question: quiz_schema.QuestionCreate):
    db_question = models.Question(
        quiz_id=question.quiz_id,
        question=question.question,
        options=question.options,
        correct_answer=question.correct_answer,
    )
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question

# --- Quiz Score CRUD ---
def create_quiz_score(db: Session, user_id: int, quiz_id: int,
                      score: int, total_questions: int, correct_answers: int):
    # Check current attempts for this specific quiz set
    existing_attempts = db.query(models.QuizScore).filter(
        models.QuizScore.user_id == user_id,
        models.QuizScore.quiz_id == quiz_id
    ).count()
    
    if existing_attempts >= 3:
        # This shouldn't happen if the router check passes, but as a safety:
        return None

    db_score = models.QuizScore(
        user_id=user_id,
        quiz_id=quiz_id,
        score=score,
        attempt_number=existing_attempts + 1,
        total_questions=total_questions,
        correct_answers=correct_answers,
    )
    db.add(db_score)
    db.commit()
    db.refresh(db_score)
    return db_score

def get_scores_by_user(db: Session, user_id: int) -> List[models.QuizScore]:
    return db.query(models.QuizScore).filter(
        models.QuizScore.user_id == user_id
    ).order_by(models.QuizScore.completed_at.desc()).all()

def get_scores_by_quiz(db: Session, quiz_id: int, user_id: Optional[int] = None) -> List[models.QuizScore]:
    query = db.query(models.QuizScore).filter(
        models.QuizScore.quiz_id == quiz_id
    )
    if user_id is not None:
        query = query.filter(models.QuizScore.user_id == user_id)
    return query.order_by(models.QuizScore.completed_at.desc()).all()

def get_scores_by_workspace(db: Session, workspace_id: int, user_id: int) -> List[models.QuizScore]:
    return (
        db.query(models.QuizScore)
        .join(models.Quiz, models.QuizScore.quiz_id == models.Quiz.id)
        .filter(models.Quiz.workspace_id == workspace_id, models.QuizScore.user_id == user_id)
        .order_by(models.QuizScore.completed_at.desc())
        .all()
    )

def count_quiz_attempts(db: Session, quiz_id: int, user_id: int) -> int:
    return db.query(models.QuizScore).filter(
        models.QuizScore.user_id == user_id,
        models.QuizScore.quiz_id == quiz_id
    ).count()
