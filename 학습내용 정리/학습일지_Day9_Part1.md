# 학습일지 Day 9 (Part 1)

**날짜:** Day 9
**학습 시간:** 코딩 트랙 (코드 리딩 중심)
**진행 상태:** utils.py 코드 리딩 완료, day4_step3.py 리딩은 내일 계속

---

## 코딩 트랙: SQLite 전환 코드 리딩

### 오늘 한 일
- Claude Code가 만든 SQLite 버전 utils.py 전체 코드 리딩
- 통계 함수 일부 코드 리딩
- 새로운 개념들을 질문하며 학습

---

## 복습 및 심화 이해

### import os의 의미
- os = Operating System(운영체제)
- 컴퓨터 시스템(파일/폴더) 기능을 Python에서 쓸 수 있게 해주는 도구 상자
- 지금까지 쓴 기능: os.path.exists(), os.path.dirname(), os.path.join()

### 경로 설정 복습
```python
기준경로 = os.path.dirname(__file__)              # 이 py 파일이 있는 폴더
JSON경로 = os.path.join(기준경로, "환자DB.json")   # 그 폴더 + 파일이름
DB경로 = os.path.join(기준경로, "환자DB.db")       # 그 폴더 + 파일이름
```

### with open() as f: 복습
- `f = open()` + `f.close()`를 합친 안전한 방식
- 들여쓰기 블록 안에서는 계속 열려있고, 블록 끝나면 자동으로 닫힘
- "한 번 읽고 바로 닫는 것"이 아님

### 함수에서 ()의 유무
- `()` 있음 = 실행 (명령): `conn.cursor()`, `conn.close()`, `cursor.fetchall()`
- `()` 없음 = 값 (속성/설정): `cursor.lastrowid`, `cursor.rowcount`, `conn.row_factory`

---

## 새로 배운 개념

### conn.row_factory = sqlite3.Row
- **세팅 지정**이지 변수 지정이 아님
- DB에서 꺼낸 결과를 딕셔너리처럼 이름표로 접근할 수 있게 해주는 설정
- 설정 안 하면: `결과[0]`, `결과[1]` (순번 기억 필요)
- 설정 하면: `결과["이름"]`, `결과["나이"]` (이름표로 접근)
- 순서 기억할 필요 없이 이름표로 쓰고 싶은 대로 쓸 수 있음
- 나중에 칸이 추가돼도 기존 코드가 안 깨짐 (확장에 안전)

### 변수 지정 vs 세팅 변경 구분
```python
conn = sqlite3.connect(DB경로)       # 변수 지정 (새 이름 만들기) → . 없음
conn.row_factory = sqlite3.Row       # 세팅 변경 (conn 안의 설정 바꾸기) → . 있음
conn.cursor()                        # 명령 실행 (conn의 기능) → . 있음
```
- `.`이 없으면 → 새 이름 만들기
- `.`이 있으면 → 이미 있는 것에 대한 조작

### conn.execute() 단축 문법
- 원래: `cursor = conn.cursor()` → `cursor.execute(...)` (2줄)
- 단축: `cursor = conn.execute(...)` (1줄)
- conn.execute()가 내부적으로 cursor를 자동 생성하고 실행까지 한 번에 해줌
- 비유: 수화기 따로 들기 → 스피커폰으로 바로 말하기

### 메서드 체이닝
```python
결과 = conn.execute("SELECT * FROM 환자").fetchall()
#      ↑ cursor 자동 생성 + 실행          ↑ 결과 바로 가져오기
```
- `.`으로 이어 붙여서 앞의 결과에 바로 다음 명령을 연결

### DB연결() 함수의 구조
```python
def DB연결():
    conn = sqlite3.connect(DB경로)       # 연결
    conn.row_factory = sqlite3.Row       # 설정
    conn.execute("CREATE TABLE IF NOT EXISTS ...")  # 테이블 확인
    conn.commit()                         # 확정
    return conn                           # 준비된 연결 상태를 돌려줌
```
- commit 후 return conn = "할 일 다 마무리하고 초기 연결 상태로 돌려줘라"
- 받는 쪽에서 이 conn으로 바로 작업 시작 가능

