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
            유효여부 INTEGER DEFAULT 1,
            정정사유 TEXT,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id)
        )
    """)

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
            유효여부 INTEGER DEFAULT 1,
            정정사유 TEXT,
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
            유효여부 INTEGER DEFAULT 1,
            정정사유 TEXT,
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
            유효여부 INTEGER DEFAULT 1,
            정정사유 TEXT,
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
            유효여부 INTEGER DEFAULT 1,
            정정사유 TEXT,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id),
            FOREIGN KEY (방문id) REFERENCES 방문(방문id)
        )
    """)

    # 기존 DB에 없는 칼럼 추가 (ALTER TABLE)
    기존_칼럼_추가 = [
        ("방문",    "분석완료",  "INTEGER DEFAULT 1"),
        ("방문",    "유효여부",  "INTEGER DEFAULT 1"),
        ("방문",    "정정사유",  "TEXT"),
        ("진단",    "유효여부",  "INTEGER DEFAULT 1"),
        ("진단",    "정정사유",  "TEXT"),
        ("검사결과", "유효여부", "INTEGER DEFAULT 1"),
        ("검사결과", "정정사유", "TEXT"),
        ("영상검사", "유효여부", "INTEGER DEFAULT 1"),
        ("영상검사", "정정사유", "TEXT"),
        ("추적계획", "유효여부", "INTEGER DEFAULT 1"),
        ("추적계획", "정정사유", "TEXT"),
    ]
    for 테이블, 칼럼, 타입 in 기존_칼럼_추가:
        try:
            conn.execute(f"SELECT {칼럼} FROM {테이블} LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE {테이블} ADD COLUMN {칼럼} {타입}")

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
                """INSERT INTO 방문 (환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI,
                                    흡연, 음주, 운동, free_text, 처방요약, 분석완료, 유효여부)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI,
                 흡연, 음주, 운동, free_text, 처방요약, 분석완료)
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
                "INSERT INTO 진단 (환자id, 방문id, 진단명, 상태, 비고, 표준코드, 유효여부) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (환자id, 방문id, 진단명, 상태, 비고, 표준코드)
            )
    finally:
        conn.close()


def 검사결과추가(환자id, 검사시행일, 검사항목, 결과값, 단위="", 참고범위=""):
    """혈액검사 결과를 추가한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 검사결과 (환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위, 유효여부) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위)
            )
    finally:
        conn.close()


def 영상검사추가(환자id, 검사시행일, 검사종류, 결과요약="", 주요수치=""):
    """영상검사 결과를 추가한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 영상검사 (환자id, 검사시행일, 검사종류, 결과요약, 주요수치, 유효여부) VALUES (?, ?, ?, ?, ?, 1)",
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
                "INSERT INTO 추적계획 (환자id, 방문id, 예정일, 내용, 유효여부) VALUES (?, ?, ?, ?, 1)",
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
    """분석완료=0이고 유효한 방문 기록을 dict 리스트로 반환한다."""
    conn = DB연결()
    try:
        결과 = conn.execute(
            """SELECT 방문.*, 환자.이름
               FROM 방문 JOIN 환자 ON 방문.환자id = 환자.환자id
               WHERE 방문.분석완료 = 0 AND 방문.유효여부 = 1"""
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

    환자들.sort(key=lambda p: p['이름'])

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
    """이름으로 환자를 검색하여 dict 리스트로 반환한다."""
    conn = DB연결()
    try:
        결과 = conn.execute(
            "SELECT * FROM 환자 WHERE 이름 LIKE ?", (f"%{이름}%",)
        ).fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 진단조회_by_진단명(환자id, 진단명):
    """같은 진단명을 가진 유효한 진단 기록을 조회한다."""
    conn = DB연결()
    try:
        결과 = conn.execute(
            """SELECT 진단.*, 방문.방문일
               FROM 진단 LEFT JOIN 방문 ON 진단.방문id = 방문.방문id
               WHERE 진단.환자id = ? AND 진단.진단명 = ? AND 진단.유효여부 = 1
               ORDER BY 방문.방문일""",
            (환자id, 진단명)
        ).fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 환자전체기록조회(환자id):
    """환자의 유효한 기록만 조회하여 dict로 반환한다."""
    conn = DB연결()
    try:
        환자 = conn.execute("SELECT * FROM 환자 WHERE 환자id = ?", (환자id,)).fetchone()
        if not 환자:
            return None

        방문목록 = conn.execute(
            "SELECT * FROM 방문 WHERE 환자id = ? AND 유효여부 = 1 ORDER BY 방문일 DESC",
            (환자id,)
        ).fetchall()

        진단목록 = conn.execute(
            """SELECT 진단.*, 방문.방문일
               FROM 진단 LEFT JOIN 방문 ON 진단.방문id = 방문.방문id
               WHERE 진단.환자id = ? AND 진단.유효여부 = 1
               ORDER BY 방문.방문일 DESC""", (환자id,)
        ).fetchall()

        검사목록 = conn.execute(
            "SELECT * FROM 검사결과 WHERE 환자id = ? AND 유효여부 = 1 ORDER BY 검사시행일 DESC",
            (환자id,)
        ).fetchall()

        영상목록 = conn.execute(
            "SELECT * FROM 영상검사 WHERE 환자id = ? AND 유효여부 = 1 ORDER BY 검사시행일 DESC",
            (환자id,)
        ).fetchall()

        추적목록 = conn.execute(
            """SELECT 추적계획.*, 방문.방문일
               FROM 추적계획 LEFT JOIN 방문 ON 추적계획.방문id = 방문.방문id
               WHERE 추적계획.환자id = ? AND 추적계획.유효여부 = 1
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


