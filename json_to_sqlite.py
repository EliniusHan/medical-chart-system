import json
import sqlite3
import os

# 스크립트 파일 기준 경로 설정
기준경로 = os.path.dirname(__file__)
JSON경로 = os.path.join(기준경로, "환자DB.json")
DB경로 = os.path.join(기준경로, "환자DB.db")

# 1) JSON 데이터 읽기
with open(JSON경로, "r") as f:
    환자목록 = json.load(f)

# 2) SQLite DB 생성 및 테이블 만들기
conn = sqlite3.connect(DB경로)
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS 환자")
cursor.execute("""
    CREATE TABLE 환자 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        이름 TEXT,
        나이 INTEGER,
        진단 TEXT,
        수축기 INTEGER,
        이완기 INTEGER
    )
""")

# 3) 데이터 삽입
for 환자 in 환자목록:
    cursor.execute(
        "INSERT INTO 환자 (이름, 나이, 진단, 수축기, 이완기) VALUES (?, ?, ?, ?, ?)",
        (환자["이름"], 환자["나이"], 환자["진단"], 환자["수축기"], 환자["이완기"])
    )

conn.commit()
print(f"환자DB.db 생성 완료! ({len(환자목록)}명 저장)")

# ============================================
# 검색 예제
# ============================================

# 검색 1: 60세 이상 고혈압 환자
print("\n=== 60세 이상 고혈압 환자 ===")
cursor.execute("SELECT 이름, 나이, 수축기, 이완기 FROM 환자 WHERE 나이 >= 60 AND 진단 = '고혈압'")
결과 = cursor.fetchall()
print(f"총 {len(결과)}명")
for 이름, 나이, 수축기, 이완기 in 결과:
    print(f"  {이름} ({나이}세) - 혈압: {수축기}/{이완기}")

# 검색 2: 진단별 환자 수 통계
print("\n=== 진단별 환자 수 ===")
cursor.execute("SELECT 진단, COUNT(*) as 환자수 FROM 환자 GROUP BY 진단 ORDER BY 환자수 DESC")
for 진단, 환자수 in cursor.fetchall():
    print(f"  {진단}: {환자수}명")

# 검색 3: 평균 나이가 가장 높은 진단명
print("\n=== 평균 나이가 가장 높은 진단명 ===")
cursor.execute("SELECT 진단, ROUND(AVG(나이), 1) as 평균나이 FROM 환자 GROUP BY 진단 ORDER BY 평균나이 DESC LIMIT 1")
진단, 평균나이 = cursor.fetchone()
print(f"  {진단} (평균 {평균나이}세)")

conn.close()
