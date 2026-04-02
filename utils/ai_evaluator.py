import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def evaluate_interview(qa_pairs: list, job_description: str, difficulty: str, language: str = "en") -> dict:
    """
    Evaluates all question-answer pairs in a single OpenAI call.
    Returns per-question scores/feedback and an overall score.
    """
    
    qa_text = ""
    for i, qa in enumerate(qa_pairs):
        if language == "tr":
            qa_text += f"\nSoru {i+1} (Konu: {qa['topic']}): {qa['question']}\nAdayın Cevabı: {qa['answer']}\n"
        else:
            qa_text += f"\nQuestion {i+1} (Topic: {qa['topic']}): {qa['question']}\nCandidate's Answer: {qa['answer']}\n"

    if language == "tr":
        system_prompt = f"""
Sen uzman bir mülakatçısın ve bir adayın mülakat performansını değerlendiriyorsun.
Tüm değerlendirmeleri ve geri bildirimleri TÜRKÇE yaz.

Aday şu pozisyon için mülakata girdi:
{job_description}

Zorluk seviyesi: {difficulty}

Mülakat transkripti:
{qa_text}

Gerçek bir mülakatçı gibi son derece KATI ve GERÇEKÇİ değerlendir. 
Adayın "bilmiyorum", "hatırlamıyorum" dediği, konuyu geçiştirdiği veya soruyu "(Pas geçildi)" diyerek atladığı durumlarda puanı acımasızca KIR (0-20 arası).
Şişirilmiş, cömert puanlar verme. Aday sadece gerçekten tatmin edici ve teknik olarak doğru bir cevap verdiyse yüksek puan ver.

Tekrar eden kalıpları, tutarlılığı, gelişimi ve derinliği göz önünde bulundur.

SADECE geçerli bir JSON nesnesi döndür:
{{
  "results": [
    {{
      "question": "orijinal soru metni",
      "topic": "konu",
      "score": 75,
      "feedback": "2-3 cümle yapıcı Türkçe geri bildirim"
    }}
  ],
  "overall_score": 78,
  "overall_feedback": "2-3 cümle genel Türkçe mülakat değerlendirmesi"
}}

Puanlama (KATI KURALLAR):
- 90-100: Olağanüstü, derin teknik bilgi içeren, harika örneklerle desteklenmiş kusursuz cevap (Çok nadir verilmelidir)
- 70-89: İyi, ana noktaları kapsayan ancak ufak eksikleri olan cevap
- 40-69: Vasat, yüzeysel, çok az detay içeren sıkıcı cevap
- 15-39: Konu dışı, hatalı veya soruyu geçiştirmeye çalışan zayıf cevap
- 0-14: "Bilmiyorum", "hatırlamıyorum", soruyu pas geçme veya tamamen sessiz kalma (Doğrudan bu aralıkta puanla)
"""
    else:
        system_prompt = f"""
You are an expert interviewer evaluating a candidate's mock interview performance.
The candidate interviewed for a role with this job description:
{job_description}

Difficulty level: {difficulty}

Here is the full interview transcript:
{qa_text}

Evaluate EACH answer strictly and realistically, like a tough real-world tech recruiter.
If the candidate says "I don't know", "I can't remember", gives evasive/vague answers, or passes the question, PENALIZE the score heavily (0-20 range). 
Do NOT be generous. Only award high scores if the answer is technically accurate, well-structured, and highly satisfying.

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

Scoring guide (STRICT RULES):
- 90-100: Exceptional, flawless answer with deep technical insight and great examples (Should be very rare)
- 70-89: Good solid answer, covers key points but lacks minor depth
- 40-69: Mediocre, superficial answer lacking concrete details
- 15-39: Off-topic, factually wrong, or evasive answer
- 0-14: Candidate said "I don't know", completely passed the question, or remained silent (Score immediately in this range)
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
