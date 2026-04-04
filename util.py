import sqlite3
import os
from datetime import datetime

# 데이터베이스 파일 경로 (스크립트 파일 기준)
DB경로 = os.path.join(os.path.dirname(__file__), "환자DB.db")


# ============================================
# SQLite 연결 및 테이블 초기화
# ============================================
def DB연결():
    """데이터베이스에 연결하고, 테이블이 없으면 자동 생성한다."""
    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # ---- 1. 환자 테이블 ----
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 환자 (
            환자id INTEGER PRIMARY KEY AUTOINCREMENT,
            이름 TEXT,
            생년월일 TEXT,
            성별 TEXT,
            가족력 TEXT,
            약부작용이력 TEXT
        )
    """)

    # ---- 2. 방문 테이블 ----
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 방문 (
            방문id INTEGER PRIMARY KEY AUTOINCREMENT,
            환자id INTEGER,
            방문일 TEXT,
            수축기 INTEGER,
            이완기 INTEGER,
            심박수 INTEGER,
            키 REAL,
            몸무게 REAL,
            BMI REAL,
            흡연 TEXT,
            음주 TEXT,
            운동 TEXT,
            free_text TEXT,
            처방요약 TEXT,
            분석완료 INTEGER DEFAULT 1,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id)
        )
    """)

    # 기존 DB에 분석완료 칼럼이 없으면 추가
    try:
        conn.execute("SELECT 분석완료 FROM 방문 LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE 방문 ADD COLUMN 분석완료 INTEGER DEFAULT 1")

    # ---- 3. 진단 테이블 ----
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 진단 (
            진단id INTEGER PRIMARY KEY AUTOINCREMENT,
            환자id INTEGER,
            방문id INTEGER,
            진단명 TEXT,
            상태 TEXT CHECK(상태 IN ('활성', '의심', '종결')),
            비고 TEXT,
            표준코드 TEXT,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id),
            FOREIGN KEY (방문id) REFERENCES 방문(방문id)
        )
    """)

    # ---- 4. 검사결과 테이블 ----
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 검사결과 (
            검사id INTEGER PRIMARY KEY AUTOINCREMENT,
            환자id INTEGER,
            검사시행일 TEXT,
            검사항목 TEXT,
            결과값 TEXT,
            단위 TEXT,
            참고범위 TEXT,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id)
        )
    """)

    # ---- 5. 영상검사 테이블 ----
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 영상검사 (
            영상id INTEGER PRIMARY KEY AUTOINCREMENT,
            환자id INTEGER,
            검사시행일 TEXT,
            검사종류 TEXT,
            결과요약 TEXT,
            주요수치 TEXT,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id)
        )
    """)

    # ---- 6. 추적계획 테이블 ----
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 추적계획 (
            추적id INTEGER PRIMARY KEY AUTOINCREMENT,
            환자id INTEGER,
            방문id INTEGER,
            예정일 TEXT,
            내용 TEXT,
            완료여부 INTEGER DEFAULT 0,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id),
            FOREIGN KEY (방문id) REFERENCES 방문(방문id)
        )
    """)

    conn.commit()
    return conn


# ============================================
# 유틸리티 함수
# ============================================
def 혈압판정(수축기, 이완기):
    """수축기/이완기 혈압으로 판정 결과를 반환한다."""
    if not 수축기 or not 이완기:
        return "미측정"
    if 수축기 >= 180 or 이완기 >= 120:
        return "고혈압 위기"
    elif 수축기 >= 140 or 이완기 >= 90:
        return "2기 고혈압"
    elif 수축기 >= 130 or 이완기 >= 80:
        return "1기 고혈압"
    elif 수축기 >= 120:
        return "주의: 혈압 상승"
    else:
        return "정상 혈압"


def 숫자입력(질문, 최소, 최대):
    """범위 내 정수를 입력받아 반환한다."""
    while True:
        try:
            숫자 = int(input(질문))
            if 최소 <= 숫자 <= 최대:
                return 숫자
            else:
                print(f" {최소}-{최대} 사이의 숫자를 입력하세요")
        except ValueError:
            print("숫자를 입력하세요")


def 실수입력(질문, 최소, 최대):
    """범위 내 실수를 입력받아 반환한다."""
    while True:
        try:
            값 = float(input(질문))
            if 최소 <= 값 <= 최대:
                return 값
            else:
                print(f" {최소}-{최대} 사이의 값을 입력하세요")
        except ValueError:
            print(" 숫자를 입력하세요")


