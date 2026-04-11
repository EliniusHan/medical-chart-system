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
import matplotlib
from anonymizer import api_익명화, api_복원
from util import api_재시도
matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

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

def _call_api(system, user, max_tokens=4096, temperature=0.1):
    응답 = api_재시도(lambda: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}]
    ))
    if not 응답:
        return None
    return 응답.content[0].text.strip()

DB_SCHEMA = """DB 구조:
- 환자(환자id, 이름, 생년월일, 성별, 가족력, 약부작용이력)
- 진단(진단id, 환자id, 방문id, 진단명, 상태, 비고, 표준코드)
- 방문(방문id, 환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연, 음주, 운동, free_text, 처방요약, 분석완료)
- 검사결과(검사id, 환자id, 검사시행일, 검사항목, 결과값, 결과수치, 단위, 참고범위)
- 영상검사(영상id, 환자id, 검사시행일, 검사종류, 결과요약, 주요수치)
- 추적계획(추적id, 환자id, 방문id, 예정일, 내용, 완료여부)
- 처방(처방id, 환자id, 방문id, 약품명, 성분명, 용량, 용법, 일수, 유효여부)
- 검사처방(처방검사id, 환자id, 방문id, 검사명, 처방일, 시행여부, 유효여부)

주의:
- 나이는 생년월일에서 계산: (strftime('%Y','now') - substr(생년월일,1,4))
- 결과수치(REAL) 칼럼이 있으므로 숫자 비교 시 결과수치 사용 (CAST 불필요)
  예: WHERE 결과수치 > 160  (CAST(결과값 AS REAL) > 160 대신)
  결과수치가 NULL인 경우는 텍스트 결과(예: "negative")이므로 숫자 비교 제외됨
- 진단 검색 시 상태='활성' 또는 상태='의심' 조건 고려
- 날짜 끝이 00이면 월 단위 데이터 (예: 260300 = 2026년 3월 중). 일 단위 비교 시 00 데이터를 제외하거나 월 단위로만 비교할 것
- 모든 테이블에서 유효여부=1인 데이터만 조회할 것 (무효 처리된 데이터 제외)"""

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

분석 유형 판단:
  연구 질문을 보고 어떤 분석이 필요한지 판단하세요:

  1. 정형 데이터만으로 충분한 경우 (검사 수치, 진단명, 혈압 등):
     → 기존처럼 SQL + 통계 코드로 처리 (analysis_type 필드 생략 또는 'standard')

  2. free_text 내용 분석이 필요한 경우 (증상, 부작용 호소, 환자 표현 등):
     → SQL로 후보 환자를 먼저 추린 후
     → 추려진 환자의 free_text를 분석하는 방식으로 처리
     → JSON에 'analysis_type': 'freetext' 추가

  free_text 분석이 필요한 예시:
    '부작용을 호소한 환자' → 증상 표현이 다양하므로 free_text 분석 필요
    '금연 성공한 환자의 패턴' → 경과 기록 분석 필요
    '환자 교육 내용을 정리해줘' → free_text에만 있는 정보

  free_text 분석 불필요 예시:
    'LDL 평균 구해줘' → 검사결과 테이블만으로 충분
    '고혈압 환자 수' → 진단 테이블만으로 충분

JSON 형식 (정형 데이터 분석):
{{
  "sql": "SELECT ...",
  "method": "paired t-test",
  "code": "import pandas as pd\\nimport matplotlib\\nmatplotlib.use('Agg')\\nimport matplotlib.pyplot as plt\\n...",
  "explanation": {{
    "data_selection": "...",
    "grouping": "...",
    "method_reason": "...",
    "result_interpretation": "p-value=0.012로 통계적으로 유의한 차이가 있음. 평균 LDL이 173에서 94로 감소."
  }}
}}

