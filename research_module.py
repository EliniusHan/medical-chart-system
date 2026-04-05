# 연구 검색 모듈 (자연어 → SQL → 결과 추출)
import os
import csv
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

DB경로 = os.path.join(os.path.dirname(__file__), "환자DB.db")

SYSTEM_PROMPT = """당신은 의료 데이터베이스 검색 어시스턴트입니다.
의사의 자연어 질문을 SQLite SQL 쿼리로 변환하세요.
반드시 실행 가능한 SQL만 출력하세요. 설명 없이 SQL만.

DB 구조:
- 환자(환자id, 이름, 생년월일, 성별, 가족력, 약부작용이력)
- 진단(진단id, 환자id, 방문id, 진단명, 상태, 비고, 표준코드)
- 방문(방문id, 환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연, 음주, 운동, free_text, 처방요약, 분석완료)
- 검사결과(검사id, 환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위)
- 영상검사(영상id, 환자id, 검사시행일, 검사종류, 결과요약, 주요수치)
- 추적계획(추적id, 환자id, 방문id, 예정일, 내용, 완료여부)

주의:
- 나이는 생년월일에서 계산: (strftime('%Y','now') - substr(생년월일,1,4))
- 결과값은 TEXT이므로 숫자 비교 시 CAST(결과값 AS REAL) 사용
- 진단 검색 시 상태='활성' 또는 상태='의심' 조건 고려
- JOIN 시 적절한 테이블 연결
- 결과는 읽기 쉽게 이름, 나이 등 기본정보 포함"""


def 자연어를_SQL로(질문):
    """자연어 질문을 Claude API로 SQL 쿼리로 변환한다."""
    응답 = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        temperature=0.1,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": 질문}]
    )
    sql = 응답.content[0].text.strip()
    # 혹시 마크다운 코드블록이 포함된 경우 제거
    if sql.startswith("```"):
        lines = sql.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        sql = "\n".join(lines).strip()
    return sql


def SQL실행(sql):
    """SQL 쿼리를 실행하고 (컬럼명 리스트, 결과 리스트) 튜플을 반환한다."""
    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        컬럼명 = list(rows[0].keys()) if rows else []
        결과 = [dict(row) for row in rows]
        return 컬럼명, 결과
    finally:
        conn.close()


def 결과출력(컬럼명, 결과):
    """쿼리 결과를 보기 좋게 출력한다."""
    if not 결과:
        print("\n 검색 결과가 없습니다.")
        return

    print(f"\n 검색 결과: {len(결과)}건\n")

    # 컬럼별 최대 너비 계산
    너비 = {col: len(col) for col in 컬럼명}
    for row in 결과:
        for col in 컬럼명:
            너비[col] = max(너비[col], len(str(row.get(col, "") or "")))

    # 헤더 출력
    헤더 = "  ".join(str(col).ljust(너비[col]) for col in 컬럼명)
    구분선 = "-" * len(헤더)
    print(f"  {헤더}")
    print(f"  {구분선}")

    # 데이터 출력
    for row in 결과:
        줄 = "  ".join(str(row.get(col, "") or "").ljust(너비[col]) for col in 컬럼명)
        print(f"  {줄}")
    print()


def CSV저장(컬럼명, 결과, 질문):
    """결과를 CSV 파일로 저장한다."""
    타임스탬프 = datetime.now().strftime("%y%m%d_%H%M%S")
    파일명 = f"연구결과_{타임스탬프}.csv"
    저장경로 = os.path.join(os.path.dirname(__file__), 파일명)

    with open(저장경로, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=컬럼명)
        writer.writeheader()
        writer.writerows(결과)

    print(f" → CSV 저장 완료: {파일명}")
    return 저장경로


def 연구검색():
    """자연어 질문 → SQL 변환 → 결과 출력 → CSV 저장 흐름을 처리한다."""
    print("\n=== 연구 검색 (자연어 → SQL) ===")
    질문 = input(" 연구 질문을 입력하세요: ").strip()
    if not 질문:
        print(" 질문이 없습니다.\n")
        return

    print("\n SQL 변환 중...")
    try:
        sql = 자연어를_SQL로(질문)
    except Exception as e:
        print(f" ⚠ API 오류: {e}\n")
        return

    print(f"\n [변환된 SQL]\n  {sql.replace(chr(10), chr(10) + '  ')}\n")

    if input(" 이 쿼리를 실행할까요? (y/n): ").strip().lower() != "y":
        print(" → 취소됨\n")
        return

    try:
        컬럼명, 결과 = SQL실행(sql)
    except sqlite3.Error as e:
        print(f" ⚠ SQL 실행 오류: {e}\n")
        return

    결과출력(컬럼명, 결과)

    if 결과 and input(" 결과를 CSV로 저장할까요? (y/n): ").strip().lower() == "y":
        CSV저장(컬럼명, 결과, 질문)