def 나이계산(생년월일):
    """생년월일(YYYYMMDD)에서 현재 나이를 계산한다."""
    try:
        생일 = datetime.strptime(생년월일, "%Y%m%d")
        오늘 = datetime.today()
        나이 = 오늘.year - 생일.year
        # 생일이 아직 안 지났으면 -1
        if (오늘.month, 오늘.day) < (생일.month, 생일.day):
            나이 -= 1
        return 나이
    except ValueError:
        return None


# ============================================
# 등록/추가 함수
# ============================================
def 환자등록(이름, 생년월일, 성별, 가족력="", 약부작용이력=""):
    """새 환자를 DB에 등록하고, 환자id를 반환한다."""
    conn = DB연결()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO 환자 (이름, 생년월일, 성별, 가족력, 약부작용이력) VALUES (?, ?, ?, ?, ?)",
                (이름, 생년월일, 성별, 가족력, 약부작용이력)
            )
            return cursor.lastrowid
    finally:
        conn.close()


def 방문기록추가(환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연="", 음주="", 운동="", free_text="", 처방요약="", 분석완료=1):
    """방문 기록을 추가하고, 방문id를 반환한다."""
    conn = DB연결()
    try:
        with conn:
            cursor = conn.execute(
                """INSERT INTO 방문 (환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연, 음주, 운동, free_text, 처방요약, 분석완료)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연, 음주, 운동, free_text, 처방요약, 분석완료)
            )
            return cursor.lastrowid
    finally:
        conn.close()


def 진단추가(환자id, 방문id, 진단명, 상태="활성", 비고="", 표준코드=None):
    """진단 기록을 추가한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 진단 (환자id, 방문id, 진단명, 상태, 비고, 표준코드) VALUES (?, ?, ?, ?, ?, ?)",
                (환자id, 방문id, 진단명, 상태, 비고, 표준코드)
            )
    finally:
        conn.close()


def 검사결과추가(환자id, 검사시행일, 검사항목, 결과값, 단위="", 참고범위=""):
    """혈액검사 결과를 추가한다. (방문과 독립, 환자id + 검사시행일로 저장)"""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 검사결과 (환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위) VALUES (?, ?, ?, ?, ?, ?)",
                (환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위)
            )
    finally:
        conn.close()


def 영상검사추가(환자id, 검사시행일, 검사종류, 결과요약="", 주요수치=""):
    """영상검사 결과를 추가한다. (방문과 독립, 환자id + 검사시행일로 저장)"""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 영상검사 (환자id, 검사시행일, 검사종류, 결과요약, 주요수치) VALUES (?, ?, ?, ?, ?)",
                (환자id, 검사시행일, 검사종류, 결과요약, 주요수치)
            )
    finally:
        conn.close()


def 추적계획추가(환자id, 방문id, 예정일, 내용):
    """추적 계획을 추가한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 추적계획 (환자id, 방문id, 예정일, 내용) VALUES (?, ?, ?, ?)",
                (환자id, 방문id, 예정일, 내용)
            )
    finally:
        conn.close()


# ============================================
# 조회 함수
# ============================================
def 환자목록가져오기():
    """DB의 모든 환자를 dict 리스트로 반환한다."""
    conn = DB연결()
    try:
        결과 = conn.execute("SELECT * FROM 환자").fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 미분석차트조회():
    """분석완료=0인 방문 기록을 dict 리스트로 반환한다."""
    conn = DB연결()
    try:
        결과 = conn.execute(
            """SELECT 방문.*, 환자.이름
               FROM 방문 JOIN 환자 ON 방문.환자id = 환자.환자id
               WHERE 방문.분석완료 = 0"""
        ).fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 분석완료처리(방문id):
    """방문 기록의 분석완료를 1로 업데이트한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute("UPDATE 방문 SET 분석완료 = 1 WHERE 방문id = ?", (방문id,))
    finally:
        conn.close()


