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
    # 테이블이 없으면 새로 만든다 (이미 있으면 무시)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 환자 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            이름 TEXT,
            나이 INTEGER,
            진단 TEXT,
            수축기 INTEGER,
            이완기 INTEGER
        )
    """)
    conn.commit()
    return conn


# ============================================
# 혈압 판정 함수 (변경 없음)
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
# 환자 브리핑 출력 (변경 없음)
# ============================================
def 환자브리핑(환자):
    print(f" 이름: {환자['이름']}")
    print(f" 나이: {환자['나이']}")
    print(f" 진단: {환자['진단']}")
    print(f" 혈압: {환자['수축기']} / {환자['이완기']} mmHg")
    print(f" 판정: {혈압판정(환자['수축기'], 환자['이완기'])}")
    print("")


# ============================================
# 숫자 입력 유틸리티 (변경 없음)
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
# SQLite CRUD 함수들
# ============================================

def 환자등록(이름, 나이, 진단, 수축기, 이완기):
    """새 환자를 DB에 등록하고, 등록된 환자의 id를 반환한다."""
    conn = DB연결()
    try:
        with conn:  # with문: 성공하면 자동 commit, 실패하면 자동 rollback
            cursor = conn.execute(
                "INSERT INTO 환자 (이름, 나이, 진단, 수축기, 이완기) VALUES (?, ?, ?, ?, ?)",
                (이름, 나이, 진단, 수축기, 이완기)
            )
            return cursor.lastrowid
    finally:
        conn.close()  # DB 연결은 반드시 닫아줘야 한다


def 환자목록가져오기():
    """DB의 모든 환자를 dict 리스트로 반환한다."""
    conn = DB연결()
    try:
        결과 = conn.execute("SELECT * FROM 환자").fetchall()
        # sqlite3.Row → dict로 변환 (환자브리핑 함수가 dict를 받으므로)
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 환자검색(이름):
    """이름으로 환자를 검색하여 dict 리스트로 반환한다."""
    conn = DB연결()
    try:
        결과 = conn.execute(
            "SELECT * FROM 환자 WHERE 이름 = ?", (이름,)
        ).fetchall()
        return [dict(행) for 행 in 결과]
    finally:
        conn.close()


def 환자삭제(이름):
    """이름으로 환자를 삭제하고, 삭제된 환자 수를 반환한다."""
    conn = DB연결()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM 환자 WHERE 이름 = ?", (이름,)
            )
            return cursor.rowcount  # 삭제된 행 수 (0이면 해당 환자 없음)
    finally:
        conn.close()


def 환자수정(이름, 수축기, 이완기):
    """이름으로 환자를 찾아 혈압을 수정하고, 수정된 환자 수를 반환한다."""
    conn = DB연결()
    try:
        with conn:
            cursor = conn.execute(
                "UPDATE 환자 SET 수축기 = ?, 이완기 = ? WHERE 이름 = ?",
                (수축기, 이완기, 이름)
            )
            return cursor.rowcount  # 수정된 행 수 (0이면 해당 환자 없음)
    finally:
        conn.close()


# ============================================
# 통계 보기 (SQL 쿼리 기반으로 재작성)
# ============================================
def 통계보기():
    """DB에서 직접 통계를 계산하여 출력한다."""
    conn = DB연결()
    try:
        # 전체 환자 수와 평균 나이
        행 = conn.execute("SELECT COUNT(*), AVG(나이) FROM 환자").fetchone()
        전체환자수 = 행[0]
        평균나이 = 행[1]

        if 전체환자수 == 0:
            print("등록된 환자가 없습니다.")
            return

        # 진단별 환자 수
        진단별결과 = conn.execute(
            "SELECT 진단, COUNT(*) as 환자수 FROM 환자 GROUP BY 진단"
        ).fetchall()

        # 고혈압 환자 수 (정상 혈압 = 수축기 < 120 AND 이완기 < 80, 그 외는 고혈압)
        행 = conn.execute(
            "SELECT COUNT(*) FROM 환자 WHERE NOT (수축기 < 120 AND 이완기 < 80)"
        ).fetchone()
        고혈압환자수 = 행[0]
        고혈압비율 = 고혈압환자수 / 전체환자수 * 100

        # 결과 출력
        print("\n=== 통계 ===")
        print(f" 전체 환자 수: {전체환자수}명")
        print(f" 평균 나이: {평균나이:.1f}세")
        print("\n [진단별 환자 수]")
        for 행 in 진단별결과:
            print(f"  {행['진단']}: {행['환자수']}명")
        print(f"\n 고혈압 비율 (정상 혈압 제외): {고혈압환자수}명 / {전체환자수}명 ({고혈압비율:.1f}%)")
        print("")
    finally:
        conn.close()
