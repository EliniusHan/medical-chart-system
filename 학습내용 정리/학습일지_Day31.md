# 학습일지 Day 31

## 날짜: 2026-04-13

## 진행 내용

### Python 3.13 + Streamlit 설치 (전날 밤)
- brew install python@3.13 → 심볼릭 링크 생성
- 가상환경 .venv 생성 (Python 3.13.13)
- 모든 패키지 재설치 (anthropic, pandas, scipy, statsmodels, matplotlib, seaborn, requests)
- Streamlit 1.56.0 설치
- VS Code가 .venv 자동 활성화 확인

### 프론트엔드 설계 (와이어프레임)
- 전체 화면 구조 설계 → 4번 반복 수정
- 최종 구조:
  - 사이드바: 환자 목록 전용 (검색 + 신환등록 + 목록)
  - 메인: 홈 / 환자상세 / 연구 / 설정 / 신환등록
  - 사이드바 헤더: "의료 차트" + 홈/연구 버튼
  - 사이드바 하단: 수동입력 + 설정 + 언어 + 로그아웃 아이콘

### 주요 설계 결정
- [DECISION] 인사이트를 별도 메뉴에서 홈으로 통합
- [DECISION] 신환등록 + 환자목록을 "환자"로 통합 → 이후 사이드바로 이동
- [DECISION] 환자 상세: 좌(탭 4개) + 우(전체이력 항상 표시)
- [DECISION] 전체이력: 날짜별 정렬(기본) / 항목별 정렬 탭
- [DECISION] 사이드바 접기 기능 포기 (Streamlit 한계)
- [DECISION] React 전환은 54일 완료 후 추가 과정으로

### app.py 구현 + 반복 수정

#### 레이아웃 변경 이력
1. 초기: 사이드바(메뉴 5개) + 메인(환자목록+상세 split)
2. v2: 인사이트→홈 통합, 신환등록+환자목록 통합
3. v3: 언어 선택 추가, 사이드바 접기/펴기 추가
4. v4: 사이드바=환자목록 전용, 메뉴→헤더로 이동
5. 최종: 환자상세 좌우분할 (탭+전체이력)

#### 환자 상세 화면
- 헤더: 이름 / 병록번호 / 나이/성별 / 생년월일 (한 줄, 컴팩트)
- 가족력 + 약부작용이력: 헤더 아래 인라인 편집 + 저장 버튼
- 좌측: 탭 4개 (브리핑, 진료기록, 수정, 삭제)
- 우측: 전체이력 (날짜별/항목별 정렬)

#### 전체이력 개선
- 내부 ID(방문id, 진단id 등) 프론트에서 숨김
- 날짜별 그룹핑 + 테이블 표시
- 날짜 형식 통일 (_날짜_정규화: YYMMDD → YYYY-MM-DD)
- 미래 검사처방 → 추적계획 섹션으로 프론트 분류
- 방문 기록 "보기" 버튼 → @st.dialog 팝업으로 free_text 표시

#### 네비게이션
- 뒤로가기: page_history 스택 + 각 페이지 헤더에 "← 뒤로" 버튼
- 홈 데일리 체크: 항목 자체가 버튼 → 클릭하면 해당 환자로 이동

#### 환자 검색 개선
- 검색 시 전체 목록 유지 + 매칭 환자 최상단으로
- 첫 번째 매칭 환자 자동 선택
- 없는 환자 검색 시 @st.dialog 경고 팝업

#### 사이드바 최적화
- 환자 목록만 스크롤 (st.container(height=400))
- 하단 아이콘(설정/언어/로그아웃) 고정

### Streamlit 한계 확인
- 사이드바 아이콘만 남기고 접기: 불가능 (완전 열림/완전 닫힘만 지원)
- 상단 패딩 제거: CSS로 제한적 (header 숨겨도 여백 남음)
- 스크롤 완전 분리: st.container(height=N)으로 부분 해결
- 버튼 스타일 커스텀: 제한적 (CSS 오버라이드 필요)

### 커리큘럼 업데이트
- Day 53~54 향후 방향에 React 전환 계획 추가
  - 54일 완료 후 추가 2~3주
  - FastAPI로 백엔드 API화 + React/Next.js 프론트

## 현재 파일 구조
```
~/Desktop/Python/
  app.py (신규! Streamlit 웹앱)
  main_system.py, util.py, chart_analyzer.py, briefing_generator.py,
  research_module.py, anonymizer.py, backup.py, public_db.py,
  practice_analyzer.py, CLAUDE.md, .env, 환자DB.db,
  .venv/ (Python 3.13 가상환경)
```

## 다음 할 것 (Day 32)
- [ ] 브리핑 탭 → briefing_generator 연결
- [ ] 진료기록 탭 → chart_analyzer 5단계 연결
- [ ] 수정/삭제 탭 → util.py 함수 연결
- [ ] 전체이력 UI 추가 다듬기
- [ ] 매일 코드 리딩 + 복습 퀴즈
