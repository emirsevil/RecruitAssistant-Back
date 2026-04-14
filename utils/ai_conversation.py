"""
LLM wrapper for live conversational interview pacing in Turkish.

Unlike ai_interviewer.py (generates questions upfront) and ai_evaluator.py (evaluates after),
this module handles mid-interview dialogue — the LLM decides whether to follow up, move on, or wrap up.
"""
import json

from utils.ai_client import get_ai_client, get_model_name

INTERVIEWER_SYSTEM_PROMPT = """
Sen deneyimli ve profesyonel bir mülakatçısın. Türkçe konuşuyorsun.
Gerçek bir iş mülakatı yürütüyorsun — samimi ama profesyonel ol.

Kurallar:
1. Her zaman Türkçe cevap ver.
2. Kısa ve öz ol. Gereksiz övgü veya yapay nezaket yapma.
3. Gerçek bir mülakatçı gibi davran — aşırı sevecen veya yapay olma.
4. Adayın cevabını kısaca değerlendir (en fazla 1 cümle geçiş) ve aksiyonu al.
5. Her soru için en fazla 1-2 takip sorusu sor, sonra bir sonraki soruya geç.
6. Aday cevap vermezse veya "(Pas geçildi)" derse, yorum yapmadan geç.
7. Takip sorularında adayın cevabındaki eksik veya belirsiz noktaları sorgula.
8. Her soruyu kesinlikle oku, diğer soruya geçeceksen geçiş cümlesi kullandıktan sonra diğer soruyu kesinlikle oku.
9. Her sorudan sonra aday tarafından verilen cevabı özetleme veya tekrar etme.

Örnek geçiş cümleleri (kısa tut bunlarla sınırlı kalmak zorunda değilsin):
- "Anladım. Peki şunu sormak istiyorum..."
- "Tamam. Şimdi farklı bir konuya geçelim..."
- "Bu konuyu biraz daha açar mısınız?"
- "Anlaşıldı. Bir sonraki soruya geçiyorum."

YAPMA:
- "Harika bir cevap!", "Çok güzel söylediniz!", "Muhteşem!" gibi yapay övgüler
- Uzun ve gereksiz geçiş cümleleri
- Adayı aşırı motive etmeye çalışmak

Aksiyonlar:
- "follow_up": Cevaptaki eksik/belirsiz bir noktayı sorgula
- "next_question": Sonraki soruya geç
- "wrap_up": Tüm sorular bitti, mülakatı kapat

SADECE geçerli bir JSON nesnesi döndür:
{{
  "response_text": "Mülakatçının kısa Türkçe cevabı...",
  "action": "follow_up" | "next_question" | "wrap_up"
}}
"""

INTRO_SYSTEM_PROMPT = """
Sen profesyonel bir mülakat yapay zekasısın. Türkçe konuşuyorsun.
Mülakata başlarken, kendini kısaca tanıt ve adayı karşıla.
Ardından ilk soruyu sor.

Kısa ve doğal ol — 2-3 cümle yeterli.

Pozisyon açıklaması:
{job_description}

Zorluk seviyesi: {difficulty}
Mülakat türü: {interview_type}

İlk soru: {first_question}

SADECE mülakatçının söyleyeceği Türkçe metni döndür, başka bir şey yazma.
"""

QUESTION_GENERATION_PROMPT = """
Sen uzman bir teknik ve İK mülakatçısın. Türkçe sorular üret.
Görevin, aşağıdaki pozisyon için {difficulty} seviyesinde {interview_type} mülakat soruları üretmek.

Pozisyon açıklaması:
{job_description}

Odaklanılacak konular/kategoriler: {categories}

Tam olarak 3 ile 5 arası soru üret.
SADECE geçerli bir JSON nesnesi döndür. Her soru Türkçe olmalı:
{{
  "questions": [
    {{ "id": 1, "question": "Kendinizden bahseder misiniz?", "topic": "Giriş", "aiResponse": true }},
    {{ "id": 2, "question": "React nasıl çalışır?", "topic": "React", "aiResponse": false }}
  ]
}}
"""


def generate_turkish_questions(job_description: str, categories: str, difficulty: str, interview_type: str) -> list:
    """Generate interview questions in Turkish."""
    system_prompt = QUESTION_GENERATION_PROMPT.format(
        job_description=job_description,
        categories=categories,
        difficulty=difficulty,
        interview_type=interview_type
    )

    try:
        client = get_ai_client()
        model = get_model_name(tier="fast")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Mülakat sorularını üret."}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("questions", [])
    except Exception as e:
        print(f"Error generating Turkish questions: {e}")
        return []


def generate_intro_text(job_description: str, difficulty: str, interview_type: str, first_question: str) -> str:
    """Generate the interviewer's opening statement in Turkish."""
    system_prompt = INTRO_SYSTEM_PROMPT.format(
        job_description=job_description,
        difficulty=difficulty,
        interview_type=interview_type,
        first_question=first_question
    )

    try:
        client = get_ai_client()
        model = get_model_name(tier="fast")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Mülakata başla."}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating intro: {e}")
        return f"Merhaba, mülakata hoş geldiniz. İlk sorumuz: {first_question}"


def generate_interviewer_response(
    conversation_history: list,
    current_question: dict,
    remaining_questions: list,
    job_description: str,
    difficulty: str,
    follow_up_count: int = 0
) -> dict:
    """
    Generate the interviewer's next response based on the conversation so far.
    
    Returns:
        {
            "response_text": "Turkish interviewer response...",
            "action": "follow_up" | "next_question" | "wrap_up"
        }
    """
    context_msg = f"""
Pozisyon: {job_description}
Zorluk: {difficulty}
Mevcut soru: {current_question.get('question', '')} (Konu: {current_question.get('topic', '')})
Bu soru için yapılan takip sayısı: {follow_up_count}
Kalan soru sayısı: {len(remaining_questions)}
{"Kalan sorular: " + json.dumps([q.get('question', '') for q in remaining_questions], ensure_ascii=False) if remaining_questions else "Bu son soruydu."}
"""

    messages = [
        {"role": "system", "content": INTERVIEWER_SYSTEM_PROMPT},
        {"role": "user", "content": context_msg}
    ]
    
    # Add conversation history
    for entry in conversation_history:
        role = "assistant" if entry.get("role") == "interviewer" else "user"
        messages.append({"role": role, "content": entry.get("text", "")})

    try:
        client = get_ai_client()
        model = get_model_name(tier="fast")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
        # Force next_question if too many follow-ups
        if follow_up_count >= 2 and result.get("action") == "follow_up":
            result["action"] = "next_question"
        
        # Force wrap_up if no remaining questions and action is next_question
        if not remaining_questions and result.get("action") == "next_question":
            result["action"] = "wrap_up"

        return {
            "response_text": result.get("response_text", "Devam edelim."),
            "action": result.get("action", "next_question")
        }
    except Exception as e:
        print(f"Error generating interviewer response: {e}")
        return {
            "response_text": "Teşekkürler. Devam edelim.",
            "action": "next_question" if remaining_questions else "wrap_up"
        }
