import os
from openai import OpenAI
from typing import List, Dict

# Ensure the OpenAI API key is set in the environment
def generate_quizzes_from_job_description(job_desc: str) -> List[Dict]:
    """Generate a list of quiz questions based on a job description.

    Each item in the returned list is a dict with keys:
        - question: str
        - options: List[str]
        - correct_answer: str
    """
    if not job_desc:
        return []

    # Initialize client inside the function to prevent top-level errors if API key is missing
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set.")
        return []
    
    client = OpenAI(api_key=api_key)
    # Prompt for the LLM
    prompt = f"""You are an expert Technical IT Interviewer. 
    Task: Analyze the provided Job Description and identify ALL distinct core technical skills, programming languages, or frameworks mentioned (e.g., Python, SQL, React, AWS, Docker). 
    
    Requirements for EACH identified skill:
    1. Generate a SEPARATE set of 5 to 7 technical questions.
    2. Questions must be deep and technical (testing actual knowledge, not just definitions).
    3. Provide exactly four options for each question as a JSON list of strings.
    4. Specify the 'correct_answer' which must match one of the options exactly.
    5. Each question object must include a 'title' field containing the name of the skill (e.g., "Python", "SQL").
    6. MANDATORY: Each question must be UNIQUE. Do not repeat the same question or concept twice for the same skill.
    7. Each question object must include a 'difficulty' field with one of these values: "Easy", "Medium", or "Hard".
       - For each skill, include a balanced mix: roughly 2 Easy, 2-3 Medium, and 1-2 Hard questions.
       - Easy: basic concepts and definitions
       - Medium: applied knowledge and common patterns
       - Hard: advanced edge cases, internals, and optimization

    Output ONLY a valid JSON array containing all questions for all skills. 
    Format:
    [
      {{"title": "SkillName1", "difficulty": "Easy", "question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "..."}},
      {{"title": "SkillName1", "difficulty": "Medium", "question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "..."}},
      {{"title": "SkillName1", "difficulty": "Hard", "question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "..."}},
      ... (5-7 questions per skill with mixed difficulties)
    ]

    Job Description:
    {job_desc}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        import json
        
        # LLMs sometimes wrap JSON in markdown blocks
        if "```json" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[-1].split("```")[0].strip()
            
        quizzes = json.loads(content)
        validated = []
        for q in quizzes:
            title = q.get("title", "Technical Quiz")
            options = q.get("options")
            if isinstance(options, dict):
                sorted_keys = sorted(options.keys())
                options = [options[k] for k in sorted_keys]
            
            if q.get("question") and isinstance(options, list) and q.get("correct_answer"):
                q["title"] = title
                q["options"] = options
                difficulty = q.get("difficulty", "Medium")
                if difficulty not in ("Easy", "Medium", "Hard"):
                    difficulty = "Medium"
                q["difficulty"] = difficulty
                validated.append(q)
        return validated
    except Exception as e:
        # In case of any error, return empty list to avoid breaking the API
        print(f"Error generating quizzes: {e}")
        return []