def 환자목록_정렬():
    """전체 환자를 이름순 정렬하고, 동명이인을 표시하여 출력한다."""
    환자들 = 환자목록가져오기()
    if not 환자들:
        print("\n 등록된 환자가 없습니다.\n")
        return

    # 이름순 정렬
    환자들.sort(key=lambda p: p['이름'])

    # 동명이인 찾기: 이름이 2번 이상 나오는 경우
    이름수 = {}
    for p in 환자들:
        이름수[p['이름']] = 이름수.get(p['이름'], 0) + 1
    동명이인셋 = {이름 for 이름, 수 in 이름수.items() if 수 >= 2}

    print(f"\n=== 환자 목록 (총 {len(환자들)}명) ===")
    for i, p in enumerate(환자들, 1):
        나이 = 나이계산(p['생년월일'])
        나이표시 = f"{나이}세" if 나이 is not None else "나이미상"
        동명표시 = " ⚠ 동명이인" if p['이름'] in 동명이인셋 else ""
        print(f"  {i}. {p['이름']} ({나이표시}, {p['성별']}){동명표시}")
    print()


def 환자검색(이름):
    """이름으로 환자를 검색하여 dict 리스트로 반환한다. (부분 검색 지원)"""
    conn = DB연결()
    try:
        결과 = conn.execute(
            "SELECT * FROM 환자 WHERE 이름 LIKE ?", (f"%{이름}%",)
        ).fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 진단조회_by_진단명(환자id, 진단명):
    """같은 진단명을 가진 모든 진단 기록을 조회한다."""
    conn = DB연결()
    try:
        결과 = conn.execute(
            """SELECT 진단.*, 방문.방문일
               FROM 진단 LEFT JOIN 방문 ON 진단.방문id = 방문.방문id
               WHERE 진단.환자id = ? AND 진단.진단명 = ?
               ORDER BY 방문.방문일""",
            (환자id, 진단명)
        ).fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 환자전체기록조회(환자id):
    """환자의 모든 기록을 조회하여 dict로 반환한다."""
    conn = DB연결()
    try:
        # 환자 기본정보
        환자 = conn.execute("SELECT * FROM 환자 WHERE 환자id = ?", (환자id,)).fetchone()
        if not 환자:
            return None

        # 방문 기록
        방문목록 = conn.execute(
            "SELECT * FROM 방문 WHERE 환자id = ? ORDER BY 방문일 DESC", (환자id,)
        ).fetchall()

        # 진단 기록
        진단목록 = conn.execute(
            """SELECT 진단.*, 방문.방문일
               FROM 진단 LEFT JOIN 방문 ON 진단.방문id = 방문.방문id
               WHERE 진단.환자id = ?
               ORDER BY 방문.방문일 DESC""", (환자id,)
        ).fetchall()

        # 검사결과
        검사목록 = conn.execute(
            "SELECT * FROM 검사결과 WHERE 환자id = ? ORDER BY 검사시행일 DESC", (환자id,)
        ).fetchall()

        # 영상검사
        영상목록 = conn.execute(
            "SELECT * FROM 영상검사 WHERE 환자id = ? ORDER BY 검사시행일 DESC", (환자id,)
        ).fetchall()

        # 추적계획
        추적목록 = conn.execute(
            """SELECT 추적계획.*, 방문.방문일
               FROM 추적계획 LEFT JOIN 방문 ON 추적계획.방문id = 방문.방문id
               WHERE 추적계획.환자id = ?
               ORDER BY 예정일""", (환자id,)
        ).fetchall()

        return {
            "환자": dict(환자),
            "방문": [dict(행) for 행 in 방문목록],
            "진단": [dict(행) for 행 in 진단목록],
            "검사결과": [dict(행) for 행 in 검사목록],
            "영상검사": [dict(행) for 행 in 영상목록],
            "추적계획": [dict(행) for 행 in 추적목록],
        }
    finally:
        conn.close()


# ============================================
# 수정 함수
# ============================================
def 환자정보수정(환자id, 수정할항목, 새값):
    """환자 기본정보의 특정 항목을 수정한다."""
    허용항목 = ["이름", "생년월일", "성별", "가족력", "약부작용이력"]
    if 수정할항목 not in 허용항목:
        return False
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                f"UPDATE 환자 SET {수정할항목} = ? WHERE 환자id = ?",
                (새값, 환자id)
            )
        return True
    finally:
        conn.close()


def 방문기록수정(방문id, 수정할항목, 새값):
    """방문 기록의 특정 항목을 수정한다."""
    허용항목 = ["방문일", "수축기", "이완기", "심박수", "키", "몸무게", "BMI",
               "흡연", "음주", "운동", "free_text", "처방요약"]
    if 수정할항목 not in 허용항목:
        return False
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                f"UPDATE 방문 SET {수정할항목} = ? WHERE 방문id = ?",
                (새값, 방문id)
            )
        return True
    finally:
        conn.close()


