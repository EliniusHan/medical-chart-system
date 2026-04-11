# 진료 패턴 분석기 (SQL 기반 인사이트 + AI 패턴 분석)
import os
import sqlite3
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from anthropic import Anthropic
from util import api_재시도

load_dotenv()

DB경로 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "환자DB.db")
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# 의사패턴 요약 캐시 (프로세스 내 재사용)
_패턴요약_캐시 = None


def _오늘날짜_YYMMDD():
    return datetime.today().strftime("%y%m%d")


def _YYMM00_만료여부(예정일str):
    """예정일이 YYMM00 형식이면 해당 월의 마지막 날 기준으로 지났는지 반환."""
    예정일str = str(예정일str)
    try:
        if 예정일str.endswith("00") and len(예정일str) == 6:
            # YYMM00 → 해당 월의 마지막 날 계산
            연도 = int("20" + 예정일str[:2])
            월 = int(예정일str[2:4])
            # 다음 달 1일 - 1일 = 이번 달 마지막 날
            if 월 == 12:
                마지막날 = datetime(연도 + 1, 1, 1) - timedelta(days=1)
            else:
                마지막날 = datetime(연도, 월 + 1, 1) - timedelta(days=1)
            return 마지막날 < datetime.today()
        else:
            # YYMMDD 형식
            날짜 = datetime.strptime("20" + 예정일str, "%Y%m%d")
            return 날짜 < datetime.today()
    except Exception:
        return False


def _YYMMDD_이번주여부(예정일str):
    """예정일이 이번 주(오늘~6일 후)인지 반환."""
    예정일str = str(예정일str)
    try:
        오늘 = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        일주일후 = 오늘 + timedelta(days=6)
        if 예정일str.endswith("00") and len(예정일str) == 6:
            # YYMM00 → 해당 월 1일로 간주
            연도 = int("20" + 예정일str[:2])
            월 = int(예정일str[2:4])
            날짜 = datetime(연도, 월, 1)
        else:
            날짜 = datetime.strptime("20" + 예정일str, "%Y%m%d")
        return 오늘 <= 날짜 <= 일주일후
    except Exception:
        return False


# ============================================
# 1. SQL 기반 자동 체크 (매일, API 비용 없음)
# ============================================

def 데일리_SQL체크():
    """로그인 시 자동으로 DB를 스캔하여 주의사항을 표시한다.
    API 호출 없이 SQL만으로 체크. Returns: list of str (메시지들)"""
    메시지들 = []
    오늘 = _오늘날짜_YYMMDD()

    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row

    try:
        # ── 1. 추적계획 지연 환자 ──────────────────────────
        rows = conn.execute("""
            SELECT t.예정일, t.내용, p.이름
            FROM 추적계획 t
            JOIN 환자 p ON t.환자id = p.환자id
            WHERE t.완료여부 = 0
              AND t.유효여부 = 1
              AND t.예정일 IS NOT NULL
              AND t.예정일 != ''
        """).fetchall()

        for row in rows:
            if _YYMM00_만료여부(row["예정일"]):
                예정일str = str(row["예정일"])
                # 경과 개월 계산 (근사치)
                try:
                    if 예정일str.endswith("00"):
                        기준연월 = int("20" + 예정일str[:2]) * 12 + int(예정일str[2:4])
                        오늘연월 = datetime.today().year * 12 + datetime.today().month
                        경과 = 오늘연월 - 기준연월
                        경과표시 = f"{경과}개월 경과"
                    else:
                        날짜 = datetime.strptime("20" + 예정일str, "%Y%m%d")
                        경과일 = (datetime.today() - 날짜).days
                        경과표시 = f"{경과일}일 경과"
                except Exception:
                    경과표시 = "기간 계산 불가"
                메시지들.append(
                    f"⚠ 추적 지연: {row['이름']} — {row['내용']} 예정 {row['예정일']} ({경과표시})"
                )

        # ── 2. 검사처방 미시행 ────────────────────────────
        rows = conn.execute("""
            SELECT o.처방일, o.검사명, p.이름
            FROM 검사처방 o
            JOIN 환자 p ON o.환자id = p.환자id
            WHERE o.시행여부 = 0
              AND o.유효여부 = 1
              AND o.처방일 IS NOT NULL
              AND o.처방일 != ''
        """).fetchall()

        for row in rows:
            if _YYMM00_만료여부(row["처방일"]):
                메시지들.append(
                    f"⚠ 미시행 검사: {row['이름']} — {row['검사명']} 처방일 {row['처방일']}"
                )

        # ── 3. 이번 주 예정 환자 ──────────────────────────
        rows = conn.execute("""
            SELECT t.예정일, t.내용, p.이름
            FROM 추적계획 t
            JOIN 환자 p ON t.환자id = p.환자id
            WHERE t.완료여부 = 0
              AND t.유효여부 = 1
              AND t.예정일 IS NOT NULL
              AND t.예정일 != ''
        """).fetchall()

        for row in rows:
            if _YYMMDD_이번주여부(row["예정일"]):
                메시지들.append(
                    f"📅 이번 주 예정: {row['이름']} — {row['내용']} 예정 {row['예정일']}"
                )

    except Exception as e:
        메시지들.append(f"[SQL 체크 오류] {e}")
    finally:
        conn.close()

    return 메시지들


