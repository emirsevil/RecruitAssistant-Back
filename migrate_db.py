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
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise e

if __name__ == "__main__":
    load_dotenv()
    run_migration()
