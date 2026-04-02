# 의료 AI 시스템 개발 커리큘럼 (v5)

**대상:** 비전공자 내과 의사 (Python 기초 5일 완료, 시스템 프롬프트 경험 있음)
**목표:** 환자 차트 AI 어시스턴트 + 연구 데이터 관리 시스템
**핵심 전환:** "직접 코딩하는 사람" → "AI 에이전트를 지휘하며 검증하는 사람"
**일일 학습 시간:** 2~3시간
**총 예상 기간:** 약 8주 (2개월)
**변경 이력:** v4 → v5 Anthropic 공식 코스 통합

---

## 학습 구조

매일 세 트랙 + Anthropic 코스를 유연하게 배분합니다.

| 트랙 | 설명 |
|------|------|
| 🔧 코딩 트랙 | Python, DB, API 개념 이해 + 코드 리딩 |
| 🧠 AI 트랙 | LLM 개념, 프롬프트 엔지니어링 |
| 🤖 에이전트 트랙 | Claude Code, Cowork, 바이브코딩 도구 |
| 📚 Anthropic 코스 | 공식 코스로 체계적 지식 보충 (틈틈이) |

### Anthropic 코스 수강 일정

| 코스 | 수강 시점 | 소요 시간 | 수강 방법 |
|------|----------|----------|----------|
| Claude 101 | Week 1 | 약 2~3시간 | 틈날 때 훑어보기 |
| AI Fluency: Framework & Foundations | Week 1~2 | 약 4~5시간 | 출퇴근길/점심시간 |
| Claude Code in Action | Week 1~2 | 약 3~4시간 | Claude Code 설치와 병행 |
| Building with the Claude API | Week 3 | 약 4~5시간 | API 연동 시작할 때 병행 |
| Intro to MCP | Week 7~8 | 약 3~4시간 | 시스템 확장 단계에서 |
| Intro to Agent Skills | Week 7~8 | 약 2~3시간 | Claude Code 숙련 후 |

---

## Week 1: 코딩 마무리 + 에이전트 입문 + 공식 코스 시작 (Day 1~7)

### Day 1~5 ✅ 완료
- 🔧 Python 기초: 변수, 딕셔너리, 리스트, 함수, 반복문, 파일 저장, JSON, 에러 처리
- 🧠 AI 기초: LLM, 토큰, 컨텍스트 윈도우, temperature, max_tokens

### Day 6: 코드 정리 + Claude Code 설치
- 🔧 모듈과 import 개념 이해, pip install 사용법
- 🤖 **Claude Code 설치 및 첫 실행**
  - 터미널에서 Claude Code 설치
  - 첫 대화: 프로젝트 폴더 분석시키기
  - day4_step3.py를 Claude Code에게 설명시켜보기
  - 실습: "이 코드에서 함수들을 별도 파일로 분리해줘" 시키기
- 📚 **Claude 101 시작** (틈날 때 — 이미 아는 내용은 건너뛰기)

### Day 7: Git + Cowork + AI Fluency
- 🔧 Git 개념 이해 (init, add, commit)
- 🤖 Claude Code로 Git 실행: "이 프로젝트를 Git으로 관리해줘"
- 🤖 Cowork 첫 체험: 폴더 지정 후 간단한 작업 시키기
- 📚 **Claude Code in Action 시작** (Claude Code 사용법 공식 가이드)
- 📚 **AI Fluency: Framework & Foundations 시작** (출퇴근길/점심시간)
- 🧠 할루시네이션: AI가 틀리는 의학 질문 직접 찾아보기

---

## Week 2: 데이터베이스 + 에이전트 실전 (Day 8~14)

### Day 8: DB 개념 + Claude Code 워크플로우
- 🔧 JSON 한계, DB 개념, SQLite 소개
- 🤖 Claude Code 워크플로우 확립
  - Plan Mode 사용법
  - CLAUDE.md 작성 (프로젝트 설명서)