# ============================================
# 2. AI 자유 분석 (주/월 1회, API 비용 있음)
# ============================================

PATTERN_SYSTEM = """당신은 내과 전문의의 진료 패턴 분석 어시스턴트입니다.
아래는 의사의 전체 진료 데이터 요약과 환자별 상세 정보입니다.
의학적으로 주목할 만한 패턴, 개선점, 주의사항을 자유롭게 분석하세요.

분석 관점:
- 처방 패턴: 특정 약물 편중, 가이드라인 대비 적절성
- 검사 누락: 진단 대비 필수 검사 미시행 비율
- 추적 이행: 계획 대비 실제 이행률
- 부작용 패턴: 특정 약물의 부작용 호소 빈도
- 치료 목표 달성: LDL, BP, A1c 등 목표 달성률

구체적 숫자와 환자 수를 포함하여 분석하세요.
개선이 필요한 항목은 구체적 행동 제안과 함께.
문제 없는 항목은 언급하지 마세요.

분석 시 문제가 있는 환자를 구체적으로 명시하세요.
각 개선점마다 해당 환자 목록을 포함하세요.

예시:

**메트포르민 미처방 당뇨 환자 (6명):**
  - 김OO (환자id: 12) — 당뇨 활성, glimepiride만 처방 중
  - 박OO (환자id: 25) — 당뇨 활성, 처방 없음
  - ...

**PPI 중복 처방 의심 환자 (3명):**
  - 이OO (환자id: 8) — 오메프라졸 + 판토프라졸 동시 처방
  - ...

**추적 지연 심각 환자 TOP 5 (경과 기간 순):**
  - 한OO (환자id: 33) — 39개월 경과, Lab 재검 미이행
  - ...

모든 문제점/개선점에 대해 반드시 해당 환자 목록을 전부 나열하세요.
환자 목록 없이 문제점만 서술하는 것은 금지합니다.

예시 — 이렇게 하면 안 됨:
  '검사 시행률 69% — 미시행 91건은 환자 안전에 직접적 위험'
  → 어떤 환자가 해당되는지 목록이 없음! ❌

예시 — 이렇게 해야 함:
  '검사 미시행 환자 (상위 10명):'
  - 김OO (환자id: 5) — Lab(A1c) 미시행, 처방일 230300
  - 박OO (환자id: 12) — 골밀도 검사 미시행, 처방일 230500
  - ...
  → 구체적 환자 + 어떤 검사가 밀렸는지 표시 ✅

환자 수가 10명 이상이면 상위 10명만 나열하고 '외 N명' 표시."""