def 전체이력조회_무효포함(환자id):
    """유효여부 관계없이 환자의 모든 기록을 조회한다. (관리자/이력 확인용)"""
    conn = DB연결()
    try:
        환자 = conn.execute("SELECT * FROM 환자 WHERE 환자id = ?", (환자id,)).fetchone()
        if not 환자:
            return None

        방문목록 = conn.execute(
            "SELECT * FROM 방문 WHERE 환자id = ? ORDER BY 방문일 DESC, 방문id DESC",
            (환자id,)
        ).fetchall()

        진단목록 = conn.execute(
            """SELECT 진단.*, 방문.방문일
               FROM 진단 LEFT JOIN 방문 ON 진단.방문id = 방문.방문id
               WHERE 진단.환자id = ?
               ORDER BY 방문.방문일 DESC""", (환자id,)
        ).fetchall()

        검사목록 = conn.execute(
            "SELECT * FROM 검사결과 WHERE 환자id = ? ORDER BY 검사시행일 DESC",
            (환자id,)
        ).fetchall()

        영상목록 = conn.execute(
            "SELECT * FROM 영상검사 WHERE 환자id = ? ORDER BY 검사시행일 DESC",
            (환자id,)
        ).fetchall()

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


def 정정이력조회(환자id):
    """유효여부=0인 기록만 조회한다. (정정/무효화 이력 확인용)"""
    conn = DB연결()
    try:
        방문목록 = conn.execute(
            "SELECT * FROM 방문 WHERE 환자id = ? AND 유효여부 = 0 ORDER BY 방문일 DESC",
            (환자id,)
        ).fetchall()

        진단목록 = conn.execute(
            """SELECT 진단.*, 방문.방문일
               FROM 진단 LEFT JOIN 방문 ON 진단.방문id = 방문.방문id
               WHERE 진단.환자id = ? AND 진단.유효여부 = 0
               ORDER BY 방문.방문일 DESC""", (환자id,)
        ).fetchall()

        검사목록 = conn.execute(
            "SELECT * FROM 검사결과 WHERE 환자id = ? AND 유효여부 = 0 ORDER BY 검사시행일 DESC",
            (환자id,)
        ).fetchall()

        영상목록 = conn.execute(
            "SELECT * FROM 영상검사 WHERE 환자id = ? AND 유효여부 = 0 ORDER BY 검사시행일 DESC",
            (환자id,)
        ).fetchall()

        추적목록 = conn.execute(
            """SELECT 추적계획.*, 방문.방문일
               FROM 추적계획 LEFT JOIN 방문 ON 추적계획.방문id = 방문.방문id
               WHERE 추적계획.환자id = ? AND 추적계획.유효여부 = 0
               ORDER BY 예정일""", (환자id,)
        ).fetchall()

        return {
            "방문": [dict(행) for 행 in 방문목록],
            "진단": [dict(행) for 행 in 진단목록],
            "검사결과": [dict(행) for 행 in 검사목록],
            "영상검사": [dict(행) for 행 in 영상목록],
            "추적계획": [dict(행) for 행 in 추적목록],
        }
    finally:
        conn.close()