- 📚 Claude Code in Action 계속 수강
- 📚 AI Fluency 계속 수강 (틈틈이)

### Day 9: SQL 기초 — AI에게 시키고 검토하기
- 🔧 SQL 개념: INSERT, SELECT, WHERE, ORDER BY
- 🤖 Claude Code에게 시키기:
  - "환자 SQLite DB 만들어줘"
  - "샘플 데이터 10명 넣어줘"
  - "고혈압 환자만 검색하는 코드 만들어줘"
- 🔧 결과 코드를 읽으며 SQL 문법 이해
- 실습: 직접 SQL 조건 바꿔보기

### Day 10: 테이블 설계 (의사만 할 수 있는 영역!)
- 🔧 **테이블 설계 (직접 해야 함!)**
  - 환자 ↔ 진료기록 ↔ 검사결과 관계 설계
  - 선생님의 실제 차트 구조 기반
- 🤖 설계한 구조를 Claude Code에게 구현시키기
- 🧠 프롬프트 실험: 차트 스타일 학습 프롬프트 개선
- 📚 Claude 101 완료 (이 시점에 끝내기)

### Day 11: JOIN + Python DB 연동
- 🔧 JOIN 개념 이해
- 🤖 Claude Code에게: "김철수의 진료기록+검사결과 함께 조회하는 코드 만들어줘"
- 🔧 결과 코드 리딩: 데이터 흐름 관점에서 검토

### Day 12: DB 함수 모듈 + 검색/통계
- 🤖 Claude Code에게: CRUD 함수, 검색, 통계 기능 만들게 하기
- 🔧 결과 검토: 에러 처리 누락 없는지, 검색 로직 맞는지
- 🧠 프롬프트: 구조화된 출력 (JSON) 실험

### Day 13: 데이터 무결성 + Git 브랜치
- 🔧 제약조건, 트랜잭션, 백업 개념
- 🤖 Claude Code에게: 제약조건 추가, 백업 스크립트, 브랜치 생성 시키기
- 🧠 AI 보안: 프롬프트 인젝션, 의료 데이터 보안 이슈
- 📚 Claude Code in Action 완료 (이 시점에 끝내기)
- 📚 AI Fluency 완료 (이 시점에 끝내기)

### Day 14: Week 2 미니 프로젝트
- 🤖 Claude Code에게 전체 DB 시스템 통합 시키기
- 🔧 **직접 테스트 + 검증:**
  - 동명이인 등록? 음수 나이? 없는 환자 검색?
  - 버그 발견 → Claude Code에게 수정 요청
- 🧠 프롬프트 프로젝트: 차트 검토용 프롬프트 완성 (JSON 출력)

---

## Week 3: API 연동 (Day 15~21)

> Building with the Claude API 코스와 병행하며 실전 적용합니다.

### Day 15: API 실습 시작
- 🔧 API 개념 복습 + Anthropic 계정/API 키 발급
- 🤖 Claude Code에게: anthropic 설치, .env 설정, 첫 API 호출 코드 만들기
- 🔧 결과 코드를 읽으며 API 호출 구조 이해
- 📚 **Building with the Claude API 시작** (API 공식 가이드 — 가장 중요한 코스!)

### Day 16: 기능 1 — 환자 브리핑 생성
- 🤖 Claude Code에게: briefing_generator.py 만들기 (기존 프롬프트 제공)
- 🔧 결과 검토: DB → 프롬프트 → API → 브리핑 데이터 흐름 확인
- 🔧 **의학적 검증: 브리핑 품질이 적절한지 (선생님만 가능!)**
- 📚 Building with the Claude API 계속

### Day 17: 기능 1 — 브리핑 품질 개선
- 🔧 다양한 환자 케이스 테스트 (신환, 다중 진단, 긴 이력)
- 🧠 **프롬프트 미세 조정 (직접 — AI가 대체 불가)**
- 🤖 수정한 프롬프트를 Claude Code에게 주고 코드에 반영시키기
- 📚 Building with the Claude API 계속

