# RecruitAssistant-Back


# To run
pip install -r requirements.txt
uvicorn main:app --reload

# To update database
alembic revision --autogenerate -m "Describe your changes here"
alembic upgrade head