def _DB_요약수집():
    """AI 패턴 분석용 통계 데이터를 DB에서 수집한다. Returns: dict"""
    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row
    요약 = {}

    try:
        # 전체 환자 수
        요약["전체환자수"] = conn.execute(
            "SELECT COUNT(*) FROM 환자"
        ).fetchone()[0]

        # 진단별 환자 수 (상위 10)
        rows = conn.execute("""
            SELECT 진단명, COUNT(DISTINCT 환자id) AS 환자수
            FROM 진단
            WHERE 유효여부 = 1
            GROUP BY 진단명
            ORDER BY 환자수 DESC
            LIMIT 10
        """).fetchall()
        요약["진단별환자수"] = [{"진단명": r["진단명"], "환자수": r["환자수"]} for r in rows]

        # 처방 빈도 상위 10
        rows = conn.execute("""
            SELECT 약품명, COUNT(*) AS 건수
            FROM 처방
            WHERE 유효여부 = 1
            GROUP BY 약품명
            ORDER BY 건수 DESC
            LIMIT 10
        """).fetchall()
        요약["처방빈도상위10"] = [{"약품명": r["약품명"], "건수": r["건수"]} for r in rows]

        # 진단별 처방 패턴 (상위 5 진단 × 처방 약품 top3)
        top_진단 = [d["진단명"] for d in 요약["진단별환자수"][:5]]
        진단별처방 = {}
        for 진단명 in top_진단:
            rows = conn.execute("""
                SELECT p.약품명, COUNT(*) AS 건수
                FROM 처방 p
                JOIN 진단 d ON p.환자id = d.환자id
                WHERE d.진단명 = ?
                  AND d.유효여부 = 1
                  AND p.유효여부 = 1
                GROUP BY p.약품명
                ORDER BY 건수 DESC
                LIMIT 3
            """, (진단명,)).fetchall()
            진단별처방[진단명] = [{"약품명": r["약품명"], "건수": r["건수"]} for r in rows]
        요약["진단별처방패턴"] = 진단별처방

        # 최근 3개월 검사결과 이상치 빈도
        # 결과수치 칼럼이 존재하는 경우만 (없으면 건너뜀)
        try:
            rows = conn.execute("""
                SELECT 검사항목, 참고범위,
                       COUNT(*) AS 전체,
                       SUM(CASE WHEN 결과수치 IS NOT NULL AND 결과수치 != '' THEN 1 ELSE 0 END) AS 수치있음
                FROM 검사결과
                WHERE 유효여부 = 1
                  AND 검사시행일 >= ?
                GROUP BY 검사항목
                HAVING 수치있음 > 0
                ORDER BY 전체 DESC
                LIMIT 10
            """, (_3개월전_YYMMDD(),)).fetchall()
            요약["최근3개월검사항목별건수"] = [
                {"항목": r["검사항목"], "전체": r["전체"]} for r in rows
            ]
        except Exception:
            요약["최근3개월검사항목별건수"] = []

        # 추적계획 이행률
        전체추적 = conn.execute(
            "SELECT COUNT(*) FROM 추적계획 WHERE 유효여부=1"
        ).fetchone()[0]
        완료추적 = conn.execute(
            "SELECT COUNT(*) FROM 추적계획 WHERE 유효여부=1 AND 완료여부=1"
        ).fetchone()[0]
        요약["추적계획이행률"] = {
            "전체": 전체추적,
            "완료": 완료추적,
            "미완료": 전체추적 - 완료추적,
            "이행률": f"{round(완료추적/전체추적*100)}%" if 전체추적 > 0 else "N/A"
        }

        # 검사처방 시행률
        전체검사처방 = conn.execute(
            "SELECT COUNT(*) FROM 검사처방 WHERE 유효여부=1"
        ).fetchone()[0]
        시행검사처방 = conn.execute(
            "SELECT COUNT(*) FROM 검사처방 WHERE 유효여부=1 AND 시행여부=1"
        ).fetchone()[0]
        요약["검사처방시행률"] = {
            "전체": 전체검사처방,
            "시행": 시행검사처방,
            "미시행": 전체검사처방 - 시행검사처방,
            "시행률": f"{round(시행검사처방/전체검사처방*100)}%" if 전체검사처방 > 0 else "N/A"
        }

    except Exception as e:
        요약["오류"] = str(e)
    finally:
        conn.close()

    return 요약


def _3개월전_YYMMDD():
    날짜 = datetime.today().replace(day=1)
    for _ in range(3):
        날짜 = (날짜 - timedelta(days=1)).replace(day=1)
    return 날짜.strftime("%y%m%d")


def _나이대변환(생년월일str):
    """생년월일(YYYY-MM-DD 또는 YYYYMMDD) → 나이대 문자열 반환. 예: '60대'"""
    try:
        생년월일str = 생년월일str.replace("-", "")
        출생년도 = int(생년월일str[:4])
        나이 = datetime.today().year - 출생년도
        return f"{(나이 // 10) * 10}대"
    except Exception:
        return "나이미상"


def _환자별_상세수집():
    """환자별 진단 + 현재 처방 목록을 수집한다.
    이름은 포함, 생년월일은 나이대로 변환.
    Returns: list of dict"""
    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row
    환자목록 = []

    try:
        patients = conn.execute(
            "SELECT 환자id, 이름, 생년월일, 성별 FROM 환자 ORDER BY 환자id"
        ).fetchall()

        for p in patients:
            환자id = p["환자id"]

            # 활성/의심 진단 목록
            진단rows = conn.execute("""
                SELECT 진단명, 상태
                FROM 진단
                WHERE 환자id = ? AND 유효여부 = 1
                ORDER BY 진단id
            """, (환자id,)).fetchall()
            진단목록 = [f"{r['진단명']}({r['상태']})" for r in 진단rows]

            # 현재 처방 (유효여부=1, 가장 최근 방문의 처방만)
            처방rows = conn.execute("""
                SELECT DISTINCT p.약품명, p.용량, p.용법
                FROM 처방 p
                JOIN 방문 v ON p.방문id = v.방문id
                WHERE p.환자id = ? AND p.유효여부 = 1
                  AND v.방문id = (
                      SELECT MAX(방문id) FROM 방문
                      WHERE 환자id = ? AND 유효여부 = 1
                  )
            """, (환자id, 환자id)).fetchall()
            처방목록 = [f"{r['약품명']} {r['용량']} {r['용법']}" for r in 처방rows]

            # 미완료 추적계획 (예정일 경과 포함)
            추적rows = conn.execute("""
                SELECT 예정일, 내용
                FROM 추적계획
                WHERE 환자id = ? AND 완료여부 = 0 AND 유효여부 = 1
                ORDER BY 예정일
            """, (환자id,)).fetchall()
            미완료추적 = [f"{r['예정일']} {r['내용']}" for r in 추적rows]

            환자목록.append({
                "환자id": 환자id,
                "이름": p["이름"],
                "나이대": _나이대변환(p["생년월일"]),
                "성별": p["성별"],
                "진단": 진단목록,
                "현재처방": 처방목록,
                "미완료추적계획": 미완료추적,
            })

    except Exception as e:
        환자목록.append({"오류": str(e)})
    finally:
        conn.close()

    return 환자목록


