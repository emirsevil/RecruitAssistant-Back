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

            print("Database migration complete! 🎉")
    except Exception as e:
        print("Error during migration:", e)

if __name__ == "__main__":
    load_dotenv()
    run_migration()