def 영향받는_차트_검색(환자id, 검색어들, 기준방문일):
    """무효 처리된 데이터를 기준방문일 이후 차트의 free_text에서 검색한다."""
    if not 검색어들 or not 기준방문일:
        return []
    conn = DB연결()
    try:
        결과 = {}
        for 키워드 in 검색어들:
            if not 키워드:
                continue
            rows = conn.execute(
                """SELECT * FROM 방문
                   WHERE 환자id = ? AND 방문일 > ? AND 유효여부 = 1
                   AND free_text LIKE ?""",
                (환자id, 기준방문일, f"%{키워드}%")
            ).fetchall()
            for 행 in rows:
                v = dict(행)
                결과[v['방문id']] = v
        return list(결과.values())
    finally:
        conn.close()


# ============================================
# 수정 함수 (원본 보존 + 정정 기록 방식)
# 환자정보수정만 예외적으로 덮어쓰기
# ============================================
def 환자정보수정(환자id, 수정할항목, 새값):
    """환자 기본정보의 특정 항목을 수정한다. (덮어쓰기)"""
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


def 방문기록수정(방문id, 수정할항목, 새값, 정정사유=""):
    """방문 기록을 원본 보존 + 정정 방식으로 수정한다. 새 방문id 반환."""
    허용항목 = ["방문일", "수축기", "이완기", "심박수", "키", "몸무게", "BMI",
               "흡연", "음주", "운동", "free_text", "처방요약"]
    if 수정할항목 not in 허용항목:
        return None
    conn = DB연결()
    try:
        기존 = conn.execute(
            "SELECT * FROM 방문 WHERE 방문id = ? AND 유효여부 = 1", (방문id,)
        ).fetchone()
        if not 기존:
            return None
        기존 = dict(기존)

        with conn:
            # 기존 레코드 무효화
            conn.execute(
                "UPDATE 방문 SET 유효여부 = 0, 정정사유 = ? WHERE 방문id = ?",
                (정정사유, 방문id)
            )
            # 새 레코드 생성 (수정 항목만 변경)
            새레코드 = dict(기존)
            새레코드[수정할항목] = 새값
            cursor = conn.execute(
                """INSERT INTO 방문 (환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI,
                                    흡연, 음주, 운동, free_text, 처방요약, 분석완료, 유효여부)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (새레코드['환자id'], 새레코드['방문일'], 새레코드['수축기'], 새레코드['이완기'],
                 새레코드['심박수'], 새레코드['키'], 새레코드['몸무게'], 새레코드['BMI'],
                 새레코드['흡연'], 새레코드['음주'], 새레코드['운동'], 새레코드['free_text'],
                 새레코드['처방요약'], 새레코드['분석완료'])
            )
            return cursor.lastrowid
    finally:
        conn.close()


def 검사결과수정(검사id, 수정할항목, 새값, 정정사유=""):
    """검사결과를 원본 보존 + 정정 방식으로 수정한다. 새 검사id 반환."""
    허용항목 = ["검사시행일", "검사항목", "결과값", "단위", "참고범위"]
    if 수정할항목 not in 허용항목:
        return None
    conn = DB연결()
    try:
        기존 = conn.execute(
            "SELECT * FROM 검사결과 WHERE 검사id = ? AND 유효여부 = 1", (검사id,)
        ).fetchone()
        if not 기존:
            return None
        기존 = dict(기존)

        with conn:
            conn.execute(
                "UPDATE 검사결과 SET 유효여부 = 0, 정정사유 = ? WHERE 검사id = ?",
                (정정사유, 검사id)
            )
            새레코드 = dict(기존)
            새레코드[수정할항목] = 새값
            cursor = conn.execute(
                """INSERT INTO 검사결과 (환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위, 유효여부)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (새레코드['환자id'], 새레코드['검사시행일'], 새레코드['검사항목'],
                 새레코드['결과값'], 새레코드['단위'], 새레코드['참고범위'])
            )
            return cursor.lastrowid
    finally:
        conn.close()


