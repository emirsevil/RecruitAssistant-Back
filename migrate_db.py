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
    except Exception as e:
        print("Error during migration:", e)

if __name__ == "__main__":
    load_dotenv()
    run_migration()
