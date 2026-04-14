import json

from utils.ai_client import get_ai_client, get_model_name

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
    {{ "id": 1, "question": "...", "topic": "...", "aiResponse": true }},
    {{ "id": 2, "question": "...", "topic": "...", "aiResponse": false }}
  ]
}}
    """

    try:
        client = get_ai_client()
        model = get_model_name(tier="fast")
        response = client.chat.completions.create(
<<<<<<< HEAD
            model="gpt-3.5-turbo",
=======
            model=model,
>>>>>>> main
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