### 함수마다 conn = DB연결() 하는 이유
- JSON 방식: 데이터를 메모리에 올려놓고 계속 들고 있음
- SQL 방식: 필요할 때만 연결 → 작업 → 연결 닫기 (매번 열고 닫기)
- 비유: JSON = 차트 50장을 책상에 올려놓고 하루종일 / SQL = 한 명 볼 때마다 의무기록실에 요청

### try/finally vs try/except
```python
try:
    # DB 작업
finally:
    conn.close()    # 성공이든 실패든 무조건 실행 (뒷정리 보장)
```
- finally = "뭐가 됐든 DB 연결은 닫아라" (뒷정리 전문)
- except = "에러가 나면 사용자에게 알려라" (에러 대응 전문, day4_step3.py에 있음)
- 에러 발생 시: finally로 conn.close() → 에러를 day4_step3.py로 올림 → except에서 처리
- 프로그램은 죽지 않음 (while 루프가 계속 돌아감)

### with conn: (자동 commit/rollback)
```python
with conn:
    conn.execute("INSERT ...")
    # 성공 → 자동 commit (확정)
    # 실패 → 자동 rollback (없던 일로)
```
- rollback = "다시 시도"가 아니라 "없던 일로 하기"
- with conn은 commit/rollback 담당, finally는 close 담당

### return cursor.lastrowid
- lastrowid = 방금 추가된 환자의 고유 id 번호 (속성, () 없음)
- 현재 day4_step3.py에서 이 값을 받지 않고 있음 (버려지고 있음)
- 나중에 진료기록 테이블 연결할 때 필요해짐
- return은 "출력"이 아니라 "함수를 호출한 곳으로 돌려주기"

### cursor.rowcount
- 삭제/수정된 행 수 (속성, () 없음)
- 0이면 해당 환자 없음, 1 이상이면 성공
- Day 5의 찾음 = True/False 패턴 대신 DB가 알아서 세어줌

### AUTOINCREMENT와 id
- 삭제된 번호를 재사용하지 않음 (고유번호 유지)
- id 1,2,3,4,5에서 3번 삭제 → 다음 환자는 6번 (3번 안 줌)
- 이유: 나중에 다른 테이블에서 이 id로 연결해놓으면, 번호가 바뀌면 연결이 끊어짐

### dict() 변환
```python
[dict(행) for 행 in 결과]
```
- sqlite3.Row 객체를 진짜 딕셔너리로 변환
- 기존 함수들(환자브리핑 등)이 딕셔너리를 받게 만들어져 있으므로 형태를 맞춰주는 것

### SQL에서 *의 의미
```sql
SELECT * FROM 환자     -- 모든 칸을 다 가져와
SELECT 이름, 나이 FROM 환자  -- 이름, 나이만 가져와
```

### (이름,) 쉼표의 의미
```python
"SELECT * FROM 환자 WHERE 이름 = ?", (이름,)
```
- ?에 넣을 값이 1개뿐일 때도 튜플 형태로 줘야 해서 쉼표 필요
- 쉼표 없이 (이름)이라고 쓰면 Python이 그냥 괄호로 인식

### fetchone() vs fetchall()
- fetchone() = 행 1줄 (그 안에 값이 여러 개 있을 수 있음)
- fetchall() = 행 여러 줄
- "one"은 값 1개가 아니라 행 1줄의 의미
- SQL 결과가 1줄이면 fetchone, 여러 줄이면 fetchall

### fetchall()은 한 번만 가능
```python
cursor.fetchall()   # 결과 전부 가져감 → 창구 비어있음
cursor.fetchall()   # 또 가져오기? → 빈 리스트!
```
- 수학의 f(f(x))와 다름: 수학은 계산(반복 가능), fetch는 수령(한 번만)
- 두 번 써야 하면 변수에 저장해두기
- 다시 필요하면 execute를 다시 실행해야 함

### 변수 덮어쓰기와 값 보존
```python
행 = (50, 52.3)          # 첫 번째 결과
전체환자수 = 행[0]        # 50이 전체환자수에 복사됨

행 = (30,)               # 행이 덮어쓰여도
전체환자수                # 여전히 50! (별도 변수에 저장했으니까)
```
- 메모지(행)에 새로 적어도 차트(전체환자수)에 옮겨 적은 건 안 바뀜

