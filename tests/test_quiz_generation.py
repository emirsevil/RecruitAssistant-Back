import json
import sys, os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root is in sys.path for imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from fastapi.testclient import TestClient
from unittest.mock import patch

# Import the FastAPI app
from main import app
from database import Base, get_db as get_db_dependency
import models
from models import Workspace, User
from sqlalchemy.orm import Session

from sqlalchemy.pool import StaticPool

# Setup in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables in the in-memory database
# We call it AFTER models are imported
Base.metadata.create_all(bind=engine)

# Create a test client
client = TestClient(app)

# Dependency override
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db_dependency] = override_get_db

from routers.auth import get_current_user
def override_get_current_user():
    db = TestingSessionLocal()
    user = db.query(models.User).first()
    db.close()
    return user

app.dependency_overrides[get_current_user] = override_get_current_user

# Helper to create a workspace with job description
def create_workspace(db: Session, user_id: int, job_desc: str) -> Workspace:
    ws = Workspace(user_id=user_id, company_name="TestCo", job_description=job_desc)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws

def test_generate_quizzes_endpoint():
    # Create a user and workspace in the in-memory test DB
    import time
    unique_email = f"test_{int(time.time())}@example.com"
    db = TestingSessionLocal()
    user = User(full_name="Test User", email=unique_email)
    db.add(user)
    db.commit()
    db.refresh(user)
    workspace = create_workspace(db, user.id, "SQL and Java development experience required.")
    db.close()

    dummy_groups = [
        {
            "title": "Technical Quiz",
            "difficulty": "Medium",
            "questions": [
                {
                    "question": "What does SQL stand for?",
                    "options": ["Structured Query Language", "Simple Query List", "Sequential Query Logic", "Standard Query Language"],
                    "correct_answer": "Structured Query Language",
                },
                {
                    "question": "Which keyword is used to inherit a class in Java?",
                    "options": ["extends", "implements", "inherits", "super"],
                    "correct_answer": "extends",
                },
            ]
        }
    ]

    # Patch the service function where it is used in the router to return dummy data
    with patch("routers.workspace.generate_quizzes_from_job_description", return_value=dummy_groups):
        response = client.post(f"/workspaces/{workspace.id}/quizzes/generate")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        
        group = data[0]
        assert group["title"] == "Technical Quiz"
        assert group["difficulty"] == "Medium"
        assert len(group["questions"]) == 2
        
        # Verify response (without correct_answer)
        for returned, expected in zip(group["questions"], dummy_groups[0]["questions"]):
            assert returned["question"] == expected["question"]
            assert returned["options"] == expected["options"]
            assert "correct_answer" not in returned

        # Verify database (with correct_answer)
        db = TestingSessionLocal()
        db_quizzes = db.query(models.Quiz).filter(models.Quiz.workspace_id == workspace.id).all()
        assert len(db_quizzes) == 1
        db_q = db_quizzes[0]
        assert db_q.title == "Technical Quiz"
        assert db_q.difficulty == "Medium"
        
        db_questions = db_q.questions
        assert len(db_questions) == 2
        for db_question, expected in zip(db_questions, dummy_groups[0]["questions"]):
            assert db_question.question == expected["question"]
            assert db_question.options == expected["options"]
            assert db_question.correct_answer == expected["correct_answer"]
        db.close()
    
    # Cleanup: refresh overrides if needed, but here it's fine
