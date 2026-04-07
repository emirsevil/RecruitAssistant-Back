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
    Task: Analyze the provided Job Description and extract ALL distinct core technical skills, programming languages, or frameworks mentioned (e.g., Python, SQL, React, AWS, Docker). 
    
    Requirements:
    1. For EACH identified skill, you MUST generate exactly 3 separate quizzes based on difficulty: "Easy", "Medium", and "Hard".
    2. Each quiz MUST contain between 5 and 9 deep, technical questions.
    3. Provide exactly four options for each question as a JSON list of strings.
    4. Specify the 'correct_answer' which must match one of the options exactly.
    5. MANDATORY: Every question must be UNIQUE. Do not repeat questions or concepts.
    6. Difficulty criteria:
       - Easy: Basic concepts, syntax, and definitions.
       - Medium: Applied knowledge, common patterns, and architecture.
       - Hard: Advanced edge cases, internals, and optimization.

    Output ONLY a valid JSON array of Quiz objects. Do not include markdown formatting like ```json. Use this exact schema:
    [
      {{
        "title": "SkillName",
        "difficulty": "Easy",
        "questions": [
          {{
            "question": "...",
            "options": ["...", "...", "...", "..."],
            "correct_answer": "..."
          }}
          // Add 5 to 9 questions here
        ]
      }},
      {{
        "title": "SkillName",
        "difficulty": "Medium",
        "questions": [ ... ] // Add 5 to 9 questions here
      }},
      {{
        "title": "SkillName",
        "difficulty": "Hard",
        "questions": [ ... ] // Add 5 to 9 questions here
      }}
      // Repeat these 3 quiz objects (Easy, Medium, Hard) for EVERY skill found in the job description.
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
