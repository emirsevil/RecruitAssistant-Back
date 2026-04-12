import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from database import engine

def run_migration():
    print("Connecting to database...")
    try:
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

            print("Final migration complete! 🚀")
    except Exception as e:
        print("Error during migration:", e)

if __name__ == "__main__":
    load_dotenv()
    run_migration()