JSON 형식 (free_text 분석):
{{
  "sql": "후보 환자 추림용 SQL (예: 스타틴 복용 중인 진단 환자 추출)",
  "analysis_type": "freetext",
  "freetext_query": "이 환자들의 차트에서 스타틴 관련 부작용 증상을 찾아주세요. 직접적 언급뿐 아니라 근육통, myalgia, 다리 뻣뻣함, 소변색 변화 등 관련 증상도 포함.",
  "method": "freetext content analysis",
  "code": "",
  "explanation": {{
    "data_selection": "...",
    "grouping": "",
    "method_reason": "free_text에 기록된 증상 표현은 정형화하기 어려우므로 AI 텍스트 분석 사용",
    "result_interpretation": ""
  }}
}}

{DB_SCHEMA}
- 그래프 저장 시 반드시 'graph_path' 변수를 사용하세요: plt.savefig(graph_path, ...)
  (graph_path는 실행 환경에서 자동 주입되는 변수입니다. 직접 파일명을 쓰지 마세요.)
- plt.show() 금지, matplotlib.use('Agg') 를 import 직후에 반드시 추가
- 코드에서 DB 연결: import sqlite3; conn = sqlite3.connect(r'{DB경로}')
- 결과값은 pd.to_numeric(..., errors='coerce') 로 변환
- explanation의 각 항목은 한국어로, 논문의 Methods/Results 섹션 수준으로 자세하게
- result_interpretation은 반드시 실제 분석 결과를 기반으로 작성하세요.
  p-value, 평균, 상관계수 등 구체적 수치를 인용하여 해석하세요.
  '분석 완료 후 채워질 항목' 같은 플레이스홀더를 절대 사용하지 마세요.
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

