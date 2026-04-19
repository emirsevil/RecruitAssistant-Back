import json

from utils.ai_client import get_ai_client, get_model_name


def generate_interview_questions(job_description: str, categories: str, difficulty: str, interview_type: str) -> list:
    if interview_type == "hr":
        system_prompt = _build_hr_prompt(job_description, difficulty)
    else:
        system_prompt = _build_technical_prompt(job_description, categories, difficulty)

    try:
        client = get_ai_client()
        model = get_model_name(tier="fast")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Generate the interview questions."}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("questions", [])
    except Exception as e:
        print(f"Error parsing AI response: {e}")
        return []


def _build_hr_prompt(job_description: str, difficulty: str) -> str:
    """Build the prompt for HR / Behavioral interviews — no categories needed."""
    return f"""
You are an expert HR interviewer specializing in behavioral and situational interviews.
Your task is to generate {difficulty} level HR / Behavioral mock interview questions.

The candidate is interviewing for a role with the following description:
{job_description}

MANDATORY RULES:
1. Generate EXACTLY 5 questions total.
2. Focus on behavioral and situational questions that assess:
   - Cultural fit and teamwork
   - Problem-solving and conflict resolution
   - Communication and leadership skills
   - Motivation, career goals, and self-awareness
   - Adaptability and handling pressure
3. Analyze the job description carefully to tailor questions to the specific role and industry.
   For example, if the JD mentions "fast-paced environment", ask about handling pressure.
   If it mentions "cross-functional teams", ask about collaboration.
4. Use the STAR method structure where appropriate (Situation, Task, Action, Result).
5. Do NOT ask technical/coding questions. Focus purely on soft skills, personality, and behavioral aspects.
6. Return ONLY a valid JSON object with a "questions" key containing an array of objects. Each object must have:
   - "id": an integer starting from 1
   - "question": the text of the interview question
   - "topic": a short string representing the HR topic (e.g. "Teamwork", "Leadership", "Conflict Resolution", "Motivation", "Adaptability")
   - "aiResponse": a boolean, set to true for intro/ice-breaker questions, false for regular questions.

Example format:
{{
  "questions": [
    {{ "id": 1, "question": "...", "topic": "...", "aiResponse": true }},
    {{ "id": 2, "question": "...", "topic": "...", "aiResponse": false }}
  ]
}}
    """


def _build_technical_prompt(job_description: str, categories: str, difficulty: str) -> str:
    """Build the prompt for Technical interviews — uses categories."""
    category_list = [c.strip() for c in categories.split(",") if c.strip()]
    num_categories = min(len(category_list), 5)
    num_extra = 5 - num_categories

    if num_extra > 0:
        extra_instruction = f"""
Additionally, generate {num_extra} more question(s) based on the job description on topics DIFFERENT from the categories above.
These extra questions should cover other relevant skills, tools, or concepts mentioned in the job description.
"""
    else:
        extra_instruction = ""

    return f"""
You are an expert technical interviewer.
Your task is to generate {difficulty} level technical mock interview questions.

The candidate is interviewing for a role with the following description:
{job_description}

MANDATORY RULES:
1. Generate EXACTLY 5 questions total.
2. Generate exactly 1 question for EACH of these categories/topics: {categories}.
   That gives you {num_categories} question(s) from the categories.
{extra_instruction}
3. Return ONLY a valid JSON object with a "questions" key containing an array of objects. Each object must have:
   - "id": an integer starting from 1
   - "question": the text of the interview question
   - "topic": a short string representing the category or topic of the question
   - "aiResponse": a boolean, set to true if you expect the AI to respond or introduce, typically false for regular questions.

Example format:
{{
  "questions": [
    {{ "id": 1, "question": "...", "topic": "...", "aiResponse": true }},
    {{ "id": 2, "question": "...", "topic": "...", "aiResponse": false }}
  ]
}}
    """