### Day 18: 기능 2 — Free-text 차트 분석
- 🤖 Claude Code에게: chart_reviewer.py 만들기 (JSON 응답 파싱 포함)
- 🔧 결과 검토: 검토 항목이 의학적으로 맞는지 확인
- 📚 Building with the Claude API 계속

### Day 19: 기능 2 — 동의/반려 시스템
- 🤖 Claude Code에게: AI 추천 항목 동의/반려 인터페이스 만들기
- 🔧 직접 테스트: 실제 차트 시나리오로 흐름 확인

### Day 20: 기능 3 — 완성본 차트 생성
- 🤖 Claude Code에게: chart_finalizer.py 만들기 (스타일 프로필 적용)
- 🧠 스타일 프롬프트 테스트: SOAP, 서술형 등 다양한 형식
- 📚 Building with the Claude API 완료 (이 시점에 끝내기)

### Day 21: 전체 AI 파이프라인 통합
- 🤖 Claude Code에게: 환자 선택 → 브리핑 → 차트 → AI 검토 → 동의/반려 → 완성본 전체 연결
- 🔧 전체 흐름 테스트 + 버그 리포트 → 수정 요청

---

## Week 4: 연구 데이터 모듈 (Day 22~28)

### Day 22: 연구 데이터 요구사항 + pandas
- 🔧 필요한 연구 데이터 정의 (직접 — 의학적 판단)
- 🔧 IRB, 비식별화 고려사항
- 🤖 Claude Code에게: pandas 설치, DB → DataFrame 변환 코드

### Day 23: AI 기반 데이터 추출 + 자연어 검색
- 🤖 Claude Code에게: free-text → 구조화 데이터 추출 코드, 자연어 → SQL 변환 코드
- 🔧 테스트: "60세 이상 고혈압+당뇨 환자" 같은 검색 검증

### Day 24: 통계 + 시각화 + 내보내기
- 🔧 **검사결과 테이블에 '결과수치' 칸 추가 (ALTER TABLE)**
  - 현재 결과값은 TEXT로 저장 ("124", "C1 negative" 등 혼재)
  - 숫자인 항목은 결과수치(REAL)에도 저장 → SQL 통계 가능
  - 예: FBS → 결과값="124", 결과수치=124 / 유방 → 결과값="C1 negative", 결과수치=NULL
  - AI가 입력 시 숫자 여부 판단 → 결과수치에 자동 저장
- 🤖 Claude Code에게: 통계 함수, 그래프, CSV/Excel 내보내기, 비식별화
- 🧠 AI에게 통계 결과 해석 요청 프롬프트 실험

### Day 25~27: 연구 데이터 모듈 통합
- 🤖 전체 연구 모듈 통합: 검색 → 추출 → 통계 → 시각화 → 내보내기
- 🔧 다양한 연구 시나리오 테스트
- 🔧 **의학적 검증: 데이터 추출이 맞는지 (선생님만 가능!)**

### Day 28: Week 3~4 리뷰
- 전체 백엔드 시스템 점검
- 프롬프트 최종 정리
- Git 커밋 정리 + GitHub push

---

## Week 5~6: 프론트엔드 + 통합 (Day 29~42)

### Day 29: Streamlit 프로토타입
- 🤖 Claude Code에게: Streamlit으로 환자 관리 웹앱 기본 구조 만들기
- 🔧 브라우저에서 동작 확인

### Day 30: 핵심 진료 인터페이스
- 🤖 Claude Code에게: 차트 작성 화면 (free-text, 브리핑, 동의/반려, 완성본)
- 🔧 실제 진료 시나리오로 흐름 테스트
- 🔧 **동의/반려 UI 개선 — 방법 1 적용**
  - 항목별 y/n 방식(Week 3) → 전체 승인 + 수정할 것만 선택 방식으로 개선
  - 체크박스로 한눈에 보고 클릭하는 UI
  - 예: "전체 승인할까요? (y/수정할 항목 번호/n)"