def 영상검사수정(영상id, 수정할항목, 새값, 정정사유=""):
    """영상검사를 원본 보존 + 정정 방식으로 수정한다. 새 영상id 반환."""
    허용항목 = ["검사시행일", "검사종류", "결과요약", "주요수치"]
    if 수정할항목 not in 허용항목:
        return None
    conn = DB연결()
    try:
        기존 = conn.execute(
            "SELECT * FROM 영상검사 WHERE 영상id = ? AND 유효여부 = 1", (영상id,)
        ).fetchone()
        if not 기존:
            return None
        기존 = dict(기존)

        with conn:
            conn.execute(
                "UPDATE 영상검사 SET 유효여부 = 0, 정정사유 = ? WHERE 영상id = ?",
                (정정사유, 영상id)
            )
            새레코드 = dict(기존)
            새레코드[수정할항목] = 새값
            cursor = conn.execute(
                """INSERT INTO 영상검사 (환자id, 검사시행일, 검사종류, 결과요약, 주요수치, 유효여부)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (새레코드['환자id'], 새레코드['검사시행일'], 새레코드['검사종류'],
                 새레코드['결과요약'], 새레코드['주요수치'])
            )
            return cursor.lastrowid
    finally:
        conn.close()


def 진단수정_단일(진단id, 수정할항목, 새값, 정정사유=""):
    """이 차트의 진단을 원본 보존 + 정정 방식으로 수정한다. 새 진단id 반환."""
    허용항목 = ["진단명", "상태", "비고", "표준코드"]
    if 수정할항목 not in 허용항목:
        return None
    conn = DB연결()
    try:
        기존 = conn.execute(
            "SELECT * FROM 진단 WHERE 진단id = ? AND 유효여부 = 1", (진단id,)
        ).fetchone()
        if not 기존:
            return None
        기존 = dict(기존)

        with conn:
            conn.execute(
                "UPDATE 진단 SET 유효여부 = 0, 정정사유 = ? WHERE 진단id = ?",
                (정정사유, 진단id)
            )
            새레코드 = dict(기존)
            새레코드[수정할항목] = 새값
            cursor = conn.execute(
                """INSERT INTO 진단 (환자id, 방문id, 진단명, 상태, 비고, 표준코드, 유효여부)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (새레코드['환자id'], 새레코드['방문id'], 새레코드['진단명'],
                 새레코드['상태'], 새레코드['비고'], 새레코드['표준코드'])
            )
            return cursor.lastrowid
    finally:
        conn.close()


