"""Seed high-quality demo data for testing the company (recruiter) portal.

Creates, all marked with demo emails so it stays isolated and re-runnable:
  - One hiring company + recruiter (login printed at the end)
  - Several realistic job openings across roles
  - A set of discoverable candidates (is_searchable=True), each with a profile,
    completed technical + HR interviews (varied scores) and quiz results
  - Runs services.performance.recompute_candidate_performance for each candidate
    so DashboardUserProgress + SkillScore populate exactly as in production.

Candidate strength is intentionally varied (strong / mid / developing) so that
recruiter matching and ranking produce meaningful, different results.

Run from the backend root (with Postgres up):
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --reset      # wipe demo data first, then reseed

Idempotent: existing demo emails are skipped (or removed first with --reset).
Default password for every demo account: demo1234

Note: demo emails use a real TLD (@demo.com). The login endpoints validate with
Pydantic EmailStr / email-validator, which rejects reserved domains like .local.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = THIS_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from utils.auth import get_password_hash  # noqa: E402
from services.performance import recompute_candidate_performance  # noqa: E402

DEMO_PASSWORD = "demo1234"
DEMO_EMAIL_DOMAIN = "@demo.com"
DEMO_COMPANY_NAME = "Nebula Software (Demo)"
RECRUITER_EMAIL = "recruiter@demo.com"

# ── Job openings for the demo company ────────────────────────────────────
JOBS = [
    dict(
        title="Senior Frontend Engineer",
        department="Engineering",
        difficulty_level="senior",
        required_skills="react, typescript, next.js, javascript, css",
        description="Own our customer-facing web app. Strong React/TypeScript and an eye for UX.",
    ),
    dict(
        title="Backend Engineer (Python)",
        department="Engineering",
        difficulty_level="mid",
        required_skills="python, fastapi, postgresql, docker, rest api",
        description="Design and ship reliable Python services and APIs at scale.",
    ),
    dict(
        title="Machine Learning Engineer",
        department="AI",
        difficulty_level="senior",
        required_skills="python, pytorch, machine learning, nlp, sql",
        description="Build and deploy ML/NLP models into production pipelines.",
    ),
    dict(
        title="Full-Stack Developer",
        department="Engineering",
        difficulty_level="junior",
        required_skills="react, node.js, typescript, postgresql, docker",
        description="Work across the stack on features end-to-end.",
    ),
    dict(
        title="Data Analyst",
        department="Data",
        difficulty_level="junior",
        required_skills="sql, python, data analysis, statistics, tableau",
        description="Turn product and business data into actionable insight.",
    ),
]

# ── Candidates ───────────────────────────────────────────────────────────
# tech / hr interviews are (categories, overall_score); quiz is (title, score).
CANDIDATES = [
    dict(
        full_name="Elif Demir", email="elif.demir@demo.com",
        professional_title="Senior Frontend Engineer",
        education="BSc Computer Engineering, Boğaziçi University",
        bio="Frontend specialist focused on React, TypeScript and design systems.",
        skills="react, typescript, next.js, javascript, css, redux",
        tech=[("react, typescript", 94), ("next.js, javascript", 90), ("css, react", 88)],
        hr=[("communication, teamwork", 86)],
        quiz=("React Fundamentals", 92),
    ),
    dict(
        full_name="Mert Kaya", email="mert.kaya@demo.com",
        professional_title="Backend Engineer",
        education="BSc Computer Science, METU",
        bio="Backend engineer who loves clean APIs, Postgres and observability.",
        skills="python, fastapi, postgresql, docker, rest api, redis",
        tech=[("python, fastapi", 91), ("postgresql, rest api", 88), ("docker, python", 85)],
        hr=[("communication, ownership", 82)],
        quiz=("SQL & Databases", 89),
    ),
    dict(
        full_name="Zeynep Yılmaz", email="zeynep.yilmaz@demo.com",
        professional_title="Machine Learning Engineer",
        education="MSc Artificial Intelligence, ITU",
        bio="ML engineer working on NLP and recommendation systems.",
        skills="python, pytorch, machine learning, nlp, sql, pandas",
        tech=[("python, pytorch", 93), ("machine learning, nlp", 90), ("sql, pandas", 86)],
        hr=[("communication, collaboration", 84)],
        quiz=("Machine Learning Basics", 90),
    ),
    dict(
        full_name="Selin Koç", email="selin.koc@demo.com",
        professional_title="Data Scientist",
        education="BSc Statistics, Hacettepe University",
        bio="Data scientist bridging analytics and applied ML.",
        skills="python, machine learning, sql, pandas, scikit-learn, statistics",
        tech=[("python, sql", 88), ("machine learning, statistics", 85), ("pandas, scikit-learn", 83)],
        hr=[("communication, problem solving", 80)],
        quiz=("Statistics & Data", 86),
    ),
    dict(
        full_name="Can Öztürk", email="can.ozturk@demo.com",
        professional_title="Full-Stack Developer",
        education="BSc Software Engineering, Yıldız Technical University",
        bio="Full-stack developer comfortable across React and Node.",
        skills="react, node.js, typescript, postgresql, docker, express",
        tech=[("react, node.js", 72), ("typescript, postgresql", 68), ("docker, express", 65)],
        hr=[("communication, teamwork", 74)],
        quiz=("JavaScript Essentials", 70),
    ),
    dict(
        full_name="Ayşe Şahin", email="ayse.sahin@demo.com",
        professional_title="Data Analyst",
        education="BSc Industrial Engineering, Sabancı University",
        bio="Analyst turning messy data into clear dashboards.",
        skills="sql, python, data analysis, statistics, tableau, excel",
        tech=[("sql, data analysis", 78), ("python, statistics", 71), ("tableau, excel", 75)],
        hr=[("communication, presentation", 79)],
        quiz=("SQL & Databases", 76),
    ),
    dict(
        full_name="Burak Aydın", email="burak.aydin@demo.com",
        professional_title="Junior Frontend Developer",
        education="BSc Computer Engineering, Ege University",
        bio="Early-career frontend developer learning React deeply.",
        skills="react, javascript, css, html",
        tech=[("react, javascript", 55), ("css, html", 50)],
        hr=[("communication, motivation", 68)],
        quiz=("React Fundamentals", 52),
    ),
    dict(
        full_name="Deniz Arslan", email="deniz.arslan@demo.com",
        professional_title="Junior Backend Developer",
        education="BSc Computer Science, Dokuz Eylül University",
        bio="Junior backend developer focused on Python and SQL.",
        skills="python, fastapi, sql, git",
        tech=[("python, sql", 62), ("fastapi, git", 58)],
        hr=[("communication, eagerness", 70)],
        quiz=("Python Basics", 60),
    ),
]

# 5 simple questions reused across quizzes (content not important for matching).
SAMPLE_QUESTIONS = [
    dict(question="Which keyword declares a constant in JavaScript?",
         options=["var", "let", "const", "static"], correct_answer="const"),
    dict(question="What does SQL stand for?",
         options=["Structured Query Language", "Simple Query Logic",
                  "Sequential Query Language", "Standard Question Layout"],
         correct_answer="Structured Query Language"),
    dict(question="Which data structure uses FIFO ordering?",
         options=["Stack", "Queue", "Tree", "Graph"], correct_answer="Queue"),
    dict(question="In Python, which type is immutable?",
         options=["list", "dict", "set", "tuple"], correct_answer="tuple"),
    dict(question="HTTP status 404 means?",
         options=["OK", "Created", "Not Found", "Server Error"],
         correct_answer="Not Found"),
]


def _wipe_demo_data(db):
    """Remove previously seeded demo data (cascades handle children)."""
    candidates = (
        db.query(models.User)
        .filter(models.User.email.like(f"%{DEMO_EMAIL_DOMAIN}"))
        .all()
    )
    for user in candidates:
        db.delete(user)
    company = (
        db.query(models.Company)
        .filter(models.Company.name == DEMO_COMPANY_NAME)
        .first()
    )
    if company:
        db.delete(company)
    db.commit()
    print(f"Reset: removed {len(candidates)} demo candidate(s)"
          + (" and the demo company." if company else "."))


def _seed_company(db):
    company = (
        db.query(models.Company)
        .filter(models.Company.name == DEMO_COMPANY_NAME)
        .first()
    )
    if company is None:
        company = models.Company(
            name=DEMO_COMPANY_NAME,
            website="https://nebula.example.com",
            description="A demo SaaS company hiring across engineering, AI and data.",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

    if db.query(models.Recruiter).filter(models.Recruiter.email == RECRUITER_EMAIL).first() is None:
        db.add(models.Recruiter(
            company_id=company.id,
            full_name="Aylin Recruiter",
            email=RECRUITER_EMAIL,
            hashed_password=get_password_hash(DEMO_PASSWORD),
        ))
        db.commit()

    created_jobs = 0
    for job in JOBS:
        exists = (
            db.query(models.JobOpening)
            .filter(models.JobOpening.company_id == company.id,
                    models.JobOpening.title == job["title"])
            .first()
        )
        if exists is None:
            db.add(models.JobOpening(company_id=company.id, **job))
            created_jobs += 1
    db.commit()
    return company, created_jobs


def _seed_candidate(db, data, now):
    if db.query(models.User).filter(models.User.email == data["email"]).first():
        return False  # already seeded

    user = models.User(
        full_name=data["full_name"],
        email=data["email"],
        hashed_password=get_password_hash(DEMO_PASSWORD),
        professional_title=data["professional_title"],
        education=data["education"],
        bio=data["bio"],
        skills=data["skills"],
        is_searchable=True,  # discoverable by recruiters
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    workspace = models.Workspace(
        user_id=user.id,
        company_name="Interview Practice",
        job_name=data["professional_title"],
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    # Completed interviews (spread over recent weeks for realistic timelines).
    day_offset = 0
    for categories, score in data["tech"]:
        day_offset += 3
        db.add(models.Interview(
            workspace_id=workspace.id, interview_type="technical",
            categories=categories, difficulty="mid", overall_score=score,
            status="completed", mode="text", duration_seconds=900,
            created_at=now - timedelta(days=day_offset),
        ))
    for categories, score in data["hr"]:
        day_offset += 3
        db.add(models.Interview(
            workspace_id=workspace.id, interview_type="hr",
            categories=categories, difficulty="mid", overall_score=score,
            status="completed", mode="text", duration_seconds=600,
            created_at=now - timedelta(days=day_offset),
        ))

    # A quiz with questions + a score.
    quiz_title, quiz_score = data["quiz"]
    quiz = models.Quiz(workspace_id=workspace.id, title=quiz_title, difficulty="Medium")
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    for q in SAMPLE_QUESTIONS:
        db.add(models.Question(quiz_id=quiz.id, question=q["question"],
                               options=q["options"], correct_answer=q["correct_answer"]))
    total = len(SAMPLE_QUESTIONS)
    correct = round(total * quiz_score / 100)
    db.add(models.QuizScore(
        user_id=user.id, quiz_id=quiz.id, score=quiz_score,
        attempt_number=1, total_questions=total, correct_answers=correct,
        completed_at=now - timedelta(days=1),
    ))
    db.commit()

    # Populate the recruiter-facing performance signals.
    recompute_candidate_performance(db, user.id)
    return True


def main():
    parser = argparse.ArgumentParser(description="Seed demo data for the company portal.")
    parser.add_argument("--reset", action="store_true",
                        help="Delete existing demo data before seeding.")
    args = parser.parse_args()

    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        if args.reset:
            _wipe_demo_data(db)

        company, new_jobs = _seed_company(db)
        print(f"Company: {company.name} (id={company.id}) — {new_jobs} new job opening(s).")

        created = 0
        for data in CANDIDATES:
            if _seed_candidate(db, data, now):
                created += 1
                print(f"  ✓ candidate {data['full_name']} <{data['email']}>")
            else:
                print(f"  · skipped (exists) {data['email']}")

        total_jobs = db.query(models.JobOpening).filter(
            models.JobOpening.company_id == company.id).count()
        searchable = db.query(models.User).filter(models.User.is_searchable == True).count()

        print("\nSeed complete.")
        print(f"  Candidates created this run: {created} (total searchable users: {searchable})")
        print(f"  Job openings for {company.name}: {total_jobs}")
        print("\nRecruiter login (company portal, http://localhost:3001):")
        print(f"  email:    {RECRUITER_EMAIL}")
        print(f"  password: {DEMO_PASSWORD}")
        print("\nAny candidate (candidate portal, http://localhost:3000) uses the same password:")
        print(f"  e.g. elif.demir@demo.com / {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