### Day 31: 연구 데이터 대시보드
- 🤖 Claude Code에게: 검색, 테이블, 그래프, 다운로드 대시보드
- 🔧 연구 시나리오로 테스트

### Day 32~33: 바이브코딩으로 UI 개선
- 🤖 Bolt/v0 체험: 같은 화면을 바이브코딩으로 만들어보기
- 🤖 Cowork 활용: 디자인 개선 작업
- 🔧 여러 도구 결과 비교 → 최적 조합 찾기

### Day 34~35: 백엔드-프론트 연결
- 🤖 Claude Code에게: DB + AI 모듈을 Streamlit에 연결
- 🔧 통합 테스트: 전체 흐름 확인

### Day 36: 로그인 + 보안
- 🤖 Claude Code에게: 로그인, API 키 보안, 접근 제어 설정
- 🔧 .gitignore, .env 최종 점검

### Day 37~40: 전체 통합 테스트
- 🔧 전체 시스템 테스트:
  - 로그인 → 환자 선택 → 브리핑
  - Free-text → AI 검토 → 동의/반려 → 완성본
  - 연구 데이터 검색 → 추출 → 통계 → 내보내기
- 🤖 버그 발견 → Claude Code에게 수정 요청
- 반복 테스트 + 안정화

### Day 41: 배포
- 🤖 Claude Code에게: Streamlit Cloud 또는 로컬 서버 배포
- 🔧 다른 기기에서 접속 테스트

### Day 42: Week 5~6 리뷰
- 전체 시스템 데모
- 🔧 **chart_analyzer.py 코드 정리**
  - 분석결과_저장()의 print() 제거 → return으로 결과만 돌려주기 (웹앱 호환)
  - 함수 내부의 from util import → 파일 맨 위로 이동 (import 정리)
- Git 최종 커밋

---

## Week 7~8: 고도화 + 심화 학습 (Day 43~56)

> MCP와 Agent Skills 코스를 들으며 시스템을 확장합니다.

### Day 43~45: 프로토타입 고도화
- 🤖 Claude Code + Cowork: 엣지 케이스 대응, 재시도 로직, 비용 최적화
- 🔧 **동의/반려 시스템 고도화 — 방법 2 적용**
  - 신뢰도 기반 자동 승인: 확실한 것(BP 숫자, 검사 수치)은 자동 저장
  - 애매한 것만 의사에게 확인 (진단 상태, 변경 감지 등)
  - 승인 흐름 단계별 정리:
    - Week 3: 항목별 y/n (기능 확인용)
    - Week 5~6: 전체 승인 + 수정할 것만 선택 (방법 1)
    - Week 7~8: 확실한 건 자동, 애매한 것만 확인 (방법 2) ← 여기!
- 📚 **Introduction to MCP 시작** (AI를 외부 서비스와 연결하는 법)

### Day 46~48: 실제 데이터로 테스트 + 다중 사용자 대비
- 🔧 가상 환자 데이터로 실전 시뮬레이션
- 🧠 프롬프트 최종 튜닝
- 🔧 성능 및 비용 분석
- 🔧 **다중 사용자 대비 — 진단명 표준화 (이 단계에서 적용!)**
  - 진단 테이블에 표준코드(KCD/ICD) 칸 활용
  - AI가 진단명 → KCD 코드 자동 매핑 (가능한 것만)
  - 매핑 안 되는 진단은 NULL → 연구 시 AI가 후보 추려서 의사에게 제시
  - 의사마다 다른 표현 → AI가 핵심 진단명 + 비고로 분리 저장
  - 비고 칸 활용: "고혈압(LSM)" → 진단명="고혈압", 비고="LSM"
- 🔧 **다중 사용자 대비 — DB 동시 접근 안전성**
  - chart_analyzer.py의 주의메모 저장: 읽기→수정 사이에 다른 작업 끼어드는 문제
  - 현재: conn으로 읽고 close → 별도 방문기록수정() 호출 (사이에 gap)
  - 개선: 트랜잭션으로 읽기+수정을 하나로 묶기 (동시 접근 시 데이터 보호)
