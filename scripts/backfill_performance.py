"""One-off backfill for the candidate-performance loop.

Recomputes the persisted, recruiter-facing performance signals
(DashboardUserProgress averages + SkillScore rows) for every candidate who
already has completed interviews or quiz scores. New activity is aggregated
automatically going forward (crud/interview.update_interview,
crud/quiz.create_quiz_score); this script seeds the existing history.

Run from the backend root:
    python -m scripts.backfill_performance
or:
    python scripts/backfill_performance.py

Idempotent — safe to re-run (recompute_candidate_performance upserts).
"""

import sys
from pathlib import Path

# Make sure we can import the app modules when run as a script from anywhere.
THIS_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = THIS_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database import SessionLocal  # noqa: E402
import models  # noqa: E402
from services.performance import recompute_candidate_performance  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        # Candidates with at least one completed interview (owned via workspace)
        interview_user_ids = {
            row[0]
            for row in (
                db.query(models.Workspace.user_id)
                .join(models.Interview, models.Interview.workspace_id == models.Workspace.id)
                .filter(models.Interview.status == "completed")
                .distinct()
                .all()
            )
        }

        # Candidates with at least one quiz score
        quiz_user_ids = {
            row[0] for row in db.query(models.QuizScore.user_id).distinct().all()
        }

        user_ids = sorted(uid for uid in (interview_user_ids | quiz_user_ids) if uid is not None)

        print(f"Backfilling performance for {len(user_ids)} candidate(s)...")
        for uid in user_ids:
            recompute_candidate_performance(db, uid)
            print(f"  ✓ user_id={uid}")
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
