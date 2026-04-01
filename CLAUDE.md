# 의료 차트 AI 어시스턴트

## 목적
환자 차트 작성 지원 + 연구 데이터 관리

## 기술 스택
- Python + SQLite (`환자DB.db`)
- Claude API (anthropic + python-dotenv)

## 현재 상태
- 환자 등록/검색/수정/삭제/통계 기능 완성 (`main_system.py` + `util.py`)
- SQLite 전환 완료 (`환자DB.db` 사용 중)
- Claude API 연동 (환자 브리핑 생성)
- 차트 분석 + AI 검토 의견 통합 기능 완성
- 미분석 차트 자동 감지 및 재분석 시스템

## 파일 구조

### 핵심 파일
- `main_system.py` — 환자 관리 시스템 본체 (신환등록/브리핑/차트입력(AI 분석)/환자목록/검색/수정/삭제/통계 메뉴 + admin 수동입력)
- `util.py` — 공용 유틸리티 함수 (혈압판정, 나이계산, DB CRUD, 통계보기)
- `chart_analyzer.py` — 차트 분석기 (free-text → AI 데이터 추출 + 검토 의견 통합, 유형별 저장)
- `briefing_generator.py` — Claude API 연동 환자 브리핑 생성
- `api_test.py` — Claude API 연결 테스트

### 데이터
- `환자DB.db` — 환자 데이터 (SQLite)

### `Test/` 폴더 (학습 과정 + 이전 파일)
- `Day1_step1.py` ~ `Day5.py` — 학습 연습 파일
- `json_to_sqlite.py` — JSON → SQLite 일회성 변환 도구 (사용 완료)
- `환자DB.json` — 이전 JSON 데이터 (SQLite 전환 전 사용)
- `curriculum.md` — 학습 커리큘럼

### 문서
- `학습내용 정리/` — Day별 학습일지
- `프로젝트 요약/` — 프로젝트 요약 문서

## 코딩 규칙
- 한글 변수명 사용 (예: `환자목록`, `혈압판정`, `수축기`)
- 주석은 한국어로 작성
- 응답도 항상 한국어로
