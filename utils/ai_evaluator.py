import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def evaluate_interview(qa_pairs: list, job_description: str, difficulty: str) -> dict:
    """
    Evaluates all question-answer pairs in a single OpenAI call.
    Returns per-question scores/feedback and an overall score.
    """
    
    qa_text = ""
    for i, qa in enumerate(qa_pairs):
        qa_text += f"\nQuestion {i+1} (Topic: {qa['topic']}): {qa['question']}\nCandidate's Answer: {qa['answer']}\n"

    system_prompt = f"""
You are an expert interviewer evaluating a candidate's mock interview performance.
The candidate interviewed for a role with this job description:
{job_description}

Difficulty level: {difficulty}

Here is the full interview transcript:
{qa_text}

Evaluate EACH answer individually and also provide an overall assessment.
Consider the full context — notice patterns like repetition across answers, 
consistency, improvement, and depth progression.

Return ONLY a valid JSON object with this exact structure:
{{
  "results": [
    {{
      "question": "the original question text",
      "topic": "the topic string",
      "score": 75,
      "feedback": "2-3 sentences of constructive feedback"
    }}
  ],
  "overall_score": 78,
  "overall_feedback": "2-3 sentences summarizing the overall interview performance"
}}

Scoring guide:
- 90-100: Exceptional, very thorough answer with great examples
- 75-89: Good answer, covers key points
- 60-74: Adequate but missing depth or examples
- 40-59: Weak, vague or off-topic
- 0-39: Very poor or no meaningful answer
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Evaluate the interview answers."}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Error evaluating interview: {e}")
        return {"results": [], "overall_score": 0, "overall_feedback": "Evaluation failed."}