### if 순서는 로직에 따라 자유
- 변수가 필요한 if → 변수 먼저 구하고 → if
- 변수 필요 없는 if → 바로 if 가능
- "위에서 아래로 실행된다"는 원칙만 지키면 됨

---

## 핵심 질문과 이해

### SQL과 free-text의 공존
- Q: "의료 기록은 대부분 free-text인데, 매번 SQL 표를 새로 만들어야 하지 않나?"
- A: 정형 데이터는 SQL 표의 칸에, free-text는 TEXT 칸에 통째로 저장. 검색은 SQL로, free-text 분석은 AI가 담당. SQL과 AI의 역할 분담.

### .db 파일의 성격
- 초기 오해: ".db는 SQL 전용이 아니라 JSON이나 free-text도 저장 가능?"
- 스스로 수정: ".db는 SQL 전용이고, 표 안에 TEXT 칸을 만들어서 free-text를 넣는 것"
- 최종 이해: SQL로 검색해서 가져오면 free-text가 따라오고, 그걸 AI가 분석하면 됨

### conn.execute() vs cursor.execute()
- Q: "cursor를 따로 만들지 않았는데 어떻게 작동하지?"
- A: conn.execute()가 내부적으로 cursor를 자동 생성. 단축 문법.

### cursor라는 변수 이름
- Q: "왜 cursor라고 이름 붙였을까 헷갈리게"
- A: conn.execute()가 돌려주는 결과가 cursor 객체라서 관례적으로 그렇게 씀. 아무 이름이나 써도 됨.

### finally는 성공해야 실행되는 건가?
- Q: "try가 성공해야 finally로 오는 거지?"
- A: 아니요, finally는 성공이든 실패든 무조건 실행. DB 연결은 반드시 닫아야 하니까.

### conn.close()로 프로그램이 죽지 않나?
- Q: "conn.close()하면 프로그램이 죽지 않나?"
- A: DB 연결만 닫는 것. 프로그램은 계속 실행. 에러는 day4_step3.py의 except에서 처리.

### return cursor.lastrowid의 용도
- Q: "lastrowid를 돌려받아서 변하는 게 있나?"
- A: 현재는 안 쓰고 있음. 나중에 진료기록 테이블 연결할 때 필요해짐.

### fetchone()인데 값이 두 개인 이유
- Q: "값이 두 개 나오는데 왜 fetchone()?"
- A: "one"은 값 1개가 아니라 행 1줄. 한 줄 안에 여러 값이 있을 수 있음.

---

## 분석 완료한 함수 목록

| 함수 | SQL | return | 상태 |
|------|-----|--------|------|
| DB연결() | CREATE TABLE IF NOT EXISTS | conn | ✅ |
| 환자등록() | INSERT | lastrowid | ✅ |
| 환자목록가져오기() | SELECT * | dict 리스트 | ✅ |
| 환자검색() | SELECT WHERE | dict 리스트 | ✅ |
| 환자삭제() | DELETE | rowcount | ✅ |
| 환자수정() | UPDATE SET | rowcount | ✅ |
| 통계 (일부) | COUNT, AVG | 수치들 | 🔄 진행 중 |

---

## 학습 과정 관찰

### 코드 리딩 수준의 변화
```
Day 4:  한 줄씩 설명 받아야 이해
Day 6:  새 문법을 질문하며 학습
Day 8:  전체 코드를 읽고 흐름 파악
Day 9:  스스로 해석하고 "이거 맞지?" 확인하는 수준
```

### 주목할 학습 패턴
- 스스로 해석을 먼저 시도한 후 검증 요청 (거의 대부분 정확)
- SQL과 free-text 공존 문제를 스스로 제기하고 해결 방향을 추론
- .db 파일의 성격에 대해 초기 오해 → 스스로 수정 → 정확한 결론 도출

---

## 내일 이어서 할 것 (Day 9 Part 2)
- day4_step3.py 코드 리딩
- 전환된 프로그램 실행 테스트 (등록/검색/수정/삭제/통계)
- 테이블 설계: 진료기록, 검사결과 테이블 추가 (의사만 가능한 영역!)
