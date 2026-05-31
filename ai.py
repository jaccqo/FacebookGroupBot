import os
import json
from datetime import datetime
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

FB_NAME = os.getenv("FB_NAME", "John")
FB_AGE = os.getenv("FB_AGE", "25")
FB_LOCATION = os.getenv("FB_LOCATION", "Los Angeles")

AI_MONTHLY_CAP_USD = float(os.getenv("AI_MONTHLY_CAP_USD", "150"))
AI_MONTHLY_STOP_AT_PERCENT = float(os.getenv("AI_MONTHLY_STOP_AT_PERCENT", "90"))

AI_EFFECTIVE_LIMIT_USD = AI_MONTHLY_CAP_USD * (AI_MONTHLY_STOP_AT_PERCENT / 100)

INPUT_PRICE_PER_MILLION = 0.80
OUTPUT_PRICE_PER_MILLION = 4.00

USAGE_FILE = Path("data/ai_usage.json")


client = AsyncAnthropic(
    api_key=ANTHROPIC_API_KEY
)


def current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def ensure_usage_file():
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not USAGE_FILE.exists():
        USAGE_FILE.write_text("{}", encoding="utf-8")


def load_usage() -> dict:
    ensure_usage_file()

    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_usage(data: dict):
    ensure_usage_file()

    USAGE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_monthly_spend() -> float:
    data = load_usage()
    month = current_month_key()

    return float(data.get(month, {}).get("spend_usd", 0.0))


def add_usage(input_tokens: int, output_tokens: int, cost_usd: float):
    data = load_usage()
    month = current_month_key()

    if month not in data:
        data[month] = {
            "spend_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": 0,
        }

    data[month]["spend_usd"] += cost_usd
    data[month]["input_tokens"] += input_tokens
    data[month]["output_tokens"] += output_tokens
    data[month]["calls"] += 1

    save_usage(data)


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_MILLION
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_MILLION

    return input_cost + output_cost


def ai_budget_available() -> bool:
    monthly_spend = get_monthly_spend()
    return monthly_spend < AI_EFFECTIVE_LIMIT_USD


async def ask_ai_for_group_answer(question: str) -> str:
    monthly_spend = get_monthly_spend()

    print("-" * 80)
    print("AI QUESTION")
    print(question)

    print("-" * 80)
    print("AI BUDGET CHECK")
    print(f"Current local monthly spend: ${monthly_spend:.4f}")
    print(f"Monthly cap: ${AI_MONTHLY_CAP_USD:.2f}")
    print(f"Stop at: {AI_MONTHLY_STOP_AT_PERCENT:.0f}%")
    print(f"Effective limit: ${AI_EFFECTIVE_LIMIT_USD:.2f}")

    if not ai_budget_available():
        print("Monthly AI budget limit reached. Returning fallback answer.")
        return "כן"

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
        messages=[
            {
                "role": "user",
                "content": f"""
You are answering a Facebook group join request as a normal human.

Profile:
- Name: {FB_NAME}
- Age: {FB_AGE}
- Location: {FB_LOCATION}

IMPORTANT:
- Never say you are an AI, assistant, bot, or automated system.
- Answer naturally as the profile above.
- Keep answers short.
- Use Hebrew if the question is Hebrew.
- Do not invent new personal details outside the profile.
- If asked age, use the provided age.
- If asked where you live, use the provided location.
- If multiple choice, return ONLY the best option.
- Avoid explanations.

Question:
{question}
"""
            }
        ],
    )

    answer = response.content[0].text.strip()

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    request_cost = estimate_cost_usd(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    add_usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=request_cost,
    )

    updated_monthly_spend = get_monthly_spend()

    print("-" * 80)
    print("AI RESPONSE")
    print(answer)

    print("-" * 80)
    print("AI TOKEN USAGE")
    print(f"Input tokens: {input_tokens}")
    print(f"Output tokens: {output_tokens}")
    print(f"Request cost: ${request_cost:.6f}")
    print(f"Updated monthly spend: ${updated_monthly_spend:.4f}")

    return answer

async def test_ai(question: str = "Where do you live?"):
    print("-" * 80)
    print("AI TEST")

    answer = await ask_ai_for_group_answer(question)

    print(f"Question: {question}")
    print(f"Answer: {answer}")

    return answer