def AI_패턴분석():
    """전체 DB 요약 + 환자별 상세 정보를 AI에게 보내서 패턴을 분석하게 한다.
    주 1회 또는 월 1회 실행 권장.
    Returns: str (AI 분석 결과) or None"""
    print("\n [DB 요약 수집 중...]")
    요약 = _DB_요약수집()

    print(" [환자별 상세 정보 수집 중...]")
    환자상세 = _환자별_상세수집()

    전송데이터 = {
        "통계요약": 요약,
        "환자별상세": 환자상세,
    }
    전송_json = json.dumps(전송데이터, ensure_ascii=False, indent=2)

    print(" [AI 분석 중...]")
    응답 = api_재시도(lambda: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0.3,
        system=PATTERN_SYSTEM,
        messages=[
            {"role": "user", "content": f"다음은 이 의원의 전체 진료 데이터 요약과 환자별 상세 정보입니다. 분석해주세요.\n\n{전송_json}"}
        ]
    ))

    if not 응답:
        return None
    return 응답.content[0].text


# ============================================
# 3. 의사 패턴 요약 캐시 (차트 분석 시 사용)
# ============================================

def 의사패턴_요약생성():
    """차트 분석 시 AI 프롬프트에 포함할 의사 패턴 요약을 생성한다.
    SQL만으로 생성 (API 불필요). 캐시하여 재사용.
    Returns: str (프롬프트에 삽입할 텍스트)"""
    global _패턴요약_캐시
    if _패턴요약_캐시 is not None:
        return _패턴요약_캐시

    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row
    항목들 = []

    try:
        # 처방 약품 TOP 5
        rows = conn.execute("""
            SELECT 약품명, COUNT(*) AS 건수
            FROM 처방
            WHERE 유효여부 = 1
            GROUP BY 약품명
            ORDER BY 건수 DESC
            LIMIT 5
        """).fetchall()
        if rows:
            처방목록 = ", ".join([f"{r['약품명']}({r['건수']}건)" for r in rows])
            항목들.append(f"처방 상위: {처방목록}")

        # 진단별 환자 수 TOP 5
        rows = conn.execute("""
            SELECT 진단명, COUNT(DISTINCT 환자id) AS 환자수
            FROM 진단
            WHERE 유효여부 = 1
            GROUP BY 진단명
            ORDER BY 환자수 DESC
            LIMIT 5
        """).fetchall()
        if rows:
            진단목록 = ", ".join([f"{r['진단명']}({r['환자수']}명)" for r in rows])
            항목들.append(f"주요 진단: {진단목록}")

        # 추적계획 이행률
        전체 = conn.execute("SELECT COUNT(*) FROM 추적계획 WHERE 유효여부=1").fetchone()[0]
        완료 = conn.execute("SELECT COUNT(*) FROM 추적계획 WHERE 유효여부=1 AND 완료여부=1").fetchone()[0]
        if 전체 > 0:
            항목들.append(f"추적계획 이행률: {round(완료/전체*100)}% ({완료}/{전체}건)")

        # 검사처방 시행률
        전체검사 = conn.execute("SELECT COUNT(*) FROM 검사처방 WHERE 유효여부=1").fetchone()[0]
        시행 = conn.execute("SELECT COUNT(*) FROM 검사처방 WHERE 유효여부=1 AND 시행여부=1").fetchone()[0]
        if 전체검사 > 0:
            항목들.append(f"검사처방 시행률: {round(시행/전체검사*100)}% ({시행}/{전체검사}건)")

    except Exception as e:
        항목들.append(f"[패턴 요약 오류] {e}")
    finally:
        conn.close()

    if not 항목들:
        return ""

    요약텍스트 = "[의사 진료 패턴 요약]\n" + "\n".join([f" {항목}" for 항목 in 항목들])
    _패턴요약_캐시 = 요약텍스트
    return 요약텍스트
