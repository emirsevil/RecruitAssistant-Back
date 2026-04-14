import os
import logging
import subprocess
import sys
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def run_migration():
    """
    Runs Alembic migrations in a subprocess to ensure complete isolation 
    from the main application's event loop and logging configuration.
    This prevents deadlocks during startup.
    """
    logger.info("Starting database migration process (via subprocess)...")
    
    try:
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 2d87720d6b34db803ce588b1ac46da4384722c3c
        # Run 'alembic upgrade head' as a separate process
        # This is safer than programmatic API when running inside the app
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Log the output from alembic
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.info(f"Alembic: {line}")
        
        logger.info("Database migration complete! 🎉")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during migration: {e.stderr}")
        logger.info("TIP: If you see an IntegrityError or conflict, run 'python fix_db.py' to resolve data conflicts.")
        # We don't want to crash everything if it's already up to date 
        # but check=True will raise if return code is non-zero
        raise e
<<<<<<< HEAD
=======
=======
>>>>>>> 2d87720d6b34db803ce588b1ac46da4384722c3c
        with engine.connect() as conn:
            # Check cover_letters columns
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='cover_letters'"))
            cols = [row[0] for row in result]
            print(f"cover_letters columns: {cols}")

            if "latex_content" not in cols:
                print("Adding latex_content to cover_letters...")
                conn.execute(text("ALTER TABLE cover_letters ADD COLUMN latex_content TEXT"))
                conn.commit()
                print("Successfully added latex_content to cover_letters.")
            else:
                print("latex_content already exists in cover_letters.")

            # Check cvs columns
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='cvs'"))
            cols = [row[0] for row in result]
            print(f"cvs columns: {cols}")

            if "latex_content" not in cols:
                print("Adding latex_content to cvs...")
                conn.execute(text("ALTER TABLE cvs ADD COLUMN latex_content TEXT"))
                conn.commit()
                print("Successfully added latex_content to cvs.")
            else:
                print("latex_content already exists in cvs.")

            # NEW: Make file_url nullable if it isn't
            print("Updating file_url in cvs to be nullable...")
            conn.execute(text("ALTER TABLE cvs ALTER COLUMN file_url DROP NOT NULL"))
            conn.commit()
            print("Successfully updated file_url in cvs.")

            print("Database migration complete! 🎉")

            # Check workspaces columns
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='workspaces'"))
            cols = [row[0] for row in result]
            print(f"workspaces columns: {cols}")

            new_ws_cols = {
                "job_name": "TEXT",
                "emoji": "TEXT",
                "color": "TEXT"
            }

            for col_name, col_type in new_ws_cols.items():
                if col_name not in cols:
                    print(f"Adding {col_name} to workspaces...")
                    conn.execute(text(f"ALTER TABLE workspaces ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"Successfully added {col_name} to workspaces.")
                else:
                    print(f"{col_name} already exists in workspaces.")

            print("Workspace migration complete! 🎉")
            
            # Check users columns
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users'"))
            cols = [row[0] for row in result]
            print(f"users columns: {cols}")

            if "hashed_password" not in cols:
                print("Adding hashed_password to users...")
                conn.execute(text("ALTER TABLE users ADD COLUMN hashed_password TEXT"))
                conn.commit()
                print("Successfully added hashed_password to users.")
            else:
                print("hashed_password already exists in users.")

            # Check schedule_events table
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name='schedule_events'
            """))
            has_schedule_events = result.first() is not None

            if not has_schedule_events:
                print("Creating schedule_events table...")
                conn.execute(text("""
                    CREATE TABLE schedule_events (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        title VARCHAR NOT NULL,
                        event_type VARCHAR NOT NULL,
                        description TEXT,
                        start_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        end_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                    )
                """))
                conn.execute(text("CREATE INDEX ix_schedule_events_id ON schedule_events (id)"))
                conn.execute(text("CREATE INDEX ix_schedule_events_user_id ON schedule_events (user_id)"))
                conn.execute(text("CREATE INDEX ix_schedule_events_start_time ON schedule_events (start_time)"))
                conn.execute(text("CREATE INDEX ix_schedule_events_end_time ON schedule_events (end_time)"))
                conn.commit()
                print("Successfully created schedule_events table.")
            else:
                print("schedule_events table already exists.")

            dashboard_tables = {
                "dashboard_user_progress": """
                    CREATE TABLE dashboard_user_progress (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                        completed_interviews INTEGER NOT NULL DEFAULT 0,
                        avg_hr_score INTEGER,
                        avg_technical_score INTEGER,
                        cv_ats_score INTEGER NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                    )
                """,
                "activity_logs": """
                    CREATE TABLE activity_logs (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        title VARCHAR NOT NULL,
                        description TEXT,
                        activity_type VARCHAR NOT NULL DEFAULT 'general',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                    )
                """,
                "skill_scores": """
                    CREATE TABLE skill_scores (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        skill_name VARCHAR NOT NULL,
                        category VARCHAR,
                        score INTEGER NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                    )
                """,
                "weekly_goals": """
                    CREATE TABLE weekly_goals (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        week_start DATE NOT NULL,
                        interviews_target INTEGER NOT NULL DEFAULT 5,
                        quizzes_target INTEGER NOT NULL DEFAULT 2,
                        practice_minutes_target INTEGER NOT NULL DEFAULT 300,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                    )
                """,
            }

            for table_name, create_sql in dashboard_tables.items():
                result = conn.execute(text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name=:table_name
                """), {"table_name": table_name})
                if result.first() is None:
                    print(f"Creating {table_name} table...")
                    conn.execute(text(create_sql))
                    conn.execute(text(f"CREATE INDEX ix_{table_name}_id ON {table_name} (id)"))
                    conn.execute(text(f"CREATE INDEX ix_{table_name}_user_id ON {table_name} (user_id)"))
                    if table_name == "activity_logs":
                        conn.execute(text("CREATE INDEX ix_activity_logs_created_at ON activity_logs (created_at)"))
                    if table_name == "weekly_goals":
                        conn.execute(text("CREATE INDEX ix_weekly_goals_week_start ON weekly_goals (week_start)"))
                    conn.commit()
                    print(f"Successfully created {table_name}.")
                else:
                    print(f"{table_name} table already exists.")

            print("Final migration complete! 🚀")
<<<<<<< HEAD
>>>>>>> main
=======
>>>>>>> 2d87720d6b34db803ce588b1ac46da4384722c3c
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise e

if __name__ == "__main__":
    load_dotenv()
    run_migration()
