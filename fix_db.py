import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def fix_database_conflicts():
    """
    Specifically cleans up quiz-related tables to resolve IntegrityErrors 
    during migration. This is a surgical cleanup, not a full reset.
    """
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("Error: DATABASE_URL not found in .env file.")
        return

    print("Connecting to database for surgical cleanup...")
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            print("Cleaning up quiz-related tables to allow migration...")
            
            # 1. Truncate quiz_scores (has foreign keys to quizzes)
            conn.execute(text("TRUNCATE TABLE quiz_scores RESTART IDENTITY CASCADE"))
            print("- Cleared quiz_scores")
            
            # 2. Truncate questions (has foreign keys to quizzes)
            conn.execute(text("TRUNCATE TABLE questions RESTART IDENTITY CASCADE"))
            print("- Cleared questions")
            
            # 3. Truncate quizzes
            conn.execute(text("TRUNCATE TABLE quizzes RESTART IDENTITY CASCADE"))
            print("- Cleared quizzes")
            
            # 4. Optional: Reset alembic version if teammate is stuck 
            # (only uncomment if they are having 'alembic_version' sync issues)
            # conn.execute(text("DELETE FROM alembic_version"))
            
            conn.commit()
            print("\nCleanup successful! 🎉 You can now run 'python main.py' or 'alembic upgrade head' without errors.")
            
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    fix_database_conflicts()
