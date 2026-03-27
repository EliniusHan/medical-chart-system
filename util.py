import sqlite3
import os

# 데이터베이스 파일 경로 (스크립트 파일 기준)
DB경로 = os.path.join(os.path.dirname(__file__), "환자DB.db")


# ============================================
# SQLite 연결 및 테이블 초기화
# ============================================
def DB연결():
    """데이터베이스에 연결하고, 테이블이 없으면 자동 생성한다."""
    conn = sqlite3.connect(DB경로)
    # Row를 dict처럼 쓸 수 있게 설정 (환자["이름"] 형태로 접근 가능)
    conn.row_factory = sqlite3.Row
    # 외래키 제약조건 활성화 (SQLite는 기본적으로 꺼져 있음)
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
            상태 TEXT CHECK(상태 IN ('활성', '관해', '종결')),
            비고 TEXT,
            FOREIGN KEY (환자id) REFERENCES 환자(환자id),
            FOREIGN KEY (방문id) REFERENCES 방문(방문id)
        )
    """)

    # ---- 4. 검사결과 테이블 (혈액검사용) ----
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
# 혈압 판정 함수
# ============================================
def 혈압판정(수축기, 이완기):
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


# ============================================
# 숫자 입력 유틸리티
# ============================================
def 숫자입력(질문, 최소, 최대):
    while True:
        try:
            숫자 = int(input(질문))
            if 최소 <= 숫자 <= 최대:
                return 숫자
            else:
                print(f" {최소}-{최대} 사이의 숫자를 입력하세요")
        except ValueError:
            print("숫자를 입력하세요")


# ============================================
# 1. 환자등록
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


# ============================================
# 2. 환자검색
# ============================================
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


# ============================================
# 3. 환자목록가져오기
# ============================================
def 환자목록가져오기():
    """DB의 모든 환자를 dict 리스트로 반환한다."""
    conn = DB연결()
    try:
        결과 = conn.execute("SELECT * FROM 환자").fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


# ============================================
# 4. 방문기록추가
# ============================================
def 방문기록추가(환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연="", 음주="", 운동="", free_text="", 처방요약=""):
    """방문 기록을 추가하고, 방문id를 반환한다."""
    conn = DB연결()
    try:
        with conn:
            cursor = conn.execute(
                """INSERT INTO 방문 (환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연, 음주, 운동, free_text, 처방요약)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (환자id, 방문일, 수축기, 이완기, 심박수, 키, 몸무게, BMI, 흡연, 음주, 운동, free_text, 처방요약)
            )
            return cursor.lastrowid
    finally:
        conn.close()


# ============================================
# 5. 진단추가
# ============================================
def 진단추가(환자id, 방문id, 진단명, 상태="활성", 비고=""):
    """진단 기록을 추가한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 진단 (환자id, 방문id, 진단명, 상태, 비고) VALUES (?, ?, ?, ?, ?)",
                (환자id, 방문id, 진단명, 상태, 비고)
            )
    finally:
        conn.close()


# ============================================
# 6. 검사결과추가
# ============================================
def 검사결과추가(환자id, 검사시행일, 검사항목, 결과값, 단위="", 참고범위=""):
    """혈액검사 결과를 추가한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 검사결과 (환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위) VALUES (?, ?, ?, ?, ?, ?)",
                (환자id, 검사시행일, 검사항목, 결과값, 단위, 참고범위)
            )
    finally:
        conn.close()


# ============================================
# 7. 영상검사추가
# ============================================
def 영상검사추가(환자id, 검사시행일, 검사종류, 결과요약="", 주요수치=""):
    """영상검사 결과를 추가한다."""
    conn = DB연결()
    try:
        with conn:
            conn.execute(
                "INSERT INTO 영상검사 (환자id, 검사시행일, 검사종류, 결과요약, 주요수치) VALUES (?, ?, ?, ?, ?)",
                (환자id, 검사시행일, 검사종류, 결과요약, 주요수치)
            )
    finally:
        conn.close()


# ============================================
# 8. 추적계획추가
# ============================================
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
# 9. 환자전체기록조회
# ============================================
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
            "SELECT 진단.*, 방문.방문일 FROM 진단 LEFT JOIN 방문 ON 진단.방문id = 방문.방문id WHERE 진단.환자id = ?", (환자id,)
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
            "SELECT 추적계획.*, 방문.방문일 FROM 추적계획 LEFT JOIN 방문 ON 추적계획.방문id = 방문.방문id WHERE 추적계획.환자id = ? ORDER BY 예정일", (환자id,)
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

        # 진단별 환자 수 (활성 진단 기준)
        진단별결과 = conn.execute(
            "SELECT 진단명, COUNT(DISTINCT 환자id) as 환자수 FROM 진단 WHERE 상태 = '활성' GROUP BY 진단명"
        ).fetchall()

        # 최근 방문 5건
        최근방문 = conn.execute(
            """SELECT 방문.방문일, 환자.이름, 방문.수축기, 방문.이완기
               FROM 방문 JOIN 환자 ON 방문.환자id = 환자.환자id
               ORDER BY 방문.방문일 DESC LIMIT 5"""
        ).fetchall()

        # 결과 출력
        print("\n=== 통계 ===")
        print(f" 전체 환자 수: {전체환자수}명")
        print(f" 전체 방문 수: {전체방문수}건")

        if 진단별결과:
            print("\n [활성 진단별 환자 수]")
            for 행 in 진단별결과:
                print(f"  {행['진단명']}: {행['환자수']}명")

        if 최근방문:
            print("\n [최근 방문 기록]")
            for 행 in 최근방문:
                판정 = 혈압판정(행['수축기'], 행['이완기'])
                print(f"  {행['방문일']} | {행['이름']} | BP {행['수축기']}/{행['이완기']} ({판정})")

        print("")
    finally:
        conn.close()
