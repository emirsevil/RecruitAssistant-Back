import json
import logging
from typing import List, Dict

from utils.ai_client import get_ai_client, get_model_name

logger = logging.getLogger(__name__)

async def extract_skills_from_job_description(job_desc: str) -> List[str]:
    """
    Analyzes the JD and returns a list of distinct technical skills/topics.
    """
    if not job_desc:
        return []

    prompt = f"""
    Analyze the following Job Description and extract the top 10 most important technical skills, programming languages, tools, or frameworks mentioned.
    MANDATORY: Keep the skill names in their original language as found in the Job Description or their standard technical form (e.g., 'Software Development Life Cycle'). DO NOT translate technical terms into another language.
    Return ONLY a JSON list of strings. No markdown formatting.
    
    Job Description:
    {job_desc}
    """

    try:
        from utils.ai_client import get_async_ai_client
        client = get_async_ai_client()
        model = get_model_name(tier="default")
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        import re
        content = response.choices[0].message.content.strip()
        
        # Robust JSON extraction
        match = re.search(r'(\[.*\])', content, re.DOTALL)
        if match:
            clean_content = match.group(1).strip()
        else:
            # Fallback to simple cleaning
            clean_content = content
            if "```json" in clean_content:
                clean_content = clean_content.split("```json")[-1].split("```")[0].strip()
            elif "```" in clean_content:
                clean_content = clean_content.split("```")[-1].split("```")[0].strip()
            
        skills = json.loads(clean_content, strict=False)
        return skills if isinstance(skills, list) else []
    except Exception as e:
        logger.error(f"Error extracting skills: {e}")
        return []

async def generate_targeted_quizzes(job_desc: str, selections: List[Dict], language: str = "tr") -> List[Dict]:
    """
    Generates quizzes for specific skills and difficulties in parallel.
    'selections' is a list of { "title": "SkillName", "difficulties": ["Easy", "Medium"] }
    """
    if not job_desc or not selections:
        return []

    from utils.ai_client import get_async_ai_client
    import asyncio
    
    client = get_async_ai_client()
    model = get_model_name(tier="default")
    
    lang_instruction = f"MANDATORY: Generate all quiz content (questions, options, and correct answers) strictly in {language.upper()}."
    if language.lower() == "tr":
        lang_instruction += " (Türkçe karakterleri düzgün kullan)."

    async def _generate_single_quiz(skill_name: str, diff: str) -> List[Dict]:
        """Helper to generate a single quiz group for one skill/difficulty."""
        logger.info(f"Generating {diff} quiz for {skill_name} in parallel...")
        
        prompt = f"""
        You are an expert Technical Interviewer.
        Generate technical quiz questions based on the Job Description and the specific Skill/Difficulty provided.
        
        {lang_instruction}
        
        Job Description:
        {job_desc}
        
        Target Topic: {skill_name}
        Difficulty: {diff}
        
        Requirements:
        1. Generate exactly 5 to 8 unique questions for this difficulty.
        2. Each question MUST have 4 options and 1 correct_answer.
        3. MANDATORY: The "title" field in the JSON MUST be exactly "{skill_name}". DO NOT translate or modify the skill name.
        4. MANDATORY: The output must be a valid JSON array of objects with this structure:
        [
          {{
            "title": "{skill_name}",
            "difficulty": "{diff}",
            "questions": [
              {{
                "question": "...",
                "options": ["A", "B", "C", "D"],
                "correct_answer": "Actual correct option text"
              }}
            ]
          }}
        ]
        
        Return ONLY the raw JSON array. No markdown, no conversation.
        """
        
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content.strip()
            
            # Robust JSON extraction for the specific quiz group
            import re
            match = re.search(r'(\[.*\])', content, re.DOTALL)
            if match:
                clean_content = match.group(1).strip()
            else:
                clean_content = content
                if "```json" in clean_content:
                    clean_content = clean_content.split("```json")[-1].split("```")[0].strip()
                elif "```" in clean_content:
                    clean_content = clean_content.split("```")[-1].split("```")[0].strip()
                
            data = json.loads(clean_content, strict=False)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Error generating single quiz for {skill_name} {diff}: {e}")
            # Log raw content for debugging on parse failure
            logger.debug(f"Raw content that failed to parse: {content}")
            return []

    # Flatten selections into individual (skill, difficulty) tasks
    tasks = []
    for sel in selections:
        skill_name = sel.get("title", "Technical Quiz")
        diffs = sel.get("difficulties", ["Medium"])
        for d in diffs:
            tasks.append(_generate_single_quiz(skill_name, d))

    if not tasks:
        return []

    # Run all tasks in parallel
    all_results = await asyncio.gather(*tasks)
    
    # Flatten and combine all generated groups
    final_output = []
    for result_list in all_results:
        final_output.extend(result_list)
        
    return final_output


async def generate_quizzes_from_job_description(job_desc: str, language: str = "tr") -> List[Dict]:
    """Legacy function, now using async Targeted flow."""
    skills = await extract_skills_from_job_description(job_desc)
    # Just pick top 3 for auto-generation if this is still used
    subset = [{"title": s, "difficulties": ["Medium"]} for s in skills[:3]]
    return await generate_targeted_quizzes(job_desc, subset, language=language)
