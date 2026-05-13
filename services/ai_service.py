from groq import AsyncGroq
from models.models import Question
from config import GROQ_API_KEY

client = AsyncGroq(api_key=GROQ_API_KEY)


async def get_ai_advice(wrong_questions: list[Question]) -> str:
    if not wrong_questions:
        return "Zo'r! Barcha savollarga to'g'ri javob berdingiz. Shunday davom eting! 🎉"

    topics_text = "\n".join(
        f"- {q.text[:80]}..." for q in wrong_questions
    )

    prompt = (
        "Sen o'zbek tilida dars beruvchi yordamchisan.\n"
        "Quyidagi savollarda o'quvchi xato qildi:\n\n"
        f"{topics_text}\n\n"
        "Faqat mavzu darajasida 3-4 ta qisqa tavsiya ber. "
        "Qaysi savol xato ekanini AYTMA. "
        "Faqat o'zbek tilida yoz."
    )

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.5,
    )

    return response.choices[0].message.content.strip()


async def parse_questions_with_ai(raw_text: str) -> list[dict]:
    prompt = (
        "Quyidagi matndan test savollarini JSON formatida chiqar.\n"
        "Format: [{\"text\": \"...\", \"option_a\": \"...\", \"option_b\": \"...\", "
        "\"option_c\": \"...\", \"option_d\": \"...\"}]\n"
        "Faqat JSON qaytар, boshqa hech narsa yozma.\n\n"
        f"{raw_text[:3000]}"
    )

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.1,
    )

    import json
    text = response.choices[0].message.content.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    return json.loads(text[start:end])
