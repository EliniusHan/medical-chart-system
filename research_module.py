# 연구 검색 모듈 (자연어 → SQL → 결과 추출 + 통계 분석)
import os
import csv
import json
import sqlite3
import random
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic
import pandas as pd

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

DB경로 = os.path.join(os.path.dirname(__file__), "환자DB.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "research_output")

# ============================================================
# 공통 유틸
# ============================================================

def _output_dir_ensure():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def _strip_codeblock(text):
    """마크다운 코드블록 제거."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text

def _call_api(system, user, max_tokens=4096):
    응답 = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return 응답.content[0].text.strip()

DB_SCHEMA = """DB 구조:
- 환자(환자id, 이름, 생년월일, 성별, 가족력, 약부작용이력)
- 진단(진단id, 환자id, 방문id, 진단명, 상태, 비고, 표준코드)
- 방문(방문id, 환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연, 음주, 운동, free_text, 처방요약, 분석완료)
- 검사결과(검사id, 환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위)
- 영상검사(영상id, 환자id, 검사시행일, 검사종류, 결과요약, 주요수치)
- 추적계획(추적id, 환자id, 방문id, 예정일, 내용, 완료여부)

주의:
- 나이는 생년월일에서 계산: (strftime('%Y','now') - substr(생년월일,1,4))
- 결과값은 TEXT이므로 숫자 비교 시 CAST(결과값 AS REAL) 사용
- 진단 검색 시 상태='활성' 또는 상태='의심' 조건 고려"""

SQL_SYSTEM = f"""당신은 의료 데이터베이스 검색 어시스턴트입니다.
의사의 자연어 질문을 SQLite SQL 쿼리로 변환하세요.
반드시 실행 가능한 SQL만 출력하세요. 설명 없이 SQL만.

{DB_SCHEMA}
- JOIN 시 적절한 테이블 연결
- 결과는 읽기 쉽게 이름, 나이 등 기본정보 포함"""

STAT_SYSTEM = f"""당신은 의료 통계 분석 어시스턴트입니다.
의사의 연구 질문을 분석하여:
1. 필요한 SQL 쿼리 (데이터 추출용)
2. 적절한 통계 기법과 선택 근거
3. 실행 가능한 Python 코드 (pandas, scipy, matplotlib, seaborn 사용)
4. 분석 과정 설명
를 JSON으로 반환하세요.

JSON 형식:
{{
  "sql": "SELECT ...",
  "method": "paired t-test",
  "code": "import pandas as pd\\nimport matplotlib\\nmatplotlib.use('Agg')\\nimport matplotlib.pyplot as plt\\n...",
  "explanation": {{
    "data_selection": "...",
    "grouping": "...",
    "method_reason": "...",
    "result_interpretation": "분석 완료 후 채워질 항목"
  }}
}}

{DB_SCHEMA}
- 그래프는 matplotlib로 생성하여 '{OUTPUT_DIR}/' 폴더에 저장 (plt.savefig 사용, plt.show() 금지)
- matplotlib.use('Agg') 를 import 직후에 반드시 추가
- 코드에서 DB 연결: import sqlite3; conn = sqlite3.connect(r'{DB경로}')
- 결과값은 pd.to_numeric(..., errors='coerce') 로 변환
- explanation의 각 항목은 한국어로, 논문의 Methods/Results 섹션 수준으로 자세하게
- 반드시 순수 JSON만 출력. 마크다운 코드블록 없이."""


# ============================================================
# 1. 자연어 검색 (SQL)
# ============================================================

def 자연어를_SQL로(질문):
    sql = _call_api(SQL_SYSTEM, 질문, max_tokens=1024)
    return _strip_codeblock(sql)


def SQL실행(sql):
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
    if not 결과:
        print("\n 검색 결과가 없습니다.")
        return
    print(f"\n 검색 결과: {len(결과)}건\n")
    너비 = {col: len(col) for col in 컬럼명}
    for row in 결과:
        for col in 컬럼명:
            너비[col] = max(너비[col], len(str(row.get(col, "") or "")))
    헤더 = "  ".join(str(col).ljust(너비[col]) for col in 컬럼명)
    print(f"  {헤더}")
    print(f"  {'-' * len(헤더)}")
    for row in 결과:
        줄 = "  ".join(str(row.get(col, "") or "").ljust(너비[col]) for col in 컬럼명)
        print(f"  {줄}")
    print()


def CSV저장(컬럼명, 결과, 접두사="연구결과"):
    _output_dir_ensure()
    타임스탬프 = datetime.now().strftime("%y%m%d_%H%M%S")
    파일명 = f"{접두사}_{타임스탬프}.csv"
    저장경로 = os.path.join(OUTPUT_DIR, 파일명)
    with open(저장경로, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=컬럼명)
        writer.writeheader()
        writer.writerows(결과)
    print(f" → CSV 저장 완료: research_output/{파일명}")
    return 저장경로


def 연구검색():
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
        CSV저장(컬럼명, 결과)


# ============================================================
# 2. 공통 유틸 — 비식별화 / 라벨링
# ============================================================

def 비식별화(df):
    """이름 → 환자001, 생년월일 → 나이대, 환자id → 랜덤 ID."""
    df = df.copy()
    if "이름" in df.columns:
        매핑 = {name: f"환자{i+1:03d}" for i, name in enumerate(df["이름"].unique())}
        df["이름"] = df["이름"].map(매핑)
    if "생년월일" in df.columns:
        def 나이대변환(생년월일):
            try:
                연도 = int(str(생년월일)[:4])
                나이 = datetime.now().year - 연도
                return f"{(나이 // 10) * 10}대"
            except:
                return "미상"
        df["생년월일"] = df["생년월일"].apply(나이대변환)
        df.rename(columns={"생년월일": "나이대"}, inplace=True)
    if "환자id" in df.columns:
        ids = df["환자id"].unique()
        랜덤매핑 = {oid: random.randint(10000, 99999) for oid in ids}
        df["환자id"] = df["환자id"].map(랜덤매핑)
    return df


def 라벨링(df, 컬럼, 조건들):
    """조건에 따라 라벨 컬럼 추가.
    조건들: [(값_이상, 값_미만, 라벨), ...] — 값_미만=None이면 상한 없음.
    예: [(160, None, '고위험군'), (0, 160, '저위험군')]
    """
    df = df.copy()
    수치 = pd.to_numeric(df[컬럼], errors="coerce")
    라벨컬럼 = 컬럼 + "_그룹"
    def _라벨(v):
        if pd.isna(v):
            return "미상"
        for 이상, 미만, 라벨 in 조건들:
            if 미만 is None:
                if v >= 이상:
                    return 라벨
            else:
                if 이상 <= v < 미만:
                    return 라벨
        return "기타"
    df[라벨컬럼] = 수치.apply(_라벨)
    return df


# ============================================================
# 3. 통계 분석 공통 — AI 응답 파싱 & 코드 실행
# ============================================================

def _parse_stat_response(raw):
    """AI 응답 JSON 파싱. 실패 시 None 반환."""
    text = _strip_codeblock(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _run_stat_code(code):
    """AI가 생성한 Python 코드를 실행하고 stdout 캡처."""
    import io, sys
    _output_dir_ensure()
    stdout_buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buf
    try:
        exec(code, {"__builtins__": __builtins__})
    except Exception as e:
        sys.stdout = old_stdout
        return None, str(e)
    finally:
        sys.stdout = old_stdout
    return stdout_buf.getvalue(), None


def _설명출력(explanation):
    항목들 = [
        ("data_selection", "데이터 선택"),
        ("grouping",       "그룹 분류"),
        ("method_reason",  "통계 기법 선택 근거"),
        ("result_interpretation", "결과 해석"),
    ]
    print("\n=== 분석 과정 설명 ===")
    for key, 제목 in 항목들:
        내용 = explanation.get(key, "")
        if 내용:
            print(f"\n[{제목}]")
            print(f"  {내용}")
    print()


# ============================================================
# 4. 통계분석_자동 — 모드 1
# ============================================================

def 통계분석_자동(질문=None):
    print("\n=== AI 자동 통계 분석 ===")
    if not 질문:
        질문 = input(" 연구 질문을 입력하세요: ").strip()
    if not 질문:
        print(" 질문이 없습니다.\n")
        return

    print("\n AI 분석 계획 수립 중...")
    try:
        raw = _call_api(STAT_SYSTEM, 질문)
    except Exception as e:
        print(f" ⚠ API 오류: {e}\n")
        return

    계획 = _parse_stat_response(raw)
    if not 계획:
        print(" ⚠ AI 응답을 파싱할 수 없습니다.")
        print(f" 원본:\n{raw[:300]}\n")
        return

    # SQL 확인
    sql = 계획.get("sql", "")
    method = 계획.get("method", "")
    print(f"\n [통계 기법] {method}")
    print(f"\n [데이터 추출 SQL]\n  {sql.replace(chr(10), chr(10) + '  ')}\n")
    if input(" 이 계획으로 진행할까요? (y/n): ").strip().lower() != "y":
        print(" → 취소됨\n")
        return

    # 코드 실행
    code = 계획.get("code", "")
    print("\n 분석 실행 중...")
    출력, 오류 = _run_stat_code(code)

    print("\n=== 분석 결과 ===")
    if 오류:
        print(f" ⚠ 코드 실행 오류: {오류}\n")
    else:
        print(출력 or " (결과 없음)")

    # 그래프 파일 안내
    저장된파일 = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png") or f.endswith(".jpg")] if os.path.exists(OUTPUT_DIR) else []
    if 저장된파일:
        print(f" 그래프 저장됨: research_output/{저장된파일[-1]}")

    # 설명 출력
    _설명출력(계획.get("explanation", {}))


# ============================================================
# 5. 통계분석_단계별 — 모드 2
# ============================================================

STEP_SYSTEM = f"""당신은 의료 통계 분석 어시스턴트입니다.
의사와 단계별로 대화하며 분석을 설계합니다.
항상 한국어로 간결하게 답변하세요.

{DB_SCHEMA}
그래프 저장: '{OUTPUT_DIR}/' (plt.savefig, plt.show() 금지, matplotlib.use('Agg') 필수)
DB 연결: import sqlite3; conn = sqlite3.connect(r'{DB경로}')
결과값 변환: pd.to_numeric(..., errors='coerce')"""

통계방법_목록 = """사용 가능한 통계 방법:
  1. 기술통계 (평균, 중앙값, 표준편차)
  2. t-test (두 그룹 평균 비교)
  3. paired t-test (같은 환자 전후 비교)
  4. chi-square (범주형 비교)
  5. ANOVA (세 그룹 이상 비교)
  6. 상관분석 (두 변수 관계)
  7. 회귀분석
  8. AI 추천 수락"""


def _단계_확인(ai_제안, 단계명):
    """AI 제안을 출력하고 y/수정사항 입력받기. y면 True와 None, 수정사항이면 False와 내용 반환."""
    print(f"\n [AI 제안 — {단계명}]\n{ai_제안}\n")
    응답 = input(" 승인하시겠습니까? (y / 수정사항 입력): ").strip()
    if 응답.lower() == "y":
        return True, None
    return False, 응답


def _ai_제안(대화기록, 요청):
    """대화 기록 기반으로 AI에게 제안 요청."""
    대화기록.append({"role": "user", "content": 요청})
    응답텍스트 = _call_api(STEP_SYSTEM, "\n".join(
        f"[{m['role']}] {m['content']}" for m in 대화기록
    ), max_tokens=2048)
    대화기록.append({"role": "assistant", "content": 응답텍스트})
    return 응답텍스트


def 통계분석_단계별():
    print("\n=== 단계별 통계 분석 ===")
    대화기록 = []

    # Step 0: 연구 질문
    질문 = input(" [Step 0] 연구 질문을 입력하세요: ").strip()
    if not 질문:
        print(" 질문이 없습니다.\n")
        return
    대화기록.append({"role": "user", "content": f"연구 질문: {질문}"})

    # Step 1: 데이터 선택
    print("\n Step 1: 데이터 선택 중...")
    제안 = _ai_제안(대화기록,
        f"연구 질문 '{질문}'에 대해 필요한 대상 환자와 변수, 기간을 추천해주세요. "
        "항목별로 간결하게 제안하고 마지막에 승인 여부를 물어보는 형태로.")
    while True:
        승인, 수정 = _단계_확인(제안, "데이터 선택")
        if 승인:
            break
        제안 = _ai_제안(대화기록, f"수정 요청: {수정}. 다시 데이터 선택을 제안해주세요.")

    # Step 2: 그룹 설정
    print("\n Step 2: 그룹 설정 중...")
    제안 = _ai_제안(대화기록, "그룹 설정 방법을 추천해주세요. (예: A군 vs B군, 전후 비교 등)")
    while True:
        승인, 수정 = _단계_확인(제안, "그룹 설정")
        if 승인:
            break
        제안 = _ai_제안(대화기록, f"수정 요청: {수정}. 다시 그룹 설정을 제안해주세요.")

    # Step 3: 통계 기법 선택
    print(f"\n Step 3: 통계 기법 선택 중...")
    제안 = _ai_제안(대화기록, "적절한 통계 기법과 선택 근거를 추천해주세요.")
    while True:
        print(f"\n [AI 제안 — 통계 기법]\n{제안}\n")
        print(통계방법_목록)
        응답 = input(" 승인(y) / 번호 선택 / 수정사항 입력: ").strip()
        if 응답.lower() == "y":
            break
        elif 응답.isdigit() and 1 <= int(응답) <= 8:
            선택방법 = 통계방법_목록.split("\n")[int(응답)].strip()
            제안 = _ai_제안(대화기록, f"통계 방법 '{선택방법}'을 사용하는 방향으로 분석 계획을 수정해주세요.")
            승인, 수정 = _단계_확인(제안, "통계 기법")
            if 승인:
                break
            제안 = _ai_제안(대화기록, f"수정 요청: {수정}")
        else:
            제안 = _ai_제안(대화기록, f"수정 요청: {응답}. 통계 기법을 재추천해주세요.")

    # Step 4: 코드 생성 및 실행
    print("\n Step 4: 분석 코드 생성 중...")
    코드응답 = _ai_제안(대화기록,
        "지금까지 논의된 내용을 바탕으로 완전한 분석 JSON을 생성해주세요. "
        f"형식: {{\"sql\": \"...\", \"method\": \"...\", \"code\": \"...\", "
        f"\"explanation\": {{\"data_selection\": \"...\", \"grouping\": \"...\", "
        f"\"method_reason\": \"...\", \"result_interpretation\": \"...\"}}}}  순수 JSON만 출력.")

    계획 = _parse_stat_response(코드응답)
    if not 계획:
        # JSON 파싱 실패 시 재시도
        print(" JSON 파싱 재시도 중...")
        계획 = _parse_stat_response(_call_api(STEP_SYSTEM,
            "방금 논의한 분석 계획을 JSON으로만 출력해주세요. 마크다운 없이 순수 JSON."))

    if not 계획:
        print(" ⚠ 분석 계획 생성 실패\n")
        return

    code = 계획.get("code", "")
    print("\n 분석 실행 중...")
    _output_dir_ensure()
    출력, 오류 = _run_stat_code(code)

    print("\n=== 분석 결과 ===")
    if 오류:
        print(f" ⚠ 코드 실행 오류: {오류}\n")
    else:
        print(출력 or " (결과 없음)")

    저장된파일 = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png") or f.endswith(".jpg")] if os.path.exists(OUTPUT_DIR) else []
    if 저장된파일:
        print(f" 그래프 저장됨: research_output/{저장된파일[-1]}")

    _설명출력(계획.get("explanation", {}))

    # Step 5: CSV 저장
    if input(" [Step 5] 결과를 CSV로 내보내시겠습니까? (y/n): ").strip().lower() == "y":
        sql = 계획.get("sql", "")
        if sql:
            try:
                컬럼명, 결과 = SQL실행(sql)
                if 결과:
                    CSV저장(컬럼명, 결과, "통계분석결과")
            except sqlite3.Error as e:
                print(f" ⚠ CSV 저장 오류: {e}\n")


# ============================================================
# 6. 연구 도구 메인 메뉴
# ============================================================

def 연구도구():
    print("\n=== 연구 도구 ===")
    print(" 1. 자연어 검색 (SQL)")
    print(" 2. AI 자동 통계 분석")
    print(" 3. 단계별 통계 분석")
    선택 = input(" 선택: ").strip()

    if 선택 == "1":
        연구검색()
    elif 선택 == "2":
        통계분석_자동()
    elif 선택 == "3":
        통계분석_단계별()
    else:
        print(" 잘못된 선택입니다.\n")