def 진단수정_선택(진단id_리스트, 수정할항목, 새값, 정정사유=""):
    """선택한 진단들을 원본 보존 + 정정 방식으로 수정한다. 수정 건수 반환."""
    허용항목 = ["진단명", "상태", "비고", "표준코드"]
    if 수정할항목 not in 허용항목:
        return 0
    conn = DB연결()
    try:
        placeholders = ",".join("?" for _ in 진단id_리스트)
        rows = conn.execute(
            f"SELECT * FROM 진단 WHERE 진단id IN ({placeholders}) AND 유효여부 = 1",
            list(진단id_리스트)
        ).fetchall()

        건수 = 0
        with conn:
            for 행 in rows:
                행 = dict(행)
                conn.execute(
                    "UPDATE 진단 SET 유효여부 = 0, 정정사유 = ? WHERE 진단id = ?",
                    (정정사유, 행['진단id'])
                )
                새레코드 = dict(행)
                새레코드[수정할항목] = 새값
                conn.execute(
                    """INSERT INTO 진단 (환자id, 방문id, 진단명, 상태, 비고, 표준코드, 유효여부)
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    (새레코드['환자id'], 새레코드['방문id'], 새레코드['진단명'],
                     새레코드['상태'], 새레코드['비고'], 새레코드['표준코드'])
                )
                건수 += 1
        return 건수
    finally:
        conn.close()


def 진단수정_전체(환자id, 기존진단명, 새진단명, 정정사유=""):
    """같은 진단명을 가진 환자의 모든 진단을 원본 보존 + 정정 방식으로 수정한다."""
    conn = DB연결()
    try:
        rows = conn.execute(
            "SELECT * FROM 진단 WHERE 환자id = ? AND 진단명 = ? AND 유효여부 = 1",
            (환자id, 기존진단명)
        ).fetchall()

        건수 = 0
        with conn:
            for 행 in rows:
                행 = dict(행)
                conn.execute(
                    "UPDATE 진단 SET 유효여부 = 0, 정정사유 = ? WHERE 진단id = ?",
                    (정정사유, 행['진단id'])
                )
                conn.execute(
                    """INSERT INTO 진단 (환자id, 방문id, 진단명, 상태, 비고, 표준코드, 유효여부)
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    (행['환자id'], 행['방문id'], 새진단명, 행['상태'], 행['비고'], 행['표준코드'])
                )
                건수 += 1
        return 건수
    finally:
        conn.close()


def 추적계획수정(추적id, 수정할항목, 새값, 정정사유=""):
    """추적계획을 원본 보존 + 정정 방식으로 수정한다. 새 추적id 반환."""
    허용항목 = ["예정일", "내용", "완료여부"]
    if 수정할항목 not in 허용항목:
        return None
    conn = DB연결()
    try:
        기존 = conn.execute(
            "SELECT * FROM 추적계획 WHERE 추적id = ? AND 유효여부 = 1", (추적id,)
        ).fetchone()
        if not 기존:
            return None
        기존 = dict(기존)

        with conn:
            conn.execute(
                "UPDATE 추적계획 SET 유효여부 = 0, 정정사유 = ? WHERE 추적id = ?",
                (정정사유, 추적id)
            )
            새레코드 = dict(기존)
            새레코드[수정할항목] = 새값
            cursor = conn.execute(
                """INSERT INTO 추적계획 (환자id, 방문id, 예정일, 내용, 완료여부, 유효여부)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (새레코드['환자id'], 새레코드['방문id'], 새레코드['예정일'],
                 새레코드['내용'], 새레코드['완료여부'])
            )
            return cursor.lastrowid
    finally:
        conn.close()


# ============================================
# 삭제 함수 (실제 삭제 → 유효여부=0 무효 처리)
# 환자삭제만 예외적으로 실제 DELETE 유지
# ============================================
def 환자삭제(환자id):
    """해당 환자의 모든 기록(6개 테이블)을 실제 삭제한다. (테스트 데이터 정리용)"""
    conn = DB연결()
    try:
        with conn:
            conn.execute("DELETE FROM 추적계획 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 영상검사 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 검사결과 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 진단 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 방문 WHERE 환자id = ?", (환자id,))
            conn.execute("DELETE FROM 환자 WHERE 환자id = ?", (환자id,))
        return True
    finally:
        conn.close()


def 방문기록삭제(방문id, 삭제사유=""):
    """방문을 무효화한다. 연결된 진단, 추적계획도 함께 무효화."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "UPDATE 방문 SET 유효여부 = 0, 정정사유 = ? WHERE 방문id = ?",
                (삭제사유, 방문id)
            )
            conn.execute(
                "UPDATE 진단 SET 유효여부 = 0, 정정사유 = ? WHERE 방문id = ? AND 유효여부 = 1",
                (삭제사유, 방문id)
            )
            conn.execute(
                "UPDATE 추적계획 SET 유효여부 = 0, 정정사유 = ? WHERE 방문id = ? AND 유효여부 = 1",
                (삭제사유, 방문id)
            )
        return True
    finally:
        conn.close()


