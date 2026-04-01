# 환자 브리핑 생성기 (Claude API 연동)
import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic
from util import 환자전체기록조회, 나이계산

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """당신은 내과 전문의의 진료 어시스턴트입니다.
환자의 전체 의료 기록을 분석하여 간결하고 정확한 브리핑을 생성하세요.

브리핑에 반드시 포함할 항목:
1. 환자 기본정보 요약 (이름, 나이, 성별)
2. 현재 활성 진단 목록 (상태가 '활성' 또는 '의심'인 진단)
3. 최근 검사 수치 추이 (검사항목별 변화 방향 포함)
4. 미완료 추적계획 (예정일과 내용)
5. 주의사항 (약부작용이력, 가족력, 혈압 추이 등 임상적으로 주의할 점)

형식:
- 항목별로 구분하여 작성
- 수치는 구체적으로 명시
- 해당 항목에 데이터가 없으면 '(없음)'으로 표시"""


def 브리핑생성(환자id):
    """환자id로 전체 기록을 조회하고 Claude API로 브리핑을 생성한다."""
    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    # 나이 계산 추가
    환자 = 기록["환자"]
    나이 = 나이계산(환자["생년월일"])
    if 나이 is not None:
        기록["환자"]["나이"] = f"{나이}세"

    응답 = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        temperature=0.1,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"다음 환자의 브리핑을 작성해주세요.\n\n{json.dumps(기록, ensure_ascii=False, indent=2)}"}
        ]
    )

    return 응답.content[0].text
