import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_interview_questions(job_description: str, categories: str, difficulty: str, interview_type: str) -> list:
    system_prompt = f"""
You are an expert technical and HR interviewer.
Your task is to generate {difficulty} level {interview_type} mock interview questions.
The candidate is interviewing for a role with the following description:
{job_description}

Focus on these categories/topics: {categories}.

Generate exactly 3 to 5 questions.
Return ONLY a valid JSON object with a "questions" key containing an array of objects. Each object must have:
- "id": an integer starting from 1
- "question": the text of the interview question
- "topic": a short string representing the category or topic of the question
- "aiResponse": a boolean, set to true if you expect the AI to respond or introduce, typically false for regular questions. E.g. true for intro, false for others.

Example format:
{{
  "questions": [
    {{ "id": 1, "question": "Tell me about yourself.", "topic": "Introduction", "aiResponse": true }},
    {{ "id": 2, "question": "How does React work?", "topic": "React", "aiResponse": false }}
  ]
}}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Generate the interview questions."}
            ],
            response_format={ "type": "json_object" }
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("questions", [])
    except Exception as e:
        print(f"Error parsing AI response: {e}")
        return []