def 검사결과삭제(검사id, 삭제사유=""):
    """검사결과를 무효 처리한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "UPDATE 검사결과 SET 유효여부 = 0, 정정사유 = ? WHERE 검사id = ?",
                (삭제사유, 검사id)
            )
        return True
    finally:
        conn.close()


def 영상검사삭제(영상id, 삭제사유=""):
    """영상검사를 무효 처리한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "UPDATE 영상검사 SET 유효여부 = 0, 정정사유 = ? WHERE 영상id = ?",
                (삭제사유, 영상id)
            )
        return True
    finally:
        conn.close()


def 진단삭제_단일(진단id, 삭제사유=""):
    """이 차트의 진단을 무효 처리한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "UPDATE 진단 SET 유효여부 = 0, 정정사유 = ? WHERE 진단id = ?",
                (삭제사유, 진단id)
            )
        return True
    finally:
        conn.close()


def 진단삭제_선택(진단id_리스트, 삭제사유=""):
    """선택한 진단들을 무효 처리한다. 처리 건수 반환."""
    conn = DB연결()
    try:
        with conn:
            placeholders = ",".join("?" for _ in 진단id_리스트)
            결과 = conn.execute(
                f"UPDATE 진단 SET 유효여부 = 0, 정정사유 = ? WHERE 진단id IN ({placeholders})",
                [삭제사유] + list(진단id_리스트)
            )
        return 결과.rowcount
    finally:
        conn.close()


def 진단삭제_전체(환자id, 진단명, 삭제사유=""):
    """같은 진단명을 가진 환자의 모든 진단을 무효 처리한다. 처리 건수 반환."""
    conn = DB연결()
    try:
        with conn:
            결과 = conn.execute(
                "UPDATE 진단 SET 유효여부 = 0, 정정사유 = ? WHERE 환자id = ? AND 진단명 = ? AND 유효여부 = 1",
                (삭제사유, 환자id, 진단명)
            )
        return 결과.rowcount
    finally:
        conn.close()


def 추적계획삭제(추적id, 삭제사유=""):
    """추적계획을 무효 처리한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "UPDATE 추적계획 SET 유효여부 = 0, 정정사유 = ? WHERE 추적id = ?",
                (삭제사유, 추적id)
            )
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
        전체환자수 = conn.execute("SELECT COUNT(*) FROM 환자").fetchone()[0]

        if 전체환자수 == 0:
            print("등록된 환자가 없습니다.")
            return

        전체방문수 = conn.execute("SELECT COUNT(*) FROM 방문 WHERE 유효여부 = 1").fetchone()[0]
        전체검사수 = conn.execute("SELECT COUNT(*) FROM 검사결과 WHERE 유효여부 = 1").fetchone()[0]
        전체영상수 = conn.execute("SELECT COUNT(*) FROM 영상검사 WHERE 유효여부 = 1").fetchone()[0]

        진단별결과 = conn.execute(
            """SELECT 진단명, COUNT(DISTINCT 환자id) as 환자수
               FROM 진단 WHERE 상태 = '활성' AND 유효여부 = 1
               GROUP BY 진단명 ORDER BY 환자수 DESC"""
        ).fetchall()

        최근방문 = conn.execute(
            """SELECT 방문.방문일, 환자.이름, 방문.수축기, 방문.이완기
               FROM 방문 JOIN 환자 ON 방문.환자id = 환자.환자id
               WHERE 방문.유효여부 = 1
               ORDER BY 방문.방문일 DESC LIMIT 5"""
        ).fetchall()

        미완료추적 = conn.execute(
            """SELECT 추적계획.예정일, 환자.이름, 추적계획.내용
               FROM 추적계획 JOIN 환자 ON 추적계획.환자id = 환자.환자id
               WHERE 추적계획.완료여부 = 0 AND 추적계획.유효여부 = 1
               ORDER BY 추적계획.예정일 LIMIT 5"""
        ).fetchall()

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