- 📚 Introduction to MCP 계속 + **Intro to Agent Skills 시작**

### Day 49~51: AI 에이전트 심화
- 🤖 Claude Code 고급: Multi-agent 워크플로우, Skills 만들기, GitHub PR 자동 리뷰
- 🤖 Cowork 심화: 스케줄링, 플러그인/커넥터
- 🔧 **외부 기록 사진 분석 기능 추가 (image_reader.py)**
  - 다른 병원 기록을 사진 촬영 → AI가 이미지 분석(OCR + 의미 파악) → JSON 정형화
  - 의사 확인 후 기존 DB 함수(검사결과추가, 진단추가 등)로 저장
  - 기존 코드 수정 없이 새 모듈만 만들어서 import (모듈 분리 원칙)
  - Claude API의 이미지 분석 기능 활용 (텍스트 분석과 코드 거의 동일)
- 📚 MCP 완료 + Agent Skills 완료

### Day 52~54: 포트폴리오 + 문서화
- 🤖 Claude Code에게: README.md, 프로젝트 구조 문서 작성
- 🔧 직접 작성 (AI가 대체 불가):
  - 프로젝트 동기 (의사 관점의 문제 정의)
  - 기술 선택 이유
  - 향후 계획

### Day 55~56: 마무리 + 향후 방향
- 전체 시스템 최종 데모
- 법률/규제 검토 체크리스트
- 향후 방향:
  - 실제 임상 적용 요건
  - 보안 강화 계획
  - 의료 AI 업계 탐색 시작
  - 추가 학습 경로 선택 (학술/전문가/창업)

---

## Anthropic 코스 수강 가이드

### 필수 코스 (커리큘럼과 병행)

**Claude 101** (Week 1, 약 2~3시간)
- Claude 기본 사용법, 핵심 기능 이해
- 이미 아는 내용은 건너뛰어도 됨
- 수강 방법: 틈날 때 빠르게 훑기

**AI Fluency: Framework & Foundations** (Week 1~2, 약 4~5시간)
- AI와 효과적/윤리적으로 협업하는 법
- 의료 AI 윤리와 직결되는 내용
- 수강 방법: 출퇴근길, 점심시간 활용

**Claude Code in Action** (Week 1~2, 약 3~4시간)
- Claude Code 설치부터 실전 활용까지
- 커리큘럼의 에이전트 트랙과 직접 연결
- 수강 방법: Claude Code 실습 전에 해당 섹션 먼저 보기
- Coursera에서도 수강 가능 (퀴즈, AI 코치 기능 추가)

**Building with the Claude API** (Week 3, 약 4~5시간)
- API 키 발급부터 프롬프트 엔지니어링, 스트리밍, 도구 사용까지
- 커리큘럼 Week 3 API 연동과 직접 병행
- 수강 방법: API 작업하는 날 관련 섹션 먼저 보고 실습

### 선택 코스 (8주 완료 후 또는 Week 7~8)

**Introduction to Model Context Protocol** (약 3~4시간)
- AI를 외부 서비스(DB, Google Drive 등)와 연결하는 프로토콜
- 시스템 확장 시 필요

**Introduction to Agent Skills** (약 2~3시간)
- Claude Code에서 재사용 가능한 스킬 만들기
- Claude Code에 충분히 익숙해진 후 수강

### 수강 불필요 (현재)

| 코스 | 이유 |
|------|------|
| Claude with Amazon Bedrock | AWS 클라우드 환경 전용 |
| Claude with Google Vertex AI | Google Cloud 환경 전용 |
| AI Fluency for educators | 교육자 대상 |
| AI Fluency for students | 학생 대상 |
| AI Fluency for nonprofits | 비영리단체 대상 |
| Teaching AI Fluency | 강사 대상 |
| MCP Advanced Topics | 기초 MCP 수료 후 필요시 |

