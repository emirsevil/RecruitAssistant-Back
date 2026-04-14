import json
import logging
from typing import List, Dict

from utils.ai_client import get_ai_client, get_model_name

logger = logging.getLogger(__name__)

def extract_skills_from_job_description(job_desc: str) -> List[str]:
    """
    Analyzes the JD and returns a list of distinct technical skills/topics.
    """
    if not job_desc:
        return []

    prompt = f"""
    Analyze the following Job Description and extract the top 10 most important technical skills, programming languages, tools, or frameworks mentioned.
    Return ONLY a JSON list of strings. No markdown formatting.
    
    Job Description:
    {job_desc}
    """

    try:
        client = get_ai_client()
        model = get_model_name(tier="default")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        
        # Cleanup potential markdown
        if "```json" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[-1].split("```")[0].strip()
            
        skills = json.loads(content)
        return skills if isinstance(skills, list) else []
    except Exception as e:
        logger.error(f"Error extracting skills: {e}")
        return []

def generate_targeted_quizzes(job_desc: str, selections: List[Dict], language: str = "tr") -> List[Dict]:
    """
    Generates quizzes for specific skills and difficulties.
    'selections' is a list of { "title": "SkillName", "difficulties": ["Easy", "Medium"] }
    """
    if not job_desc or not selections:
        return []

    # Construct a detailed prompt for targeted generation
    selections_str = json.dumps(selections, indent=2)
    
    lang_instruction = f"MANDATORY: Generate all quiz content (questions, options, and correct answers) strictly in {language.upper()}."
    if language.lower() == "tr":
        lang_instruction += " (Türkçe karakterleri düzgün kullan)."

    prompt = f"""
    You are an expert Technical Interviewer.
    Generate technical quiz questions based on the Job Description and the specific Skill/Difficulty selections provided below.
    
    {lang_instruction}
    
    Job Description:
    {job_desc}
    
    Target Selections:
    {selections_str}
    
    Requirements:
    1. For EACH difficulty selected for a skill, generate exactly 5 to 8 unique questions.
    2. Each question MUST have 4 options and 1 correct_answer.
    3. MANDATORY: The output must be a valid JSON array of objects with this structure:
    [
      {{
        "title": "SkillName",
        "difficulty": "Easy",
        "questions": [
          {{
            "question": "...",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "Actual correct option text"
          }}
        ]
      }}
    ]
    4. Difficulty Guidelines:
       - Easy: Basic syntax, terminology.
       - Medium: Real-world usage, common patterns.
       - Hard: Optimizations, edge cases, internals.
       
    Return ONLY the raw JSON array. No markdown, no conversation.
    """

    try:
        client = get_ai_client()
        model = get_model_name(tier="default")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        
        if "```json" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[-1].split("```")[0].strip()
            
        raw_data = json.loads(content)
        return raw_data if isinstance(raw_data, list) else []
    except Exception as e:
        logger.error(f"Error generating targeted quizzes: {e}")
        return []


def generate_quizzes_from_job_description(job_desc: str, language: str = "tr") -> List[Dict]:
    """Legacy function, now using gpt-4o for better quality."""
    skills = extract_skills_from_job_description(job_desc)
    # Just pick top 3 for auto-generation if this is still used
    subset = [{"title": s, "difficulties": ["Medium"]} for s in skills[:3]]
    return generate_targeted_quizzes(job_desc, subset, language=language)