def 검사결과수정(검사id, 수정할항목, 새값):
    """검사결과 원본 1개를 수정한다. (객관적 사실이므로 전체 자동 반영)"""
    허용항목 = ["검사시행일", "검사항목", "결과값", "단위", "참고범위"]
    if 수정할항목 not in 허용항목:
        return False
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                f"UPDATE 검사결과 SET {수정할항목} = ? WHERE 검사id = ?",
                (새값, 검사id)
            )
        return True
    finally:
        conn.close()


def 영상검사수정(영상id, 수정할항목, 새값):
    """영상검사 원본 1개를 수정한다. (객관적 사실이므로 전체 자동 반영)"""
    허용항목 = ["검사시행일", "검사종류", "결과요약", "주요수치"]
    if 수정할항목 not in 허용항목:
        return False
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                f"UPDATE 영상검사 SET {수정할항목} = ? WHERE 영상id = ?",
                (새값, 영상id)
            )
        return True
    finally:
        conn.close()


def 진단수정_단일(진단id, 수정할항목, 새값):
    """이 차트(진단id)의 진단만 수정한다."""
    허용항목 = ["진단명", "상태", "비고", "표준코드"]
    if 수정할항목 not in 허용항목:
        return False
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                f"UPDATE 진단 SET {수정할항목} = ? WHERE 진단id = ?",
                (새값, 진단id)
            )
        return True
    finally:
        conn.close()


def 진단수정_선택(진단id_리스트, 수정할항목, 새값):
    """선택한 진단id들만 수정한다."""
    허용항목 = ["진단명", "상태", "비고", "표준코드"]
    if 수정할항목 not in 허용항목:
        return 0
    conn = DB연결()
    try:
        with conn:
            placeholders = ",".join("?" for _ in 진단id_리스트)
            결과 = conn.execute(
                f"UPDATE 진단 SET {수정할항목} = ? WHERE 진단id IN ({placeholders})",
                [새값] + list(진단id_리스트)
            )
        return 결과.rowcount
    finally:
        conn.close()


def 진단수정_전체(환자id, 기존진단명, 새진단명):
    """같은 진단명을 가진 해당 환자의 모든 진단 기록을 일괄 수정한다."""
    conn = DB연결()
    try:
        with conn:
            결과 = conn.execute(
                "UPDATE 진단 SET 진단명 = ? WHERE 환자id = ? AND 진단명 = ?",
                (새진단명, 환자id, 기존진단명)
            )
        return 결과.rowcount
    finally:
        conn.close()


def 추적계획수정(추적id, 수정할항목, 새값):
    """추적계획의 특정 항목을 수정한다."""
    허용항목 = ["예정일", "내용", "완료여부"]
    if 수정할항목 not in 허용항목:
        return False
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                f"UPDATE 추적계획 SET {수정할항목} = ? WHERE 추적id = ?",
                (새값, 추적id)
            )
        return True
    finally:
        conn.close()


# ============================================
# 삭제 함수
# ============================================
def 환자삭제(환자id):
    """해당 환자의 모든 기록(6개 테이블)을 함께 삭제한다."""
    conn = DB연결()
    try:
        with conn:
            # 자식 테이블부터 삭제 (외래키 제약조건)
            conn.execute("DELETE FROM 추적계획 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 영상검사 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 검사결과 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 진단 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 방문 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 환자 WHERE 환자id = ?", (환자id,))
        return True
    finally:
        conn.close()


def 방문기록삭제(방문id):
    """방문의 free_text만 삭제한다. 검사결과/영상검사는 절대 삭제하지 않으며, 진단/추적계획도 유지된다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "UPDATE 방문 SET free_text = NULL WHERE 방문id = ?",
                (방문id,)
            )
        return True
    finally:
        conn.close()


def 검사결과삭제(검사id):
    """검사결과 원본을 삭제한다. (객관적 사실이므로 전체 반영)"""
    conn = DB연결()
    try:
        with conn:
            conn.execute("DELETE FROM 검사결과 WHERE 검사id = ?", (검사id,))
        return True
    finally:
        conn.close()


def 영상검사삭제(영상id):
    """영상검사 원본을 삭제한다. (객관적 사실이므로 전체 반영)"""
    conn = DB연결()
    try:
        with conn:
            conn.execute("DELETE FROM 영상검사 WHERE 영상id = ?", (영상id,))
        return True
    finally:
        conn.close()


def 진단삭제_단일(진단id):
    """이 차트(진단id)의 진단만 삭제한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute("DELETE FROM 진단 WHERE 진단id = ?", (진단id,))
        return True
    finally:
        conn.close()


