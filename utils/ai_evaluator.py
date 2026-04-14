import json

from utils.ai_client import get_ai_client, get_model_name

def evaluate_interview(qa_pairs: list, job_description: str, difficulty: str) -> dict:
    """
    Evaluates all question-answer pairs in a single LLM call.
    Returns per-question scores/feedback and an overall score.
    """
    
    qa_text = ""
    for i, qa in enumerate(qa_pairs):
        qa_text += f"\nSoru {i+1} (Konu: {qa['topic']}): {qa['question']}\nAdayın Cevabı: {qa['answer']}\n"

    system_prompt = f"""
Sen uzman bir mülakatçısın ve bir adayın mülakat performansını değerlendiriyorsun.
TÜM değerlendirmeleri ve geri bildirimleri (results, feedback, overall_feedback) MUTLAKA TÜRKÇE yaz.

Aday şu pozisyon için mülakata girdi:
{job_description}

Zorluk seviyesi: {difficulty}

Mülakat transkripti:
{qa_text}

Gerçek bir mülakatçı gibi son derece KATI ve GERÇEKÇİ değerlendir. 
Adayın "bilmiyorum", "hatırlamıyorum" dediği, konuyu geçiştirdiği veya soruyu "(Pas geçildi)" diyerek atladığı durumlarda puanı acımasızca KIR (0-20 arası).
Şişirilmiş, cömert puanlar verme. Aday sadece gerçekten tatmin edici ve teknik olarak doğru bir cevap verdiyse yüksek puan ver.

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
                {"role": "user", "content": "Evaluate the interview answers."}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Error evaluating interview: {e}")
        return {"results": [], "overall_score": 0, "overall_feedback": "Evaluation failed."}
