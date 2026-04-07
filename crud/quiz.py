from sqlalchemy.orm import Session
import models
from schemas import quiz as quiz_schema
from typing import List, Optional


def get_quiz(db: Session, quiz_id: int):
    return db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()


def list_quizzes(db: Session, skip: int = 0, limit: int = 100, workspace_id: Optional[int] = None) -> List[models.Quiz]:
    query = db.query(models.Quiz)
    if workspace_id is not None:
        query = query.filter(models.Quiz.workspace_id == workspace_id)
    return query.offset(skip).limit(limit).all()


def create_quiz(db: Session, quiz: quiz_schema.QuizCreate):
    db_quiz = models.Quiz(
        workspace_id=quiz.workspace_id,
        title=quiz.title,
        difficulty=quiz.difficulty,
        question=quiz.question,
        options=quiz.options,
        correct_answer=quiz.correct_answer,
    )
    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)
    return db_quiz


def update_quiz(db: Session, quiz_id: int, quiz_update: quiz_schema.QuizUpdate):
    db_quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not db_quiz:
        return None
    update_data = quiz_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_quiz, key, value)
    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)
    return db_quiz


def delete_quiz(db: Session, quiz_id: int):
    db_quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not db_quiz:
        return None
    db.delete(db_quiz)
    db.commit()
    return db_quiz


# --- Quiz Score CRUD ---

def create_quiz_score(db: Session, user_id: int, workspace_id: int,
                      quiz_title: str, difficulty: str, score: int, 
                      total_questions: int, correct_answers: int):
    db_score = models.QuizScore(
        user_id=user_id,
        workspace_id=workspace_id,
        quiz_title=quiz_title,
        difficulty=difficulty,
        score=score,
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


def get_scores_by_workspace(db: Session, workspace_id: int, user_id: Optional[int] = None) -> List[models.QuizScore]:
    query = db.query(models.QuizScore).filter(
        models.QuizScore.workspace_id == workspace_id
    )
    if user_id is not None:
        query = query.filter(models.QuizScore.user_id == user_id)
    return query.order_by(models.QuizScore.completed_at.desc()).all()