---

## 시간 배분 가이드 (하루 2~3시간)

### Week 1~2: 기초 + 입문 (Anthropic 코스 집중기)
| 활동 | 시간 |
|------|------|
| 🔧 코딩 개념 + 코드 리딩 | 1h |
| 🤖 Claude Code 실습 | 30min |
| 📚 Anthropic 코스 | 30min~1h |

### Week 3~4: API 연동 + 연구 모듈
| 활동 | 시간 |
|------|------|
| 🤖 Claude Code로 기능 구현 | 1h |
| 🔧 결과 검토 + 테스트 | 30min |
| 🧠 프롬프트 작업 | 30min |
| 📚 Building with Claude API (Week 3만) | 30min |

### Week 5~6: 프론트엔드 + 통합
| 활동 | 시간 |
|------|------|
| 🤖 Claude Code + 바이브코딩 | 1.5h |
| 🔧 테스트 + 검증 | 30min~1h |

### Week 7~8: 고도화 + 심화
| 활동 | 시간 |
|------|------|
| 🤖 에이전트 심화 작업 | 1.5h |
| 📚 MCP + Agent Skills 코스 | 30min~1h |
| 🔧 문서화 + 마무리 | 30min |

---

## "AI에게 시키고 검토하기" 체크리스트

### 데이터 흐름 검증
- [ ] 데이터가 어디서 들어와서 어디로 가는지 추적 가능한가?
- [ ] 불러오기 없이 저장하면 데이터 날아가는 구조는 아닌가?
- [ ] 불필요한 데이터가 AI에게 전송되고 있지는 않은가?

### 에러 처리 검증
- [ ] 잘못된 입력에 프로그램이 죽지 않는가?
- [ ] 파일이 없거나 깨졌을 때 대처가 되어있는가?
- [ ] API 호출 실패 시 재시도 로직이 있는가?

### 의학적 검증 (선생님만 가능!)
- [ ] AI의 의학적 판단이 적절한가?
- [ ] 프롬프트가 필요한 모든 검토 항목을 포함하는가?
- [ ] 출력 형식이 실제 차트 양식과 맞는가?
- [ ] 의학적 오류 검증이 있는가? (이완기 > 수축기 등)

### 보안 검증
- [ ] API 키가 코드에 하드코딩되어 있지 않은가?
- [ ] 환자 데이터가 GitHub에 올라가지 않는가?
- [ ] .gitignore가 제대로 설정되어 있는가?

---

## 중요도 순위 (v5 최종)

1. **데이터 흐름 이해** — AI가 만든 코드를 검증하는 핵심 능력
2. **프롬프트 엔지니어링** — AI 성능의 90%를 결정, 에이전트에게 시킬 수 없음
3. **데이터베이스 설계** — 의사만 할 수 있는 영역
4. **AI 에이전트 활용법** — 생산성을 결정하는 도구 숙련도
5. **코드 리딩 능력** — AI가 만든 코드를 읽고 문제를 찾는 능력
6. **AI 원리 이해** — AI Fluency 코스 + LLM 개념 (판단력의 기반)
7. **코드 문법** — 까먹어도 AI에게 물어보면 됨

---

## 8주 완료 후 추천 학습 경로

### 즉시 (수료 직후)
- Anthropic 코스 중 MCP Advanced Topics (시스템 확장)
- 프로토타입을 다른 의사에게 보여주고 피드백 수집

### 1~3개월 후 (방향 탐색)
- Andrew Ng Coursera 강의 (AI 학술 이해) — 2주 맛보기
- KoSAIM 의료인공지능학회 세미나 참석 — 네트워킹
- 의료 AI 스타트업 탐색 — 프로토타입 가지고 대화

### 6개월 후 (방향 확정 후)
- 갈래 1: MIT AI in Healthcare (edX) — 학술 경로
- 갈래 2: 의료 AI 회사 합류 — 전문가 경로
- 갈래 3: Y Combinator Startup School — 창업 경로