def 통계오류처리(에러, 연구질문="", 데이터요약=""):
    """통계 코드 실행 오류를 처리한다.
    알려진 패턴은 상세 설명, 모르는 오류는 AI에게 해석 요청."""
    오류메시지 = str(에러)
    오류 = 오류메시지.lower()

    if any(k in 오류 for k in ["singular", "singular matrix", "lapack", "linalg"]):
        print(" ⚠ 분석 오류: 데이터가 부족하여 회귀분석을 수행할 수 없습니다.")
        print("    (Singular matrix)")
        print("\n 원인:")
        print("  - 표본 수(n)가 독립변수 수(k)보다 적거나 같습니다 (n ≤ k).")
        print("    → 분석에 사용하는 변수(나이, 성별, BMI 등)가 여러 개인데 환자 수가")
        print("      그보다 적으면, 수학적으로 방정식을 풀 수 없습니다.")
        print("      최소한 변수 수보다 환자가 많아야 합니다.")
        print()
        print("  - 또는 특정 변수의 모든 값이 동일합니다 (ConstantInputWarning).")
        print("    → 예: 환자 전원이 남성이면 '성별' 변수에 변동이 없어서")
        print("      성별이 결과에 미치는 영향을 계산할 수 없습니다.")
        print()
        print("  - 독립변수 간 완전 공선성(Multicollinearity)이 존재합니다.")
        print("    → 예: 키와 BMI를 동시에 넣었는데 키가 BMI 계산에 이미 포함되어 있으면,")
        print("      두 변수가 사실상 같은 정보를 담고 있어서 분리해서 분석할 수 없습니다.")
        print("\n 대안:")
        print("  1. 더 넓은 조건으로 검색 (예: 당뇨 → 전체 환자)")
        print("  2. 독립변수를 줄여서 단순 상관분석으로 변경")
        print("     → 여러 변수의 영향을 동시에 보는 대신, 두 변수만 비교")
        print("  3. 기술통계로 변경 (평균, 범위만 확인)")
        print("  4. 데이터가 더 쌓인 후 재분석")

    elif any(k in 오류 for k in ["not enough data", "sample size", "valueerror", "zero-size"]):
        print(" ⚠ 표본 수가 부족합니다.")
        print("    (n < 30, 중심극한정리 적용 어려움)")
        print("    → 표본이 30명 미만이면 평균값의 분포가 정규분포에 가깝다고")
        print("      보장할 수 없어서, 모수 검정의 신뢰도가 낮아집니다.")
        print("\n 원인:")
        print("  - 해당 조건을 만족하는 환자 수가 너무 적음")
        print("  - 결측값(NULL) 제거 후 유효한 데이터가 없음")
        print("\n 대안:")
        print("  1. 더 넓은 조건으로 재검색")
        print("  2. 비모수 검정 또는 기술통계만 수행")
        print("  3. 데이터가 더 쌓인 후 재분석")

    elif any(k in 오류 for k in ["normality", "shapiro", "normaltest"]):
        print(" ⚠ 데이터가 정규분포를 따르지 않습니다.")
        print("    (Shapiro-Wilk test p < 0.05)")
        print("    → 데이터가 평균을 중심으로 좌우 대칭으로 퍼져있지 않습니다.")
        print("      극단적으로 높거나 낮은 값이 있거나, 한쪽으로 치우쳐 있을 수 있습니다.")
        print("      t-test 같은 모수 검정은 정규분포를 가정하므로 결과가 부정확할 수 있습니다.")
        print("\n 대안: 비모수 검정 사용 권장")
        print("    → 정규분포를 가정하지 않는 방법")
        print("      두 그룹 비교: Mann-Whitney U test")
        print("      전후 비교: Wilcoxon signed-rank test")

    elif any(k in 오류 for k in ["levene", "bartlett", "homoscedasticity", "variance"]):
        print(" ⚠ 그룹 간 분산이 동일하지 않습니다.")
        print("    (Levene's test p < 0.05)")
        print("    → A그룹은 값이 좁은 범위에 모여있는데, B그룹은 넓게 퍼져있습니다.")
        print("      이런 경우 일반 t-test의 결과를 신뢰하기 어렵습니다.")
        print("\n 대안: Welch's t-test 사용 권장")
        print("    → 분산이 달라도 사용 가능한 보정된 t-test")

    elif any(k in 오류 for k in ["keyerror", "column", "no such column", "operationalerror"]):
        print(" ⚠ 분석 오류: 데이터 컬럼을 찾을 수 없습니다.")
        print("    (KeyError / OperationalError — SQL 또는 컬럼명 불일치)")
        print("\n 원인:")
        print("  - AI가 생성한 SQL의 컬럼명이 실제 DB와 다름")
        print("\n 대안:")
        print("  - 질문을 더 구체적으로 입력 후 재시도")

    elif any(k in 오류 for k in ["convergence", "did not converge", "maxiter"]):
        print(" ⚠ 분석 오류: 모델이 수렴하지 않았습니다.")
        print("    (Convergence failure — 반복 계산이 최대 횟수에 도달)")
        print("    → 모델이 '정답'에 가까워지려고 반복 계산하는데,")
        print("      정해진 횟수 안에 수렴하지 못했습니다.")
        print("      보통 데이터 스케일 차이가 매우 크거나 표본이 부족할 때 발생합니다.")
        print("\n 대안:")
        print("  1. 변수 표준화 후 재시도 (각 변수를 0~1 또는 평균 0, 표준편차 1로 변환)")
        print("  2. 더 단순한 모델로 변경 (단순 상관분석)")

    else:
        # 알 수 없는 오류 → AI에게 해석 요청
        print(f" ⚠ 분석 오류: 코드 실행 중 오류가 발생했습니다.")
        print(f"    ({오류메시지[:120]})")
        print("\n AI 오류 해석 중...")
        ai_프롬프트 = f"""다음 통계 분석 중 오류가 발생했습니다.
오류: {오류메시지}
분석 내용: {연구질문 or '(정보 없음)'}
데이터 현황: {데이터요약 or '(정보 없음)'}

이 오류의 원인을 아래 형식으로 설명하세요.
JSON이나 코드 없이 순수 한국어 텍스트만 출력하세요.

[오류 원인]
(전문 용어와 함께 쉽게 풀어서 설명)

[대안]
(번호 목록으로 구체적인 대안 제시)"""
        try:
            ai해석 = _call_api(
                "당신은 의료 통계 오류를 친절하게 설명하는 전문가입니다. "
                "JSON이나 코드 없이 순수 한국어 텍스트만 출력하세요.",
                ai_프롬프트, max_tokens=512
            )
            print(ai해석)
        except Exception:
            print("\n 대안:")
            print("  1. 질문을 더 구체적으로 변경 후 재시도")
            print("  2. 더 단순한 통계 기법 선택 (기술통계 → 상관분석 → 회귀분석 순)")

    print()


