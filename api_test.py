# Claude API 연결 테스트
import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

응답 = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "안녕하세요, 테스트입니다"}
    ]
)

print("=== Claude API 응답 ===")
print(응답.content[0].text)