def 진단삭제_선택(진단id_리스트):
    """선택한 진단id들만 삭제한다."""
    conn = DB연결()
    try:
        with conn:
            placeholders = ",".join("?" for _ in 진단id_리스트)
            결과 = conn.execute(
                f"DELETE FROM 진단 WHERE 진단id IN ({placeholders})",
                list(진단id_리스트)
            )
        return 결과.rowcount
    finally:
        conn.close()


def 진단삭제_전체(환자id, 진단명):
    """같은 진단명을 가진 해당 환자의 모든 진단 기록을 삭제한다."""
    conn = DB연결()
    try:
        with conn:
            결과 = conn.execute(
                "DELETE FROM 진단 WHERE 환자id = ? AND 진단명 = ?",
                (환자id, 진단명)
            )
        return 결과.rowcount
    finally:
        conn.close()


def 추적계획삭제(추적id):
    """추적계획을 삭제한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute("DELETE FROM 추적계획 WHERE 추적id = ?", (추적id,))
        return True
    finally:
        conn.close()


def 추적계획완료(추적id):
    """추적계획의 완료여부를 1(완료)로 변경한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "UPDATE 추적계획 SET 완료여부 = 1 WHERE 추적id = ?",
                (추적id,)
            )
        return True
    finally:
        conn.close()


# ============================================
# 통계보기
# ============================================
def 통계보기():
    """DB에서 통계를 계산하여 출력한다."""
    conn = DB연결()
    try:
        # 전체 환자 수
        전체환자수 = conn.execute("SELECT COUNT(*) FROM 환자").fetchone()[0]

        if 전체환자수 == 0:
            print("등록된 환자가 없습니다.")
            return

        # 전체 방문 수
        전체방문수 = conn.execute("SELECT COUNT(*) FROM 방문").fetchone()[0]

        # 전체 검사 수
        전체검사수 = conn.execute("SELECT COUNT(*) FROM 검사결과").fetchone()[0]

        # 전체 영상 수
        전체영상수 = conn.execute("SELECT COUNT(*) FROM 영상검사").fetchone()[0]

        # 진단별 환자 수 (활성 진단 기준)
        진단별결과 = conn.execute(
            "SELECT 진단명, COUNT(DISTINCT 환자id) as 환자수 FROM 진단 WHERE 상태 = '활성' GROUP BY 진단명 ORDER BY 환자수 DESC"
        ).fetchall()

        # 최근 방문 5건
        최근방문 = conn.execute(
            """SELECT 방문.방문일, 환자.이름, 방문.수축기, 방문.이완기
               FROM 방문 JOIN 환자 ON 방문.환자id = 환자.환자id
               ORDER BY 방문.방문일 DESC LIMIT 5"""
        ).fetchall()

        # 미완료 추적계획
        미완료추적 = conn.execute(
            """SELECT 추적계획.예정일, 환자.이름, 추적계획.내용
               FROM 추적계획 JOIN 환자 ON 추적계획.환자id = 환자.환자id
               WHERE 추적계획.완료여부 = 0
               ORDER BY 추적계획.예정일 LIMIT 5"""
        ).fetchall()

        # 결과 출력
        print("\n=== 통계 ===")
        print(f" 전체 환자 수: {전체환자수}명")
        print(f" 전체 방문 수: {전체방문수}건")
        print(f" 전체 혈액검사: {전체검사수}건")
        print(f" 전체 영상검사: {전체영상수}건")

        if 진단별결과:
            print("\n [활성 진단별 환자 수]")
            for 행 in 진단별결과:
                print(f"  {행['진단명']}: {행['환자수']}명")

        if 최근방문:
            print("\n [최근 방문 기록]")
            for 행 in 최근방문:
                판정 = 혈압판정(행['수축기'], 행['이완기'])
                if 행['수축기'] and 행['이완기']:
                    print(f"  {행['방문일']} | {행['이름']} | BP {행['수축기']}/{행['이완기']} ({판정})")
                else:
                    print(f"  {행['방문일']} | {행['이름']} | BP 미측정")

        if 미완료추적:
            print("\n [미완료 추적계획]")
            for 행 in 미완료추적:
                print(f"  {행['예정일']} | {행['이름']} | {행['내용']}")

        print("")
    finally:
        conn.close()