def _parse_stat_response(raw):
    """AI 응답 JSON 파싱. 실패 시 None 반환."""
    text = _strip_codeblock(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _run_stat_code(code):
    """AI가 생성한 Python 코드를 실행하고 (stdout, 오류, 그래프경로) 반환."""
    import io, sys
    _output_dir_ensure()

    # 타임스탬프 기반 파일명 생성 → 코드 실행 전에 변수로 주입
    graph_path = os.path.join(OUTPUT_DIR, f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

    stdout_buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buf
    try:
        exec(code, {"__builtins__": __builtins__, "graph_path": graph_path})
    except Exception as e:
        sys.stdout = old_stdout
        return None, str(e), None
    finally:
        sys.stdout = old_stdout

    # 실제 저장된 파일 확인 (주입한 경로 또는 폴더 내 최신 파일)
    그래프경로 = None
    if os.path.exists(graph_path):
        그래프경로 = graph_path
    elif os.path.exists(OUTPUT_DIR):
        png파일들 = sorted(
            [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png") or f.endswith(".jpg")],
            key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f))
        )
        if png파일들:
            그래프경로 = os.path.join(OUTPUT_DIR, png파일들[-1])

    return stdout_buf.getvalue(), None, 그래프경로


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
# 4. free_text 분석 공통 실행기
# ============================================================

def _freetext_분석실행(질문, 계획):
    """free_text AI 분석 모드. 통계분석_자동/단계별 공통으로 사용."""
    sql = 계획.get('sql', '')
    freetext_query = 계획.get('freetext_query', '')

    print(f"\n [분석 방식] free_text AI 분석")
    print(" 분석 범위:")
    print("  1. SQL로 후보 추린 후 분석 (권장, 비용 절감)")
    print("  2. 전체 환자 분석 (정밀, 비용 높음)")
    범위 = input(" 선택 (1/2): ").strip()

    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row

    if 범위 == "2":
        rows = conn.execute(
            "SELECT 방문.*, 환자.이름 FROM 방문 JOIN 환자 ON 방문.환자id=환자.환자id "
            "WHERE 방문.유효여부=1 AND 방문.free_text IS NOT NULL AND 방문.free_text != ''"
        ).fetchall()
        차트들 = [dict(r) for r in rows]
        conn.close()
        print(f" → 전체 환자 {len(set(c['환자id'] for c in 차트들))}명, free_text {len(차트들)}건")
    else:
        print(f" [추림 SQL]\n  {sql}")
        try:
            후보컬럼, 후보결과 = SQL실행(sql)
        except Exception as e:
            conn.close()
            print(f" ⚠ SQL 실행 오류: {e}\n")
            return
        환자ids = list(set(row['환자id'] for row in 후보결과))
        print(f" → {len(환자ids)}명 추려짐")
        차트들 = []
        for pid in 환자ids:
            rows = conn.execute(
                "SELECT 방문.*, 환자.이름 FROM 방문 JOIN 환자 ON 방문.환자id=환자.환자id "
                "WHERE 방문.환자id=? AND 방문.유효여부=1 AND 방문.free_text IS NOT NULL AND 방문.free_text != ''",
                (pid,)
            ).fetchall()
            차트들.extend([dict(r) for r in rows])
        conn.close()

    if not 차트들:
        print(" 분석할 free_text가 없습니다.\n")
        return

    # 비용 안내
    총글자 = sum(len(c.get('free_text', '')) for c in 차트들)
    예상토큰 = 총글자 // 4
    print(f"\n 분석 대상: {len(set(c['환자id'] for c in 차트들))}명, free_text {len(차트들)}건")
    print(f" 예상 토큰: 약 {예상토큰 // 1000}K")
    if input(" 진행할까요? (y/n): ").strip().lower() != 'y':
        print(" → 취소됨\n")
        return

    # 환자별 api_익명화 호출 → PT_XXXXX 매핑 수집
    전체_매핑 = {}
    이름_to_랜덤id = {}
    for 이름 in set(c['이름'] for c in 차트들):
        임시_익명, 임시_매핑 = api_익명화({"환자": {"이름": 이름}})
        랜덤id = 임시_익명["환자"]["이름"]   # PT_XXXXX
        이름_to_랜덤id[이름] = 랜덤id
        전체_매핑.update(임시_매핑)

    비식별_차트 = ""
    for c in 차트들:
        비식별_차트 += f"\n[{이름_to_랜덤id[c['이름']]}] ({c['방문일']}):\n{c['free_text']}\n"

    # AI에게 분석 요청
    print("\n AI 분석 중...")
    분석_프롬프트 = f"""연구 질문: {질문}

다음은 {len(set(c['환자id'] for c in 차트들))}명 환자의 진료 기록입니다.
각 환자의 차트를 읽고 연구 질문에 해당하는 내용을 찾아주세요.
직접적 언급뿐 아니라 관련 증상, 동의어, 의학 약어도 포함하세요.

{freetext_query}

{비식별_차트}

결과 형식:
=== 분석 결과 ===
해당 환자: N명 / 전체 N명 (N%)

[환자별 상세]
PT_XXXXX (방문일): 관련 내용, 판단, 근거

[요약]
전체적인 패턴, 특이사항, 통계적 의미"""

    try:
        분석결과 = _call_api(
            "당신은 의료 차트 내용 분석 전문가입니다. 순수 한국어 텍스트로만 답변하세요.",
            분석_프롬프트,
            max_tokens=2048,
            temperature=0.3
        )
    except Exception as e:
        print(f" ⚠ AI 분석 오류: {e}\n")
        return

    # PT_XXXXX → 실명 복원 후 매핑 폐기
    분석결과 = api_복원(분석결과, 전체_매핑)
    전체_매핑 = None

    print(f"\n{분석결과}\n")


# ============================================================
# 5. 통계분석_자동 — 모드 1
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

    # free_text 분석 모드 분기
    if 계획.get('analysis_type') == 'freetext':
        _freetext_분석실행(질문, 계획)
        return

    # SQL 확인
    sql = 계획.get("sql", "")
    method = 계획.get("method", "")
    print(f"\n [통계 기법] {method}")
    print(f"\n [데이터 추출 SQL]\n  {sql.replace(chr(10), chr(10) + '  ')}\n")
    if input(" 이 계획으로 진행할까요? (y/n): ").strip().lower() != "y":
        print(" → 취소됨\n")
        return

    # 1단계: 코드 실행 → 실제 결과 숫자 확보
    code = 계획.get("code", "")
    print("\n 분석 실행 중...")
    출력, 오류, 그래프경로 = _run_stat_code(code)

    print("\n=== 분석 결과 ===")
    if 오류:
        통계오류처리(오류, 연구질문=질문, 데이터요약=계획.get("sql", ""))
        return
    print(출력 or " (결과 없음)")

    # 그래프 파일 안내
    if 그래프경로:
        print(f" 그래프 저장됨: {os.path.relpath(그래프경로)}")

    # 2단계: 실제 결과를 AI에게 보내 해석 요청
    print("\n 결과 해석 생성 중...")
    해석_시스템 = """당신은 의료 통계 결과를 해석하는 전문가입니다.
JSON이나 코드를 출력하지 마세요. 순수 한국어 텍스트만 출력하세요.
반드시 아래 형식으로 작성하세요:

[데이터 선택]
(어떤 데이터를 선택했는지)

[그룹 분류]
(어떻게 그룹을 나눴는지)

[통계 기법 선택 근거]
(왜 이 통계 기법을 선택했는지)

[결과 해석]
(실제 숫자를 인용하며 의학적으로 해석. 숫자를 절대 변경하지 말 것)"""

    해석_프롬프트 = f"""연구 질문: {질문}
통계 기법: {계획.get('method', '')}

실제 분석 결과:
{출력}"""

    try:
        실제해석 = _call_api(해석_시스템, 해석_프롬프트, max_tokens=1024)
    except Exception as e:
        실제해석 = f"(해석 생성 오류: {e})"

    print("\n=== 분석 과정 설명 ===")
    print(실제해석)
    print()


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
        "free_text 분석이 필요한 경우 analysis_type='freetext'와 freetext_query 필드를 포함하세요. "
        f"정형 분석 형식: {{\"sql\": \"...\", \"method\": \"...\", \"code\": \"...\", "
        f"\"explanation\": {{\"data_selection\": \"...\", \"grouping\": \"...\", "
        f"\"method_reason\": \"...\", \"result_interpretation\": \"...\"}}}}  "
        f"free_text 분석 형식: {{\"sql\": \"후보추림SQL\", \"analysis_type\": \"freetext\", "
        f"\"freetext_query\": \"...\", \"method\": \"freetext content analysis\", \"code\": \"\"}}  "
        "순수 JSON만 출력.")

    계획 = _parse_stat_response(코드응답)
    if not 계획:
        # JSON 파싱 실패 시 재시도
        print(" JSON 파싱 재시도 중...")
        계획 = _parse_stat_response(_call_api(STEP_SYSTEM,
            "방금 논의한 분석 계획을 JSON으로만 출력해주세요. 마크다운 없이 순수 JSON."))

    if not 계획:
        print(" ⚠ 분석 계획 생성 실패\n")
        return

    # free_text 분석 모드 분기
    if 계획.get('analysis_type') == 'freetext':
        _freetext_분석실행(질문, 계획)
        return

    code = 계획.get("code", "")
    print("\n 분석 실행 중...")
    출력, 오류, 그래프경로 = _run_stat_code(code)

    print("\n=== 분석 결과 ===")
    if 오류:
        통계오류처리(오류, 연구질문=질문, 데이터요약=계획.get("sql", ""))
    else:
        print(출력 or " (결과 없음)")

    if 그래프경로:
        print(f" 그래프 저장됨: {os.path.relpath(그래프경로)}")

    # 2단계: 실제 결과를 AI에게 보내 해석 요청
    if not 오류 and 출력:
        print("\n 결과 해석 생성 중...")
        해석_시스템 = """당신은 의료 통계 결과를 해석하는 전문가입니다.
JSON이나 코드를 출력하지 마세요. 순수 한국어 텍스트만 출력하세요.
반드시 아래 형식으로 작성하세요:

[데이터 선택]
(어떤 데이터를 선택했는지)

[그룹 분류]
(어떻게 그룹을 나눴는지)

[통계 기법 선택 근거]
(왜 이 통계 기법을 선택했는지)

[결과 해석]
(실제 숫자를 인용하며 의학적으로 해석. 숫자를 절대 변경하지 말 것)"""

        해석_프롬프트 = f"""연구 질문: {질문}
통계 기법: {계획.get('method', '')}

실제 분석 결과:
{출력}"""

        try:
            실제해석 = _call_api(해석_시스템, 해석_프롬프트, max_tokens=1024)
        except Exception as e:
            실제해석 = f"(해석 생성 오류: {e})"

        print("\n=== 분석 과정 설명 ===")
        print(실제해석)
        print()

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
