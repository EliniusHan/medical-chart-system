# 의료 차트 AI 어시스턴트

## 목적
환자 차트 작성 지원 + 연구 데이터 관리

## 기술 스택
- Python (순수 Python, 외부 라이브러리 미사용)
- SQLite (환자DB.db)
- Claude API (예정)

## 현재 상태
- 환자 등록/검색/수정/삭제/통계 기능 완성 (JSON 기반 — `main_system.py` + `util.py`)
- SQLite 전환 진행 중 (`json_to_sqlite.py`로 JSON → SQLite 변환 완료, 메인 시스템은 아직 JSON 사용)

## 파일 구조

### 핵심 파일
- `main_system.py` — 환자 관리 시스템 본체 (등록/삭제/수정/목록/검색/통계 메뉴)
- `util.py` — 공용 유틸리티 함수 (혈압판정, 환자브리핑, 저장/불러오기, 숫자입력, 통계보기)
- `json_to_sqlite.py` — JSON → SQLite 변환 스크립트 + SQL 검색 예제

### 데이터
- `환자DB.json` — 환자 데이터 (JSON, 현재 메인 시스템이 사용)
- `환자DB.db` — 환자 데이터 (SQLite, 전환 대상)

### 학습 과정 (`Test/` 폴더)
- `Test/Day1_step1.py` — 변수, 출력, 조건문 기초
- `Test/Day1_step2.py` — 딕셔너리, 리스트, 반복문
- `Test/Day2.py` — input으로 환자 정보 입력받기, 혈압 판정
- `Test/Day3_step1.py` — 함수 정의 (혈압판정, 환자브리핑), 하드코딩 데이터
- `Test/Day3_step2.py` — while 반복문으로 환자 등록 시스템
- `Test/Day4_step1.py` — 파일 읽기/쓰기 기초 (txt)
- `Test/Day4_step2.py` — JSON 저장/불러오기 기초
- `Test/Day5.py` — try/except 예외 처리

### 문서
- `curriculum.md` — 학습 커리큘럼
- `학습내용 정리/` — Day별 학습일지 (Day1~Day8)
- `프로젝트 요약/` — 프로젝트 요약 문서

## 코딩 규칙
- 한글 변수명 사용 (예: `환자목록`, `혈압판정`, `수축기`)
- 주석은 한국어로 작성
- 응답도 항상 한국어로
