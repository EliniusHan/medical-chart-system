# 차트 분석기 (Claude API 연동)
# 흐름: AI분석(1st API) → 제안승인 → free-text 업데이트 → 의사수정 → 테이블저장(2nd API 선택)
import os
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic

DB경로 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "환자DB.db")
from util import (
    환자전체기록조회, 나이계산,
    방문기록_일괄수정,
    진단추가, 검사결과추가, 영상검사추가, 추적계획추가,
    환자정보수정,
    처방추가, 검사처방추가,
    api_재시도,
)
from anonymizer import api_익명화, api_복원
from public_db import 처방_안전성_조회, pubmed_검색
from practice_analyzer import 의사패턴_요약생성

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ============================================================
# 공통 추출 규칙 (SYSTEM_PROMPT + REEXTRACT_SYSTEM 공유)
# ============================================================
_EXTRACTION_RULES = """
=== 검사 분류 최우선 원칙 ===
결과 수치/소견이 차트에 적혀 있는가?
  YES → lab_results 또는 imaging
  NO  → test_orders (검사처방)
이 원칙은 아래의 모든 규칙보다 우선합니다.

의사의 차트 작성 스타일 규칙:

1. 섹션 구분:
   * (1개) = 섹션 구분자
   ** (2개) = 계획 항목. 날짜 유무로 '이미 한 것'과 '앞으로 할 것'을 구분.

   [날짜 없는 **] → 방문일에 시행/처방한 것

   - **약 N개월
     → 처방(일수=N×30, 오늘 처방), 처방요약 포함 (추적계획 ❌)

   - **Lab(검사명) 또는 **혈액검사명
     → 검사처방: 검사명="Lab (기본패널 + 괄호 안 항목)", 처방일=방문일(YYMMDD)
     → 결과 수치가 없으므로 검사결과(lab_results)에 넣지 말 것!

   - **영상검사명 (CXR, EKG, 초음파 등)
     → 검사처방: 검사명=해당 검사, 처방일=방문일(YYMMDD)
     → 결과 소견이 없으므로 영상검사(imaging)에 넣지 말 것!

   [날짜 있는 **] → 해당 월에 할 예정

   - **YYMM Lab(검사명)
     → 검사처방(처방일=YYMM00) + 추적계획(예정일=YYMM00)

   - **YYMM 검사명 (Chest CT, BMD 등)
     → 검사처방(처방일=YYMM00) + 추적계획(예정일=YYMM00)

   - **YYMM 약 N개월
     → 처방(일수=N×30) + 추적계획(예정일=YYMM00)

   예시:
   **약 2개월              → 처방(일수=60, 오늘 처방) + 처방요약 (추적계획 ❌)
   **Lab(A1c, Lipid)       → 검사처방: 검사명="Lab (CBC, LFT, BUN/Cr, 전해질, A1c, Lipid)", 처방일=방문일
   **경동맥 초음파          → 검사처방: 검사명="경동맥 초음파", 처방일=방문일
   **CXR                   → 검사처방: 검사명="CXR", 처방일=방문일
   **EKG                   → 검사처방: 검사명="EKG", 처방일=방문일
   **2604 Lab(A1c, Lipid)  → 검사처방(처방일=260400) + 추적계획(예정일=260400)
   **2701 Chest CT         → 검사처방(처방일=270100) + 추적계획(예정일=270100)

   - *가 없어도 내용을 보고 섹션을 추론할 것

2. 하위 내용 표시:
   줄 앞에 '-'가 붙으면 바로 윗줄의 하위 내용.
   상위+하위를 묶어서 하나의 맥락으로 이해.
   영상검사 결과요약에 하위 항목들을 포함시킬 것.

3. 진단명 표기:
   #으로 시작하면 진단명
   #r/o 또는 #의심이 붙으면 상태='의심'
   괄호 안 내용은 비고로 분리
     예: #당뇨전단계(A1c 6.1) → 진단명='당뇨전단계', 비고='A1c 6.1'

4. 표준코드(KCD/ICD) 매핑:
   가능하면 KCD/ICD 코드 매핑. 확실하지 않으면 빈 문자열.

5. 생활습관 해석:
   빈칸 = 이번 방문에서 물어보지 않음 (누락 아님, 지적하지 말 것)
   '비흡연', '없음' = 확인함, 해당 없음

6. 가족력/약부작용이력 감지:
   free-text에서 가족력이나 약부작용 관련 언급 시 감지하여 처리.
   변경유형: 'add'(새 정보), 'modify'(기존 수정), 'remove'(삭제)
   변경 없으면 patient_info의 각 항목 변경유형='', 새값='' 으로 출력.

7. 환자 테이블 정보와 차트 내용 불일치 감지:
   다르면 → 환자 테이블 기준으로 처리

[기존 데이터 비교 규칙]
- 이미 저장된 것과 동일한 값 → "구분": "기존참조" (새로 저장 안 함)
- 기존과 다른 값 → "구분": "변경감지" + "기존값" 필드 추가
- 완전히 새로운 값 → "구분": "신규"

** 계획 분류 규칙 — 매우 중요:
  YYMM + 검사/영상 → 검사처방 ✅ + 추적계획 ✅
  YYMM + 약 → 처방(일수 계산) ✅ + 추적계획 ✅
  YYMM + 재방문 → 추적계획만 ✅
  YYMM 없이 '약 N개월' → 처방만 ✅ (추적계획 ❌)

  핵심:
  YYMMDD(6자리) 있으면 → 추적계획 ✅
  YYMM(4자리) 있으면 → 추적계획 ✅ (YYMM00으로 저장)
  날짜 없으면 → 해당 테이블만, 추적계획 ❌

처방 추출 규칙:
  차트에서 약물 처방을 개별 약품 단위로 추출.
  예: 'rosuvastatin 10mg qd 시작' → {약품명: rosuvastatin, 용량: 10mg, 용법: qd}
  예: 'amlodipine 5mg + losartan 50mg' → 2건 각각 추출
  예: '**약 2개월' → 기존 처방 목록 참조, 동일 약품, 일수=60, 추적계획 ❌
  처방요약 칸은 전체 처방 내용 텍스트 요약으로 유지.

  '유지' 처방도 반드시 추출하세요.
  매 방문마다 처방된 약은 신규/변경/유지 관계없이 전부 추출.
  구분 필드로 구분:
    신규 처방 → 구분: '신규'
    용량/용법 변경 → 구분: '변경감지'
    기존과 동일 유지 → 구분: '유지'
  '유지' 처방도 테이블에 저장하여 매 방문마다 처방 이력이 남도록 합니다.

검사처방 추출 규칙:
  날짜 있는 ** 뒤에 검사 내용 → 검사처방(처방일=YYMM00) + 추적계획(예정일=YYMM00)

날짜 변환 규칙:
  YYMMDD (6자리) → 그대로 저장
    예: '260315' → '260315'

  YYMM (4자리) → YYMM00으로 저장
    예: '2603' → '260300'
    예: '**2606 Lab' → 처방일/예정일 '260600'

  절대 하지 말 것:
    '2603' → '260301' ❌
    '2603 FBS 118' → 검사시행일 '260301' ❌ (방문일이나 1일을 채우지 말 것!)
    YYMM 4자리가 있으면 예외 없이 → YYMM00
    00은 '이 달 중 언제인지 모름'을 의미합니다.

날짜 저장 규칙:
  검사결과/영상검사 시행일: YYMMDD 6자리
    → 날짜를 모를 경우(의사가 YYMM만 기재): YYMM00 (01 ❌, 방문일 대체 ❌)
  추적계획 예정일: YYMM00 6자리 (01이 아니라 00!)
  검사처방 처방일: YYMM00 6자리
  방문기록 방문일: YYMMDD 6자리

  날짜 계산 기준:
  - 모든 날짜 계산은 '이 차트의 방문일'을 기준 (오늘 날짜가 아님!)
  - 의사가 날짜를 안 쓰면 방문일 사용
  - '약 2개월' → 방문일 기준 2개월 후 (YYMM00 형식)
  - 날짜 없는 검사/영상 → 시행일 = 방문일 (YYMMDD)
  - 의사가 YYMM 4자리로 검사 수치를 쓰면
    → 정확한 날짜를 모른다는 의미 → 검사시행일 = YYMM00
    → 절대 방문일을 대신 사용하지 말 것! YYMM이 있으면 항상 YYMM00

  추적계획 완료 매칭:
  - 날짜 아닌 내용(검사항목)으로 매칭
  - 예: 추적계획 '2604 Lab(A1c)' + 검사결과 '260510 A1c' → 내용 일치 → 완료 처리

언급되지 않은 항목은 빈 값 또는 빈 리스트로 처리하세요.
"""

SYSTEM_PROMPT = """당신은 내과 전문의의 진료 어시스턴트입니다.
의사가 작성한 차트를 분석하여 다음을 모두 수행하세요.
반드시 JSON만 출력하세요. 설명이나 마크다운 코드블록 없이 순수 JSON만 출력하세요.

=== [A] 데이터 추출 ===

추출 항목:
1. 활력징후 (vitals): 수축기, 이완기, 심박수, 키, 몸무게, BMI (키/몸무게로 자동 계산)
2. 생활습관 (lifestyle): 흡연, 음주, 운동
3. 진단 (diagnoses): 진단명, 상태(활성/의심/종결), 비고, 표준코드(KCD/ICD), 구분
4. 검사결과 (lab_results): 검사시행일, 검사항목, 결과값, 단위, 참고범위, 구분
   ⚠ 결과 수치가 명시된 경우만! 수치 없으면 lab_results 금지 → test_orders로.
5. 영상검사 (imaging): 검사시행일, 검사종류, 결과요약, 주요수치, 구분
   ⚠ 결과 소견이 명시된 경우만! 소견 없으면 imaging 금지 → test_orders로.
6. 추적계획 (tracking): 예정일(YYMM00), 내용, 구분
7. 처방요약 (prescription_summary): 처방 내용 한 줄 요약
8. 처방 (prescriptions): 개별 약품 단위 (약품명, 성분명, 용량, 용법, 일수, 구분)
9. 검사처방 (test_orders): 시행했거나 시행 예정이지만 결과가 없는 검사 전부 (검사명, 처방일, 구분)
10. 환자정보 업데이트 (patient_info): 가족력, 약부작용이력 각각 {변경유형, 기존값, 새값, 근거}

=== 검사 분류 규칙 (최우선 적용) ===

[lab_results vs test_orders]
  판단 기준: 결과 수치가 차트에 적혀 있는가?
  - 수치 있음 (예: "HbA1c 9.5", "LDL 130 mg/dL", "Cr 0.9") → lab_results
  - 수치 없음 (예: "Lab 시행", "**Lab(A1c, Lipid)", "혈액검사 시행") → test_orders
  - "시행" / "처방" / "예정" / "확인" 단어가 있고 결과 수치가 없으면 → 반드시 test_orders

[imaging vs test_orders]
  - 결과 소견 있음 (예: "CXR: 정상 소견", "경동맥 초음파: IMT 1.1mm") → imaging
  - 시행 기록만 있고 소견 없음 (예: "CXR 시행", "EKG 시행", "**CXR") → test_orders

[Lab() 표기법 해석]
  "Lab(A1c, Lipid)" 또는 "**Lab(A1c, Lipid)" 의 의미:
  → 기본 Lab 패널(CBC, LFT, BUN/Cr, 전해질) + 괄호 안 항목(A1c, Lipid)을 함께 시행.
  → test_orders 하나로 통합: 검사명 = "Lab (CBC, LFT, BUN/Cr, 전해질, A1c, Lipid)"
  → 개별 항목으로 쪼개지 말 것.
""" + _EXTRACTION_RULES + """

=== [B] AI 검토 의견 (suggestions) ===

의사가 놓친 것, 추가로 고려할 것만 제안하세요.
의사가 이미 차트에 적었거나 인지하고 있는 내용은 제외!
- 의사가 이미 진단명으로 적은 것 → 다시 알려주지 마세요
- 의사가 이미 차트에 언급한 수치 이상 → 반복하지 마세요
- 의사가 이미 조치를 취한 것 → 다시 권장하지 마세요
- 의사가 언급하지 않은 검사, 의뢰, 주의사항만 제안하세요

검토 의견 제시 시:
- 근거가 되는 가이드라인을 반드시 명시하세요.
  예: '🔴 LDL 145, 목표 미달 [ESC/EAS 2023, 고위험군 <100]'
- DUR에서 금기 사항이 발견되면 반드시 포함하세요.
  예: '⚖ 병용금기 발견: gemfibrozil + rosuvastatin [DUR]'
- PubMed 논문이 관련 있으면 근거로 포함하세요.
  예: '📚 PubMed: High-intensity statin... (NEJM 2023)'
- 급여 정보가 있으면 처방 관련 제안에 명시하세요.
  예: '💡 rosuvastatin 증량 권장 [급여: 고위험군 LDL 100 이상 — 충족]'
- 이전 방문 데이터와 비교하여 악화/개선 추세가 있으면 명시하세요.
  예: '📈 LDL 3회 연속 상승 추세 (94 → 120 → 145)'

검토 의견 출력 형식 예시:
  {"icon": "💡", "content": "rosuvastatin 증량 권장",
   "reason": "LDL 145 목표 미달 [ESC/EAS 2023] / 급여: 충족 / DUR: 병용금기 없음",
   "chart_text": "LDL 목표 미달로 rosuvastatin 증량 고려."}

  {"icon": "⚖", "content": "병용금기 발견",
   "reason": "gemfibrozil + rosuvastatin [DUR 병용금기]",
   "chart_text": "DUR 확인 결과 gemfibrozil과 rosuvastatin 병용금기로 확인되어 처방 조정 필요."}

  {"icon": "💡", "content": "경동맥 초음파 권장",
   "reason": "심혈관 위험인자 다수 / 📚 PubMed: Carotid IMT predicts CV events (JACC 2022)",
   "chart_text": "경동맥 초음파 시행하여 죽상경화 평가 예정."}

각 제안에 차트에 삽입할 문구(chart_text)도 함께 생성하세요.
제안할 것이 없으면 빈 배열 [] 출력.

=== [C] 법적 확인사항 (legal) ===

법적으로 반드시 확인/권고해야 하는 것.
각 항목에 차트에 삽입할 문구(chart_text)를 함께 제안.
예: 임신 가능성 확인(ACEi 처방), 금연 권고(심혈관 고위험군), 간기능 확인(스타틴 신규)
해당 없으면 빈 배열 [] 출력.

=== [D] 설명의무 기록 (informed_consent) ===

새로 처방되거나 변경된 약물이 있으면 주요 부작용과 설명의무 이행 문구(chart_text) 제안.
신규 처방 없으면: {"drugs": [], "side_effects": [], "chart_text": ""}

=== JSON 출력 형식 ===

{
  "extraction": {
    "vitals": {"수축기": 152, "이완기": 96, "심박수": 78, "키": 170, "몸무게": 78, "BMI": 27.0},
    "lifestyle": {"흡연": "하루 반 갑(10년)", "음주": "주 2회 소주 1병", "운동": "안 함"},
    "diagnoses": [{"진단명": "고혈압", "상태": "활성", "비고": "", "표준코드": "I10", "구분": "신규"}],
    "lab_results": [
      // 결과 수치가 명시된 검사만! 수치 없으면 여기 넣지 말 것.
      {"검사항목": "FBS", "결과값": "118", "단위": "mg/dL", "참고범위": "70-100", "검사시행일": "260300", "구분": "신규"}
    ],
    "imaging": [
      // 결과 소견이 명시된 영상검사만! 소견 없으면 여기 넣지 말 것.
      {"검사시행일": "260415", "검사종류": "경동맥초음파", "결과요약": "Rt. IMT 1.1mm", "주요수치": "IMT 1.1mm", "구분": "신규"}
    ],
    "prescriptions": [{"약품명": "amlodipine", "성분명": "", "용량": "5mg", "용법": "qd", "일수": 60, "구분": "신규"}],
    "tracking": [{"예정일": "260500", "내용": "Lab(Lipid, LFT, FBS, A1c)", "구분": "신규"}],
    "test_orders": [
      // 시행했거나 시행 예정이지만 결과가 없는 검사 전부. CXR/EKG 시행도 여기.
      {"검사명": "Lab (CBC, LFT, BUN/Cr, 전해질, Lipid, FBS, A1c)", "처방일": "260300", "구분": "신규"},
      {"검사명": "CXR", "처방일": "260300", "구분": "신규"},
      {"검사명": "EKG", "처방일": "260300", "구분": "신규"}
    ],
    "prescription_summary": "amlodipine 5mg qd + rosuvastatin 10mg qd 시작, 2개월치",
    "patient_info": {
      "가족력": {"변경유형": "add", "기존값": "", "새값": "고혈압(부친)", "근거": "환자 보고"},
      "약부작용이력": {"변경유형": "", "기존값": "", "새값": "", "근거": ""}
    }
  },
  "suggestions": [
    {"icon": "💡", "content": "심전도 검사 고려", "reason": "고혈압 신규 진단 시 기본 평가", "chart_text": "심전도 검사 시행하여 기본 심장 평가 진행 예정."}
  ],
  "legal": [
    {"icon": "⚖", "content": "금연 권고 필요", "reason": "심혈관 고위험군", "chart_text": "심혈관 고위험군으로 금연의 필요성에 대해 설명하고 강력히 권고함."}
  ],
  "informed_consent": {
    "drugs": ["amlodipine", "rosuvastatin"],
    "side_effects": ["부종", "어지럼증", "근육통", "간수치 상승"],
    "chart_text": "상기 처방 약물(amlodipine, rosuvastatin)의 주요 부작용(부종, 어지럼증, 근육통, 간수치 상승)에 대해 환자에게 설명하였으며, 이상 증상 발생 시 즉시 내원하도록 안내함."
  }
}"""


REEXTRACT_SYSTEM = """당신은 의료 데이터 추출 어시스턴트입니다.
최종 확정된 차트에서 데이터만 추출하세요.
검토 의견, 제안, 법적 확인사항, 설명의무 기록은 출력하지 마세요.
반드시 JSON만 출력하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.

추출 항목:
1. 활력징후 (vitals): 수축기, 이완기, 심박수, 키, 몸무게, BMI
2. 생활습관 (lifestyle): 흡연, 음주, 운동
3. 진단 (diagnoses): 진단명, 상태(활성/의심/종결), 비고, 표준코드, 구분
4. 검사결과 (lab_results): 검사시행일, 검사항목, 결과값, 단위, 참고범위, 구분
   ⚠ 결과 수치가 명시된 경우만! 수치 없으면 test_orders로.
5. 영상검사 (imaging): 검사시행일, 검사종류, 결과요약, 주요수치, 구분
   ⚠ 결과 소견이 명시된 경우만! 소견 없으면 test_orders로.
6. 추적계획 (tracking): 예정일(YYMM00), 내용, 구분
7. 처방요약 (prescription_summary): 처방 내용 한 줄 요약
8. 처방 (prescriptions): 약품명, 성분명, 용량, 용법, 일수, 구분
9. 검사처방 (test_orders): 시행했거나 시행 예정이지만 결과가 없는 검사 전부 (검사명, 처방일, 구분)
10. 환자정보 업데이트 (patient_info): 가족력, 약부작용이력

=== 검사 분류 규칙 (최우선 적용) ===

  결과 수치 있음 → lab_results / 수치 없음 → test_orders
  결과 소견 있음 → imaging / 소견 없음 → test_orders
  "Lab(A1c, Lipid)" → test_orders 하나로: "Lab (CBC, LFT, BUN/Cr, 전해질, A1c, Lipid)"
""" + _EXTRACTION_RULES + """

JSON 형식 — extraction 키 하나만 포함:
{
  "extraction": {
    "vitals": {},
    "lifestyle": {},
    "diagnoses": [],
    "lab_results": [],
    "imaging": [],
    "prescriptions": [],
    "tracking": [],
    "test_orders": [],
    "prescription_summary": "",
    "patient_info": {
      "가족력": {"변경유형": "", "기존값": "", "새값": "", "근거": ""},
      "약부작용이력": {"변경유형": "", "기존값": "", "새값": "", "근거": ""}
    }
  }
}"""


# ============================================================
# 내부 헬퍼
# ============================================================
def _parse_json_response(text):
    """AI 응답에서 JSON 파싱 (마크다운 코드블록 제거 포함)"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f" [오류] AI 응답을 JSON으로 파싱할 수 없습니다.")
        print(f" 원본 응답:\n{text[:500]}")
        return None



def _익명화_api호출(system, 프롬프트, 매핑, max_tokens=4096):
    """익명화된 프롬프트로 API 호출 후 복원. Returns: 응답텍스트 or None"""
    응답 = api_재시도(lambda: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": 프롬프트}]
    ))
    if not 응답:
        return None
    텍스트 = api_복원(응답.content[0].text.strip(), 매핑)
    return 텍스트


# ============================================================
# 공공 DB 조회 헬퍼 (차트분석 내부용)
# ============================================================

# 흔한 내과 진단명 → 영문 변환 테이블
_진단명_영문 = {
    "고혈압": "hypertension",
    "고지혈증": "dyslipidemia",
    "당뇨": "diabetes mellitus",
    "당뇨전단계": "prediabetes",
    "갑상선기능저하증": "hypothyroidism",
    "갑상선기능항진증": "hyperthyroidism",
    "통풍": "gout",
    "골다공증": "osteoporosis",
    "만성콩팥병": "chronic kidney disease",
    "심방세동": "atrial fibrillation",
    "심부전": "heart failure",
    "관상동맥질환": "coronary artery disease",
    "뇌졸중": "stroke",
    "빈혈": "anemia",
    "지방간": "fatty liver",
}


def _free_text에서_약품명_추출(free_text):
    """free-text에서 약품명 패턴 간단 추출 (영문 소문자 + 숫자mg 조합).
    완벽하지 않아도 됨 — AI가 나중에 정확히 추출함."""
    import re
    패턴 = r'\b[a-z]{4,}(?:\s*\d+\s*mg)?\b'
    후보 = re.findall(패턴, free_text.lower())
    제외목록 = {"with", "that", "this", "from", "have", "been", "will", "also",
               "than", "more", "less", "after", "before", "normal", "blood",
               "free", "text", "note", "plan", "done", "left", "right"}
    seen = set()
    약품목록 = []
    for w in 후보:
        w = w.strip()
        if w not in seen and w not in 제외목록:
            seen.add(w)
            약품목록.append(w)
        if len(약품목록) >= 5:
            break
    return 약품목록


def _free_text에서_pubmed_검색어_추출(free_text):
    """free-text에서 진단명을 찾아 영문 검색어 생성."""
    for 한글, 영문 in _진단명_영문.items():
        if 한글 in free_text:
            return f"{영문} treatment guideline"
    return None


def _공공DB_조회(free_text):
    """처방 안전성(DUR/e약은요/급여) + PubMed 조회.
    Returns: (공공DB결과_문자열, 조회성공여부)"""
    try:
        약품목록 = _free_text에서_약품명_추출(free_text)
        검색어 = _free_text에서_pubmed_검색어_추출(free_text)

        안전성결과 = 처방_안전성_조회(약품목록) if 약품목록 else {}
        pubmed결과 = pubmed_검색(검색어) if 검색어 else []

        dur_정보 = {약품: v["dur"] for 약품, v in 안전성결과.items()}
        약품정보 = {약품: v["약품정보"] for 약품, v in 안전성결과.items()}
        급여정보 = {약품: v["급여정보"] for 약품, v in 안전성결과.items()}

        조회결과 = (
            "[공공 DB 조회 결과 — 참고하여 검토 의견에 반영하세요]\n\n"
            "[DUR 정보]\n" + json.dumps(dur_정보, ensure_ascii=False, indent=2) + "\n\n"
            "[약품 정보 (e약은요)]\n" + json.dumps(약품정보, ensure_ascii=False, indent=2) + "\n\n"
            "[급여 정보]\n" + json.dumps(급여정보, ensure_ascii=False, indent=2) + "\n\n"
            "[PubMed 검색 결과]\n" + json.dumps(pubmed결과, ensure_ascii=False, indent=2) + "\n\n"
            "위 정보를 검토 의견(💡), 법적 확인(⚖), 설명의무에 활용하세요.\n"
            "DUR에서 병용금기가 발견되면 반드시 ⚖ 법적 확인사항에 포함하세요.\n"
            "PubMed 논문은 관련 있는 것만 검토 의견에 포함하세요.\n"
            "급여 정보가 있으면 처방 관련 제안에 급여 여부를 명시하세요."
        )

        return 조회결과, True

    except Exception as e:
        print(f"  ⚠ 공공 DB 조회 실패: {e}")
        return "[공공 DB 조회 결과 — 조회 실패 또는 해당 정보 없음. 내부 지식으로 판단하세요.]", False


# ============================================================
# Step 2: 1번째 API — 분석 + 추출 + 제안
# ============================================================
def 차트분석(환자id, free_text, 방문일=None):
    """AI 분석: 데이터 추출 + 검토의견 + 법적확인 + 설명의무 전부 수행.
    Returns: dict(extraction, suggestions, legal, informed_consent) or None"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    나이 = 나이계산(기록["환자"]["생년월일"])
    if 나이 is not None:
        기록["환자"]["나이"] = f"{나이}세"

    # 공공 DB 조회 (AI API 호출 전)
    공공DB_문자열, 조회성공 = _공공DB_조회(free_text)
    if not 조회성공:
        print("  ⚠ 공공 DB 조회 실패. AI 내부 지식으로 검토합니다.")

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_free_text = free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else free_text

    패턴요약 = 의사패턴_요약생성()
    패턴요약_섹션 = f"\n[의사 진료 패턴 — 참고하여 맥락에 맞는 검토 의견 제시에 활용]\n{패턴요약}\n" if 패턴요약 else ""

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[오늘 free-text]
{익명_free_text}

{공공DB_문자열}{패턴요약_섹션}
위 free-text를 분석하여 기존 데이터와 비교한 뒤, 지정된 JSON 형식으로 출력하세요."""

    응답텍스트 = _익명화_api호출(SYSTEM_PROMPT, 프롬프트, 매핑)
    매핑 = None
    return _parse_json_response(응답텍스트)


# ============================================================
# Step 3: 제안 표시 + 승인 (extraction은 메모리 보관)
# ============================================================
def 제안확인(분석결과):
    """💡⚖설명의무 제안만 표시. extraction은 그대로 반환.
    Returns: (extraction, approved_texts: list[str])
             approved_texts가 비면 제안 없음 또는 전부 거부."""
    extraction = 분석결과.get("extraction", {})
    suggestions = 분석결과.get("suggestions", [])
    legal = 분석결과.get("legal", [])
    informed_consent = 분석결과.get("informed_consent", {})

    approved_texts = []
    has_any = bool(suggestions or legal or informed_consent.get("chart_text"))

    if not has_any:
        print("\n [AI 검토] 검토 의견 없음")
        return extraction, approved_texts

    print("\n=== AI 검토 결과 ===")

    # ── AI 검토 의견 (💡) ──
    if suggestions:
        print("\n── AI 검토 의견 ──")
        for i, s in enumerate(suggestions, 1):
            print(f"  💡 {i}. {s.get('content', '')} ({s.get('reason', '')})")
            chart_text = s.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 법적 확인사항 (⚖) ──
    if legal:
        print("\n── 법적 확인사항 ──")
        for i, l in enumerate(legal, 1):
            print(f"  ⚖ {i}. {l.get('content', '')} ({l.get('reason', '')})")
            chart_text = l.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 설명의무 기록 ──
    ic_text = informed_consent.get("chart_text", "")
    if ic_text:
        drugs = ", ".join(informed_consent.get("drugs", []))
        se = ", ".join(informed_consent.get("side_effects", []))
        print(f"\n── 설명의무 기록 ──")
        if drugs:
            print(f"   약물: {drugs}  |  부작용: {se}")
        print(f"   제안: \"{ic_text}\"")
        if input("   → 차트에 반영할까요? (y/n): ").strip().lower() == "y":
            approved_texts.append(ic_text)

    return extraction, approved_texts


# ============================================================
# Step 4: 승인된 chart_text를 free-text 아래에 추가 (API 없음)
# ============================================================
def 제안_free_text_추가(free_text, approved_texts):
    """승인된 chart_text들을 free_text 아래에 덧붙인다."""
    if not approved_texts:
        return free_text
    추가문구 = "\n".join(approved_texts)
    구분선 = "\n---\n" if free_text.strip() else ""
    return free_text + 구분선 + 추가문구


# ============================================================
# Step 5: 의사 직접 수정
# ============================================================
def 의사_최종수정(free_text):
    """차트를 의사에게 보여주고 직접 수정하게 한다.
    새 내용 입력 시 교체. 빈 줄 입력 시 원본 그대로 확정."""
    print("\n=== 최종 차트 확인 ===")
    print("─" * 50)
    print(free_text)
    print("─" * 50)
    print("수정이 필요하면 전체 내용을 다시 입력하세요.")
    print("(수정 없이 확정하려면 바로 Enter)")

    줄들 = []
    while True:
        줄 = input()
        if 줄 == "":
            break
        줄들.append(줄)

    return "\n".join(줄들) if 줄들 else free_text


# ============================================================
# Step 6 내부: 추출 데이터 요약 표시
# ============================================================
def _추출데이터_요약표시(extraction):
    """추출된 데이터를 한눈에 보기 출력"""
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"  [활력징후] {bp}{hr}{ht}{wt}{bmi}")

    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"  [생활습관] {', '.join(항목들)}")

    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"  [진단] {목록}")

    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"  [검사결과] {목록}")

    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"  [영상검사] {목록}")

    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"  [처방] {목록}")

    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"  [추적계획] {목록}")

    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"  [검사처방] {목록}")

    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"  [처방요약] {ps}")

    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if 변경 and 변경.get("변경유형") and 변경.get("새값"):
            print(f"  [환자정보-{항목}] ({변경['변경유형']}) {변경.get('새값', '')}")


# ============================================================
# Step 6 내부: 항목별 y/n 승인
# ============================================================
def _추출데이터_항목별_승인(extraction):
    """항목별 카테고리 단위로 y/n 질문. Returns: approved_data dict"""
    approved = {}

    # 활력징후
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기", "심박수", "키", "몸무게"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"\n  [활력징후] {bp}{hr}{ht}{wt}{bmi}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["vitals"] = vitals

    # 생활습관
    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"\n  [생활습관] {', '.join(항목들)}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lifestyle"] = lifestyle

    # 진단
    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"\n  [진단] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["diagnoses"] = diagnoses

    # 검사결과
    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"\n  [검사결과] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lab_results"] = labs

    # 영상검사
    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"\n  [영상검사] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["imaging"] = imaging

    # 처방
    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"\n  [처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescriptions"] = prescriptions

    # 추적계획
    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"\n  [추적계획] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["tracking"] = tracking

    # 검사처방
    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"\n  [검사처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["test_orders"] = test_orders

    # 처방요약
    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"\n  [처방요약] {ps}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescription_summary"] = ps

    # 환자정보
    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if not 변경 or not 변경.get("변경유형"):
            continue
        유형표시 = {"add": "추가", "modify": "수정", "remove": "삭제"}.get(변경.get("변경유형", ""), "변경")
        print(f"\n  [환자정보-{항목}] ({유형표시}) {변경.get('기존값', '')} → {변경.get('새값', '')}")
        if 변경.get("근거"):
            print(f"     근거: {변경['근거']}")
        if input("  → 업데이트할까요? (y/n): ").strip().lower() == "y":
            if "patient_info" not in approved:
                approved["patient_info"] = {}
            approved["patient_info"][항목] = 변경

    return approved


# ============================================================
# Step 6: 2번째 API — 재추출 (선택적)
# ============================================================
def 재추출(환자id, final_free_text, 방문일):
    """최종 확정 free-text로 데이터만 재추출 (2번째 API).
    Returns: extraction dict or None"""
    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_text = final_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else final_free_text

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[최종 확정 차트]
{익명_text}

위 최종 차트에서 데이터를 추출하세요."""

    응답텍스트 = _익명화_api호출(REEXTRACT_SYSTEM, 프롬프트, 매핑)
    매핑 = None
    결과 = _parse_json_response(응답텍스트)
    if 결과:
        return 결과.get("extraction", 결과)
    return None


# ============================================================
# Step 7: 테이블 저장
# ============================================================
def 분석결과_저장(환자id, 방문id, final_free_text, approved_data):
    """승인된 항목을 유형별로 테이블에 저장. Returns: 저장건수"""
    저장건수 = 0

    # --- 방문 테이블 일괄 업데이트 (free_text, 활력징후, 생활습관, 처방요약) ---
    # 방문기록수정()을 여러 번 호출하면 매번 새 레코드가 생성되므로
    # 한 번의 UPDATE로 처리하여 불필요한 레코드 복사 방지
    방문_업데이트 = {}
    vitals = approved_data.get("vitals", {})
    lifestyle = approved_data.get("lifestyle", {})
    ps = approved_data.get("prescription_summary", "")

    if final_free_text:
        방문_업데이트["free_text"] = final_free_text
    for 필드 in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"]:
        if vitals.get(필드) is not None:
            방문_업데이트[필드] = vitals[필드]
    for 필드 in ["흡연", "음주", "운동"]:
        if lifestyle.get(필드):
            방문_업데이트[필드] = lifestyle[필드]
    if ps:
        방문_업데이트["처방요약"] = ps

    if 방문_업데이트:
        방문기록_일괄수정(방문id, 방문_업데이트)
        저장건수 += 1
        if final_free_text:
            print(f"  → free_text 저장 완료")
        if vitals:
            bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
            print(f"  → 활력징후 저장: {bp}")
        if lifestyle:
            print(f"  → 생활습관 저장 완료")
        if ps:
            print(f"  → 처방요약 저장: {ps[:40]}{'...' if len(ps) > 40 else ''}")

    # --- 진단 ---
    for d in approved_data.get("diagnoses", []):
        진단추가(환자id, 방문id, d["진단명"], d.get("상태", "활성"), d.get("비고", ""), d.get("표준코드", None))
        저장건수 += 1
        print(f"  → 진단 저장: {d['진단명']} ({d.get('상태', '')})")

    # --- 검사결과 ---
    for k in approved_data.get("lab_results", []):
        검사결과추가(환자id, k.get("검사시행일", ""), k["검사항목"], k.get("결과값", ""),
                   k.get("단위", ""), k.get("참고범위", ""), 방문id=방문id)
        _검사처방_시행완료_매칭(환자id, k.get("검사시행일", ""), k["검사항목"])
        저장건수 += 1
        print(f"  → 검사결과 저장: {k['검사항목']} {k.get('결과값', '')}")

    # --- 영상검사 ---
    for e in approved_data.get("imaging", []):
        영상검사추가(환자id, e.get("검사시행일", ""), e["검사종류"], e.get("결과요약", ""),
                   e.get("주요수치", ""), 방문id=방문id)
        저장건수 += 1
        print(f"  → 영상검사 저장: {e['검사종류']}")

    # --- 처방 ---
    for p in approved_data.get("prescriptions", []):
        처방추가(환자id, 방문id, p.get("약품명", ""), p.get("성분명", ""), p.get("용량", ""), p.get("용법", ""), p.get("일수", 0))
        저장건수 += 1
        print(f"  → 처방 저장: {p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')}")

    # --- 추적계획 ---
    for t in approved_data.get("tracking", []):
        추적계획추가(환자id, 방문id, t.get("예정일", ""), t.get("내용", ""))
        저장건수 += 1
        print(f"  → 추적계획 저장: {t.get('내용', '')}")

    # --- 검사처방 ---
    # 처방일 fallback: AI가 처방일을 비워둔 경우 방문일로 대체
    _방문일_fallback = ""
    if approved_data.get("test_orders"):
        _conn = sqlite3.connect(DB경로)
        try:
            row = _conn.execute(
                "SELECT 방문일 FROM 방문 WHERE 방문id=? AND 유효여부=1", (방문id,)
            ).fetchone()
            if row:
                _방문일_fallback = row[0]
        finally:
            _conn.close()

    for o in approved_data.get("test_orders", []):
        처방일 = o.get("처방일", "") or _방문일_fallback
        검사처방추가(환자id, 방문id, o.get("검사명", ""), 처방일)
        저장건수 += 1
        print(f"  → 검사처방 저장: {o.get('검사명', '')} (예정: {처방일})")

    # --- 환자정보 업데이트 ---
    기존환자 = 환자전체기록조회(환자id)
    for 항목명, 변경 in approved_data.get("patient_info", {}).items():
        변경유형 = 변경.get("변경유형", "")
        새값 = 변경.get("새값", "")
        기존값 = 기존환자["환자"].get(항목명, "") if 기존환자 else ""

        if 변경유형 == "add":
            최종값 = (기존값 + ", " + 새값).strip(", ") if 기존값 else 새값
        elif 변경유형 == "modify":
            최종값 = 새값
        elif 변경유형 == "remove":
            최종값 = ""
        else:
            continue

        환자정보수정(환자id, 항목명, 최종값)
        저장건수 += 1
        print(f"  → {항목명} 업데이트: {최종값}")

    return 저장건수


# ============================================================
# 전체 흐름 orchestrator (main_system.py에서 호출)
# ============================================================
def 차트분석_저장_전체흐름(환자id, 방문id, free_text, 방문일=None):
    """Steps 2~7 전체 실행.
    방문id는 호출 전에 미리 생성되어 있어야 함.
    Returns: (final_free_text, 저장건수) or (None, 0) on failure"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    # Step 2: AI 분석
    print("\n [AI 분석 중...]")
    분석결과 = 차트분석(환자id, free_text, 방문일)
    if not 분석결과:
        print(" [오류] AI 분석 실패")
        return None, 0

    # Step 3: 제안 확인 (extraction 메모리 보관)
    extraction, approved_texts = 제안확인(분석결과)

    # Step 4 & 5: 제안이 있고 승인된 것이 있으면 붙이고 의사 수정
    final_free_text = free_text
    if approved_texts:
        final_free_text = 제안_free_text_추가(free_text, approved_texts)
        final_free_text = 의사_최종수정(final_free_text)
    # 제안 없으면 Steps 4, 5 건너뜀

    # Step 6: 추출 데이터 표시 → 재분석 여부 선택
    print("\n=== 테이블 저장 데이터 (최초 분석 기준) ===")
    _추출데이터_요약표시(extraction)

    재분석 = input("\n차트 수정으로 데이터가 바뀌었나요? AI로 재분석할까요? (y/n): ").strip().lower()
    if 재분석 == "y":
        print(" [재분석 중...]")
        재추출결과 = 재추출(환자id, final_free_text, 방문일)
        if 재추출결과:
            extraction = 재추출결과
            print(" [재분석 완료]")
        else:
            print(" [경고] 재분석 실패. 최초 추출 데이터 사용.")

    # 항목별 승인
    print("\n=== 항목별 저장 승인 ===")
    approved_data = _추출데이터_항목별_승인(extraction)

    # Step 7: 저장
    print("\n [저장 중...]")
    저장건수 = 분석결과_저장(환자id, 방문id, final_free_text, approved_data)
    print(f"\n 총 {저장건수}건 저장 완료.")

    return final_free_text, 저장건수


# ============================================================
# 헬퍼: 검사처방 시행완료 자동 매칭
# ============================================================
def _검사처방_시행완료_매칭(환자id, 검사시행일, 검사항목):
    """검사결과 저장 시 매칭되는 미시행 검사처방을 시행여부=1로 업데이트."""
    conn = sqlite3.connect(DB경로)
    try:
        미시행 = conn.execute(
            "SELECT 처방검사id, 검사명 FROM 검사처방 "
            "WHERE 환자id=? AND 시행여부=0 AND 유효여부=1",
            (환자id,)
        ).fetchall()
        for row in 미시행:
            처방검사id, 검사명 = row[0], row[1]
            if 검사항목 in 검사명 or 검사명 in 검사항목:
                conn.execute(
                    "UPDATE 검사처방 SET 시행여부=1 WHERE 처방검사id=?",
                    (처방검사id,)
                )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 차트 수정 함수 (기존 차트분석_저장_전체흐름()과 별개)
# ============================================================
def _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일):
    """free-text 수정 전후를 비교하여 변경사항만 추출한다. 저장하지 않음.
    Returns: dict (변경, 추가, 삭제, 활력징후_변경, 처방요약_변경) 또는 None"""

    시스템_프롬프트 = """당신은 의료 차트 데이터 비교 어시스턴트입니다.
수정 전후의 free-text를 비교하여 변경된 의료 데이터만 추출하세요.
새로운 제안이나 검토 의견은 절대 하지 마세요.
변경/추가/삭제된 데이터만 JSON으로 출력하세요.

JSON 형식:
{
  "변경": [
    {"테이블": "검사결과", "기존": {"검사항목": "HbA1c", "결과값": "9.5"}, "수정후": {"검사항목": "HbA1c", "결과값": "8.5"}, "검사시행일": "260301"}
  ],
  "추가": [
    {"테이블": "검사결과", "데이터": {"검사항목": "TG", "결과값": "150", "단위": "mg/dL", "검사시행일": "260301"}}
  ],
  "삭제": [
    {"테이블": "검사결과", "데이터": {"검사항목": "LDL", "결과값": "160", "검사시행일": "260301"}}
  ],
  "활력징후_변경": {"수축기": 140, "이완기": 88} 또는 null,
  "처방요약_변경": "변경된 처방요약" 또는 null
}
변경이 없는 항목은 빈 배열로.
활력징후_변경, 처방요약_변경은 변경 없으면 null로.
순수 JSON만 출력. 마크다운이나 설명 없이."""

    프롬프트 = f"""[방문일: {방문일}]

[수정 전 free-text]
{기존_free_text}

[수정 후 free-text]
{새_free_text}

위 두 텍스트를 비교하여 변경된 의료 데이터만 추출하세요."""

    # 익명화 처리
    기록 = 환자전체기록조회(환자id)
    if 기록:
        익명기록, 매핑 = api_익명화(기록)
        랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
        실제이름 = 매핑.get(랜덤id) if 랜덤id else None
        익명_기존 = 기존_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 기존_free_text
        익명_새 = 새_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 새_free_text
        익명_프롬프트 = 프롬프트.replace(기존_free_text, 익명_기존).replace(새_free_text, 익명_새)
    else:
        매핑 = {}
        익명_프롬프트 = 프롬프트

    # API 호출
    응답 = _익명화_api호출(시스템_프롬프트, 익명_프롬프트, 매핑)
    매핑 = None  # 매핑 메모리 해제

    if not 응답:
        return None

    변경사항 = _parse_json_response(응답)
    return 변경사항  # 파싱 실패 시 None, 성공 시 dict


def 차트_데이터만_수정(환자id, 방문id, 기존_free_text, 새_free_text, 방문일, 변경사항=None):
    """free-text 수정 시 변경된 데이터만 감지하여 테이블을 업데이트한다.
    AI 제안/검토 의견 없음. 데이터 변경분만 처리.
    변경사항이 이미 있으면 그대로 사용, 없으면 새로 추출.
    Returns: (변경사항_요약, 변경건수)"""

    if 변경사항 is None:
        변경사항 = _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일)
    if not 변경사항:
        return "변경사항 추출 실패", 0

    변경건수 = 0
    변경요약 = []
    conn = sqlite3.connect(DB경로)

    try:
        # free-text 자체 업데이트
        방문기록_일괄수정(방문id, {"free_text": 새_free_text})

        # 활력징후 변경
        vs = 변경사항.get("활력징후_변경")
        if vs:
            필드 = {k: vs[k] for k in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"] if vs.get(k) is not None}
            if 필드:
                방문기록_일괄수정(방문id, 필드)
                변경건수 += 1
                변경요약.append(f"활력징후 수정: {필드}")

        # 처방요약 변경
        if 변경사항.get("처방요약_변경"):
            방문기록_일괄수정(방문id, {"처방요약": 변경사항["처방요약_변경"]})
            변경건수 += 1
            변경요약.append("처방요약 수정")

        # 변경된 항목 처리 (기존 무효화 + 새 레코드)
        for 항목 in 변경사항.get("변경", []):
            테이블 = 항목.get("테이블", "")
            기존 = 항목.get("기존", {})
            수정후 = 항목.get("수정후", {})
            시행일 = 항목.get("검사시행일", 방문일)

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 기존.get("검사항목"), 기존.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text 수정' WHERE 검사id=?", (r[0],))
                conn.commit()
                검사결과추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사항목", 기존.get("검사항목")),
                           수정후.get("결과값", ""), 수정후.get("단위", ""), 수정후.get("참고범위", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"검사결과 수정: {기존.get('검사항목')} {기존.get('결과값')} → {수정후.get('결과값')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text 수정' WHERE 진단id=?", (r[0],))
                conn.commit()
                진단추가(환자id, 방문id, 수정후.get("진단명", 기존.get("진단명")),
                        수정후.get("상태", "활성"), 수정후.get("비고", ""), 수정후.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 수정: {기존.get('진단명')} → {수정후.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text 수정' WHERE 처방id=?", (r[0],))
                conn.commit()
                처방추가(환자id, 방문id, 수정후.get("약품명", 기존.get("약품명")),
                        수정후.get("성분명", ""), 수정후.get("용량", ""),
                        수정후.get("용법", ""), 수정후.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 수정: {기존.get('약품명')} → {수정후.get('약품명')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 기존.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text 수정' WHERE 영상id=?", (r[0],))
                conn.commit()
                영상검사추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사종류", 기존.get("검사종류")),
                           수정후.get("결과요약", ""), 수정후.get("주요수치", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 수정: {기존.get('검사종류')}")

        # 추가된 항목 처리
        for 항목 in 변경사항.get("추가", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                검사결과추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사항목"), 데이터.get("결과값", ""),
                           데이터.get("단위", ""), 데이터.get("참고범위", ""),
                           방문id=방문id)
                _검사처방_시행완료_매칭(환자id, 데이터.get("검사시행일", 방문일), 데이터.get("검사항목", ""))
                변경건수 += 1
                변경요약.append(f"검사결과 추가: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                영상검사추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사종류"), 데이터.get("결과요약", ""),
                           데이터.get("주요수치", ""), 방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 추가: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                진단추가(환자id, 방문id, 데이터.get("진단명"), 데이터.get("상태", "활성"),
                        데이터.get("비고", ""), 데이터.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 추가: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                처방추가(환자id, 방문id, 데이터.get("약품명"), 데이터.get("성분명", ""),
                        데이터.get("용량", ""), 데이터.get("용법", ""), 데이터.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 추가: {데이터.get('약품명')}")

            elif 테이블 == "추적계획":
                추적계획추가(환자id, 방문id, 데이터.get("예정일", ""), 데이터.get("내용", ""))
                변경건수 += 1
                변경요약.append(f"추적계획 추가: {데이터.get('내용')}")

            elif 테이블 == "검사처방":
                검사처방추가(환자id, 방문id, 데이터.get("검사명", ""), 데이터.get("처방일", ""))
                변경건수 += 1
                변경요약.append(f"검사처방 추가: {데이터.get('검사명')}")

        # 삭제된 항목 처리 (무효화)
        for 항목 in 변경사항.get("삭제", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 데이터.get("검사항목"), 데이터.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 검사id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"검사결과 삭제: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 데이터.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 영상id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"영상검사 삭제: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 진단id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"진단 삭제: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 처방id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"처방 삭제: {데이터.get('약품명')}")

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"업데이트 오류: {e}", 0
    finally:
        conn.close()

    요약텍스트 = "\n".join(변경요약) if 변경요약 else "변경사항 없음"
    return 요약텍스트, 변경건수


def 차트_재분석_저장(환자id, 방문id, 새_free_text, 방문일):
    """free-text 수정 후 AI 재분석. 기존 데이터 무효화 후 재추출/저장.
    Streamlit 호환 (input() 사용 안 함).
    Returns: (extraction_data, 저장건수) or (None, 0)"""

    # 1. 이 방문에 연결된 기존 데이터 전부 무효화
    conn = sqlite3.connect(DB경로)
    try:
        for 테이블 in ["진단", "추적계획", "처방", "검사처방"]:
            conn.execute(
                f"UPDATE {테이블} SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
                (방문id,)
            )
        conn.execute(
            "UPDATE 검사결과 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.execute(
            "UPDATE 영상검사 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.commit()
    finally:
        conn.close()

    # 2. free-text 업데이트
    방문기록_일괄수정(방문id, {"free_text": 새_free_text})

    # 3. AI 재분석 (차트분석 함수 직접 호출, input() 없음)
    분석결과 = 차트분석(환자id, 새_free_text, 방문일)
    if not 분석결과:
        return None, 0

    extraction = 분석결과.get("extraction", {})
    if not extraction:
        return None, 0

    # 4. 전체 항목 자동 승인하여 저장
    approved_data = {}
    approved_data["vitals"] = extraction.get("vitals", {})
    approved_data["lifestyle"] = extraction.get("lifestyle", {})
    approved_data["diagnoses"] = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    approved_data["lab_results"] = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    approved_data["imaging"] = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    approved_data["prescriptions"] = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    approved_data["tracking"] = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    approved_data["test_orders"] = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    approved_data["prescription_summary"] = extraction.get("prescription_summary", "")
    approved_data["patient_info"] = {k: v for k, v in extraction.get("patient_info", {}).items() if v and v.get("변경유형")}

    저장건수 = 분석결과_저장(환자id, 방문id, 새_free_text, approved_data)
    방문기록_일괄수정(방문id, {"분석완료": 1})

    return extraction, 저장건수
def _parse_json_response(text):
    """AI 응답에서 JSON 파싱 (마크다운 코드블록 제거 포함)"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f" [오류] AI 응답을 JSON으로 파싱할 수 없습니다.")
        print(f" 원본 응답:\n{text[:500]}")
        return None



def _익명화_api호출(system, 프롬프트, 매핑, max_tokens=4096):
    """익명화된 프롬프트로 API 호출 후 복원. Returns: 응답텍스트 or None"""
    응답 = api_재시도(lambda: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": 프롬프트}]
    ))
    if not 응답:
        return None
    텍스트 = api_복원(응답.content[0].text.strip(), 매핑)
    return 텍스트


# ============================================================
# 공공 DB 조회 헬퍼 (차트분석 내부용)
# ============================================================

# 흔한 내과 진단명 → 영문 변환 테이블
_진단명_영문 = {
    "고혈압": "hypertension",
    "고지혈증": "dyslipidemia",
    "당뇨": "diabetes mellitus",
    "당뇨전단계": "prediabetes",
    "갑상선기능저하증": "hypothyroidism",
    "갑상선기능항진증": "hyperthyroidism",
    "통풍": "gout",
    "골다공증": "osteoporosis",
    "만성콩팥병": "chronic kidney disease",
    "심방세동": "atrial fibrillation",
    "심부전": "heart failure",
    "관상동맥질환": "coronary artery disease",
    "뇌졸중": "stroke",
    "빈혈": "anemia",
    "지방간": "fatty liver",
}


def _free_text에서_약품명_추출(free_text):
    """free-text에서 약품명 패턴 간단 추출 (영문 소문자 + 숫자mg 조합).
    완벽하지 않아도 됨 — AI가 나중에 정확히 추출함."""
    import re
    패턴 = r'\b[a-z]{4,}(?:\s*\d+\s*mg)?\b'
    후보 = re.findall(패턴, free_text.lower())
    제외목록 = {"with", "that", "this", "from", "have", "been", "will", "also",
               "than", "more", "less", "after", "before", "normal", "blood",
               "free", "text", "note", "plan", "done", "left", "right"}
    seen = set()
    약품목록 = []
    for w in 후보:
        w = w.strip()
        if w not in seen and w not in 제외목록:
            seen.add(w)
            약품목록.append(w)
        if len(약품목록) >= 5:
            break
    return 약품목록


def _free_text에서_pubmed_검색어_추출(free_text):
    """free-text에서 진단명을 찾아 영문 검색어 생성."""
    for 한글, 영문 in _진단명_영문.items():
        if 한글 in free_text:
            return f"{영문} treatment guideline"
    return None


def _공공DB_조회(free_text):
    """처방 안전성(DUR/e약은요/급여) + PubMed 조회.
    Returns: (공공DB결과_문자열, 조회성공여부)"""
    try:
        약품목록 = _free_text에서_약품명_추출(free_text)
        검색어 = _free_text에서_pubmed_검색어_추출(free_text)

        안전성결과 = 처방_안전성_조회(약품목록) if 약품목록 else {}
        pubmed결과 = pubmed_검색(검색어) if 검색어 else []

        dur_정보 = {약품: v["dur"] for 약품, v in 안전성결과.items()}
        약품정보 = {약품: v["약품정보"] for 약품, v in 안전성결과.items()}
        급여정보 = {약품: v["급여정보"] for 약품, v in 안전성결과.items()}

        조회결과 = (
            "[공공 DB 조회 결과 — 참고하여 검토 의견에 반영하세요]\n\n"
            "[DUR 정보]\n" + json.dumps(dur_정보, ensure_ascii=False, indent=2) + "\n\n"
            "[약품 정보 (e약은요)]\n" + json.dumps(약품정보, ensure_ascii=False, indent=2) + "\n\n"
            "[급여 정보]\n" + json.dumps(급여정보, ensure_ascii=False, indent=2) + "\n\n"
            "[PubMed 검색 결과]\n" + json.dumps(pubmed결과, ensure_ascii=False, indent=2) + "\n\n"
            "위 정보를 검토 의견(💡), 법적 확인(⚖), 설명의무에 활용하세요.\n"
            "DUR에서 병용금기가 발견되면 반드시 ⚖ 법적 확인사항에 포함하세요.\n"
            "PubMed 논문은 관련 있는 것만 검토 의견에 포함하세요.\n"
            "급여 정보가 있으면 처방 관련 제안에 급여 여부를 명시하세요."
        )

        return 조회결과, True

    except Exception as e:
        print(f"  ⚠ 공공 DB 조회 실패: {e}")
        return "[공공 DB 조회 결과 — 조회 실패 또는 해당 정보 없음. 내부 지식으로 판단하세요.]", False


# ============================================================
# Step 2: 1번째 API — 분석 + 추출 + 제안
# ============================================================
def 차트분석(환자id, free_text, 방문일=None):
    """AI 분석: 데이터 추출 + 검토의견 + 법적확인 + 설명의무 전부 수행.
    Returns: dict(extraction, suggestions, legal, informed_consent) or None"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    나이 = 나이계산(기록["환자"]["생년월일"])
    if 나이 is not None:
        기록["환자"]["나이"] = f"{나이}세"

    # 공공 DB 조회 (AI API 호출 전)
    공공DB_문자열, 조회성공 = _공공DB_조회(free_text)
    if not 조회성공:
        print("  ⚠ 공공 DB 조회 실패. AI 내부 지식으로 검토합니다.")

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_free_text = free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else free_text

    패턴요약 = 의사패턴_요약생성()
    패턴요약_섹션 = f"\n[의사 진료 패턴 — 참고하여 맥락에 맞는 검토 의견 제시에 활용]\n{패턴요약}\n" if 패턴요약 else ""

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[오늘 free-text]
{익명_free_text}

{공공DB_문자열}{패턴요약_섹션}
위 free-text를 분석하여 기존 데이터와 비교한 뒤, 지정된 JSON 형식으로 출력하세요."""

    응답텍스트 = _익명화_api호출(SYSTEM_PROMPT, 프롬프트, 매핑)
    매핑 = None
    return _parse_json_response(응답텍스트)


# ============================================================
# Step 3: 제안 표시 + 승인 (extraction은 메모리 보관)
# ============================================================
def 제안확인(분석결과):
    """💡⚖설명의무 제안만 표시. extraction은 그대로 반환.
    Returns: (extraction, approved_texts: list[str])
             approved_texts가 비면 제안 없음 또는 전부 거부."""
    extraction = 분석결과.get("extraction", {})
    suggestions = 분석결과.get("suggestions", [])
    legal = 분석결과.get("legal", [])
    informed_consent = 분석결과.get("informed_consent", {})

    approved_texts = []
    has_any = bool(suggestions or legal or informed_consent.get("chart_text"))

    if not has_any:
        print("\n [AI 검토] 검토 의견 없음")
        return extraction, approved_texts

    print("\n=== AI 검토 결과 ===")

    # ── AI 검토 의견 (💡) ──
    if suggestions:
        print("\n── AI 검토 의견 ──")
        for i, s in enumerate(suggestions, 1):
            print(f"  💡 {i}. {s.get('content', '')} ({s.get('reason', '')})")
            chart_text = s.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 법적 확인사항 (⚖) ──
    if legal:
        print("\n── 법적 확인사항 ──")
        for i, l in enumerate(legal, 1):
            print(f"  ⚖ {i}. {l.get('content', '')} ({l.get('reason', '')})")
            chart_text = l.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 설명의무 기록 ──
    ic_text = informed_consent.get("chart_text", "")
    if ic_text:
        drugs = ", ".join(informed_consent.get("drugs", []))
        se = ", ".join(informed_consent.get("side_effects", []))
        print(f"\n── 설명의무 기록 ──")
        if drugs:
            print(f"   약물: {drugs}  |  부작용: {se}")
        print(f"   제안: \"{ic_text}\"")
        if input("   → 차트에 반영할까요? (y/n): ").strip().lower() == "y":
            approved_texts.append(ic_text)

    return extraction, approved_texts


# ============================================================
# Step 4: 승인된 chart_text를 free-text 아래에 추가 (API 없음)
# ============================================================
def 제안_free_text_추가(free_text, approved_texts):
    """승인된 chart_text들을 free_text 아래에 덧붙인다."""
    if not approved_texts:
        return free_text
    추가문구 = "\n".join(approved_texts)
    구분선 = "\n---\n" if free_text.strip() else ""
    return free_text + 구분선 + 추가문구


# ============================================================
# Step 5: 의사 직접 수정
# ============================================================
def 의사_최종수정(free_text):
    """차트를 의사에게 보여주고 직접 수정하게 한다.
    새 내용 입력 시 교체. 빈 줄 입력 시 원본 그대로 확정."""
    print("\n=== 최종 차트 확인 ===")
    print("─" * 50)
    print(free_text)
    print("─" * 50)
    print("수정이 필요하면 전체 내용을 다시 입력하세요.")
    print("(수정 없이 확정하려면 바로 Enter)")

    줄들 = []
    while True:
        줄 = input()
        if 줄 == "":
            break
        줄들.append(줄)

    return "\n".join(줄들) if 줄들 else free_text


# ============================================================
# Step 6 내부: 추출 데이터 요약 표시
# ============================================================
def _추출데이터_요약표시(extraction):
    """추출된 데이터를 한눈에 보기 출력"""
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"  [활력징후] {bp}{hr}{ht}{wt}{bmi}")

    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"  [생활습관] {', '.join(항목들)}")

    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"  [진단] {목록}")

    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"  [검사결과] {목록}")

    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"  [영상검사] {목록}")

    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"  [처방] {목록}")

    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"  [추적계획] {목록}")

    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"  [검사처방] {목록}")

    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"  [처방요약] {ps}")

    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if 변경 and 변경.get("변경유형") and 변경.get("새값"):
            print(f"  [환자정보-{항목}] ({변경['변경유형']}) {변경.get('새값', '')}")


# ============================================================
# Step 6 내부: 항목별 y/n 승인
# ============================================================
def _추출데이터_항목별_승인(extraction):
    """항목별 카테고리 단위로 y/n 질문. Returns: approved_data dict"""
    approved = {}

    # 활력징후
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기", "심박수", "키", "몸무게"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"\n  [활력징후] {bp}{hr}{ht}{wt}{bmi}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["vitals"] = vitals

    # 생활습관
    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"\n  [생활습관] {', '.join(항목들)}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lifestyle"] = lifestyle

    # 진단
    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"\n  [진단] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["diagnoses"] = diagnoses

    # 검사결과
    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"\n  [검사결과] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lab_results"] = labs

    # 영상검사
    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"\n  [영상검사] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["imaging"] = imaging

    # 처방
    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"\n  [처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescriptions"] = prescriptions

    # 추적계획
    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"\n  [추적계획] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["tracking"] = tracking

    # 검사처방
    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"\n  [검사처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["test_orders"] = test_orders

    # 처방요약
    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"\n  [처방요약] {ps}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescription_summary"] = ps

    # 환자정보
    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if not 변경 or not 변경.get("변경유형"):
            continue
        유형표시 = {"add": "추가", "modify": "수정", "remove": "삭제"}.get(변경.get("변경유형", ""), "변경")
        print(f"\n  [환자정보-{항목}] ({유형표시}) {변경.get('기존값', '')} → {변경.get('새값', '')}")
        if 변경.get("근거"):
            print(f"     근거: {변경['근거']}")
        if input("  → 업데이트할까요? (y/n): ").strip().lower() == "y":
            if "patient_info" not in approved:
                approved["patient_info"] = {}
            approved["patient_info"][항목] = 변경

    return approved


# ============================================================
# Step 6: 2번째 API — 재추출 (선택적)
# ============================================================
def 재추출(환자id, final_free_text, 방문일):
    """최종 확정 free-text로 데이터만 재추출 (2번째 API).
    Returns: extraction dict or None"""
    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_text = final_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else final_free_text

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[최종 확정 차트]
{익명_text}

위 최종 차트에서 데이터를 추출하세요."""

    응답텍스트 = _익명화_api호출(REEXTRACT_SYSTEM, 프롬프트, 매핑)
    매핑 = None
    결과 = _parse_json_response(응답텍스트)
    if 결과:
        return 결과.get("extraction", 결과)
    return None


# ============================================================
# Step 7: 테이블 저장
# ============================================================
def 분석결과_저장(환자id, 방문id, final_free_text, approved_data):
    """승인된 항목을 유형별로 테이블에 저장. Returns: 저장건수"""
    저장건수 = 0

    # --- 방문 테이블 일괄 업데이트 (free_text, 활력징후, 생활습관, 처방요약) ---
    # 방문기록수정()을 여러 번 호출하면 매번 새 레코드가 생성되므로
    # 한 번의 UPDATE로 처리하여 불필요한 레코드 복사 방지
    방문_업데이트 = {}
    vitals = approved_data.get("vitals", {})
    lifestyle = approved_data.get("lifestyle", {})
    ps = approved_data.get("prescription_summary", "")

    if final_free_text:
        방문_업데이트["free_text"] = final_free_text
    for 필드 in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"]:
        if vitals.get(필드) is not None:
            방문_업데이트[필드] = vitals[필드]
    for 필드 in ["흡연", "음주", "운동"]:
        if lifestyle.get(필드):
            방문_업데이트[필드] = lifestyle[필드]
    if ps:
        방문_업데이트["처방요약"] = ps

    if 방문_업데이트:
        방문기록_일괄수정(방문id, 방문_업데이트)
        저장건수 += 1
        if final_free_text:
            print(f"  → free_text 저장 완료")
        if vitals:
            bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
            print(f"  → 활력징후 저장: {bp}")
        if lifestyle:
            print(f"  → 생활습관 저장 완료")
        if ps:
            print(f"  → 처방요약 저장: {ps[:40]}{'...' if len(ps) > 40 else ''}")

    # --- 진단 ---
    for d in approved_data.get("diagnoses", []):
        진단추가(환자id, 방문id, d["진단명"], d.get("상태", "활성"), d.get("비고", ""), d.get("표준코드", None))
        저장건수 += 1
        print(f"  → 진단 저장: {d['진단명']} ({d.get('상태', '')})")

    # --- 검사결과 ---
    for k in approved_data.get("lab_results", []):
        검사결과추가(환자id, k.get("검사시행일", ""), k["검사항목"], k.get("결과값", ""),
                   k.get("단위", ""), k.get("참고범위", ""), 방문id=방문id)
        _검사처방_시행완료_매칭(환자id, k.get("검사시행일", ""), k["검사항목"])
        저장건수 += 1
        print(f"  → 검사결과 저장: {k['검사항목']} {k.get('결과값', '')}")

    # --- 영상검사 ---
    for e in approved_data.get("imaging", []):
        영상검사추가(환자id, e.get("검사시행일", ""), e["검사종류"], e.get("결과요약", ""),
                   e.get("주요수치", ""), 방문id=방문id)
        저장건수 += 1
        print(f"  → 영상검사 저장: {e['검사종류']}")

    # --- 처방 ---
    for p in approved_data.get("prescriptions", []):
        처방추가(환자id, 방문id, p.get("약품명", ""), p.get("성분명", ""), p.get("용량", ""), p.get("용법", ""), p.get("일수", 0))
        저장건수 += 1
        print(f"  → 처방 저장: {p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')}")

    # --- 추적계획 ---
    for t in approved_data.get("tracking", []):
        추적계획추가(환자id, 방문id, t.get("예정일", ""), t.get("내용", ""))
        저장건수 += 1
        print(f"  → 추적계획 저장: {t.get('내용', '')}")

    # --- 검사처방 ---
    # 처방일 fallback: AI가 처방일을 비워둔 경우 방문일로 대체
    _방문일_fallback = ""
    if approved_data.get("test_orders"):
        _conn = sqlite3.connect(DB경로)
        try:
            row = _conn.execute(
                "SELECT 방문일 FROM 방문 WHERE 방문id=? AND 유효여부=1", (방문id,)
            ).fetchone()
            if row:
                _방문일_fallback = row[0]
        finally:
            _conn.close()

    for o in approved_data.get("test_orders", []):
        처방일 = o.get("처방일", "") or _방문일_fallback
        검사처방추가(환자id, 방문id, o.get("검사명", ""), 처방일)
        저장건수 += 1
        print(f"  → 검사처방 저장: {o.get('검사명', '')} (예정: {처방일})")

    # --- 환자정보 업데이트 ---
    기존환자 = 환자전체기록조회(환자id)
    for 항목명, 변경 in approved_data.get("patient_info", {}).items():
        변경유형 = 변경.get("변경유형", "")
        새값 = 변경.get("새값", "")
        기존값 = 기존환자["환자"].get(항목명, "") if 기존환자 else ""

        if 변경유형 == "add":
            최종값 = (기존값 + ", " + 새값).strip(", ") if 기존값 else 새값
        elif 변경유형 == "modify":
            최종값 = 새값
        elif 변경유형 == "remove":
            최종값 = ""
        else:
            continue

        환자정보수정(환자id, 항목명, 최종값)
        저장건수 += 1
        print(f"  → {항목명} 업데이트: {최종값}")

    return 저장건수


# ============================================================
# 전체 흐름 orchestrator (main_system.py에서 호출)
# ============================================================
def 차트분석_저장_전체흐름(환자id, 방문id, free_text, 방문일=None):
    """Steps 2~7 전체 실행.
    방문id는 호출 전에 미리 생성되어 있어야 함.
    Returns: (final_free_text, 저장건수) or (None, 0) on failure"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    # Step 2: AI 분석
    print("\n [AI 분석 중...]")
    분석결과 = 차트분석(환자id, free_text, 방문일)
    if not 분석결과:
        print(" [오류] AI 분석 실패")
        return None, 0

    # Step 3: 제안 확인 (extraction 메모리 보관)
    extraction, approved_texts = 제안확인(분석결과)

    # Step 4 & 5: 제안이 있고 승인된 것이 있으면 붙이고 의사 수정
    final_free_text = free_text
    if approved_texts:
        final_free_text = 제안_free_text_추가(free_text, approved_texts)
        final_free_text = 의사_최종수정(final_free_text)
    # 제안 없으면 Steps 4, 5 건너뜀

    # Step 6: 추출 데이터 표시 → 재분석 여부 선택
    print("\n=== 테이블 저장 데이터 (최초 분석 기준) ===")
    _추출데이터_요약표시(extraction)

    재분석 = input("\n차트 수정으로 데이터가 바뀌었나요? AI로 재분석할까요? (y/n): ").strip().lower()
    if 재분석 == "y":
        print(" [재분석 중...]")
        재추출결과 = 재추출(환자id, final_free_text, 방문일)
        if 재추출결과:
            extraction = 재추출결과
            print(" [재분석 완료]")
        else:
            print(" [경고] 재분석 실패. 최초 추출 데이터 사용.")

    # 항목별 승인
    print("\n=== 항목별 저장 승인 ===")
    approved_data = _추출데이터_항목별_승인(extraction)

    # Step 7: 저장
    print("\n [저장 중...]")
    저장건수 = 분석결과_저장(환자id, 방문id, final_free_text, approved_data)
    print(f"\n 총 {저장건수}건 저장 완료.")

    return final_free_text, 저장건수


# ============================================================
# 헬퍼: 검사처방 시행완료 자동 매칭
# ============================================================
def _검사처방_시행완료_매칭(환자id, 검사시행일, 검사항목):
    """검사결과 저장 시 매칭되는 미시행 검사처방을 시행여부=1로 업데이트."""
    conn = sqlite3.connect(DB경로)
    try:
        미시행 = conn.execute(
            "SELECT 처방검사id, 검사명 FROM 검사처방 "
            "WHERE 환자id=? AND 시행여부=0 AND 유효여부=1",
            (환자id,)
        ).fetchall()
        for row in 미시행:
            처방검사id, 검사명 = row[0], row[1]
            if 검사항목 in 검사명 or 검사명 in 검사항목:
                conn.execute(
                    "UPDATE 검사처방 SET 시행여부=1 WHERE 처방검사id=?",
                    (처방검사id,)
                )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 차트 수정 함수 (기존 차트분석_저장_전체흐름()과 별개)
# ============================================================
def _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일):
    """free-text 수정 전후를 비교하여 변경사항만 추출한다. 저장하지 않음.
    Returns: dict (변경, 추가, 삭제, 활력징후_변경, 처방요약_변경) 또는 None"""

    시스템_프롬프트 = """당신은 의료 차트 데이터 비교 어시스턴트입니다.
수정 전후의 free-text를 비교하여 변경된 의료 데이터만 추출하세요.
새로운 제안이나 검토 의견은 절대 하지 마세요.
변경/추가/삭제된 데이터만 JSON으로 출력하세요.

JSON 형식:
{
  "변경": [
    {"테이블": "검사결과", "기존": {"검사항목": "HbA1c", "결과값": "9.5"}, "수정후": {"검사항목": "HbA1c", "결과값": "8.5"}, "검사시행일": "260301"}
  ],
  "추가": [
    {"테이블": "검사결과", "데이터": {"검사항목": "TG", "결과값": "150", "단위": "mg/dL", "검사시행일": "260301"}}
  ],
  "삭제": [
    {"테이블": "검사결과", "데이터": {"검사항목": "LDL", "결과값": "160", "검사시행일": "260301"}}
  ],
  "활력징후_변경": {"수축기": 140, "이완기": 88} 또는 null,
  "처방요약_변경": "변경된 처방요약" 또는 null
}
변경이 없는 항목은 빈 배열로.
활력징후_변경, 처방요약_변경은 변경 없으면 null로.
순수 JSON만 출력. 마크다운이나 설명 없이."""

    프롬프트 = f"""[방문일: {방문일}]

[수정 전 free-text]
{기존_free_text}

[수정 후 free-text]
{새_free_text}

위 두 텍스트를 비교하여 변경된 의료 데이터만 추출하세요."""

    # 익명화 처리
    기록 = 환자전체기록조회(환자id)
    if 기록:
        익명기록, 매핑 = api_익명화(기록)
        랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
        실제이름 = 매핑.get(랜덤id) if 랜덤id else None
        익명_기존 = 기존_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 기존_free_text
        익명_새 = 새_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 새_free_text
        익명_프롬프트 = 프롬프트.replace(기존_free_text, 익명_기존).replace(새_free_text, 익명_새)
    else:
        매핑 = {}
        익명_프롬프트 = 프롬프트

    # API 호출
    응답 = _익명화_api호출(시스템_프롬프트, 익명_프롬프트, 매핑)
    매핑 = None  # 매핑 메모리 해제

    if not 응답:
        return None

    변경사항 = _parse_json_response(응답)
    return 변경사항  # 파싱 실패 시 None, 성공 시 dict


def 차트_데이터만_수정(환자id, 방문id, 기존_free_text, 새_free_text, 방문일, 변경사항=None):
    """free-text 수정 시 변경된 데이터만 감지하여 테이블을 업데이트한다.
    AI 제안/검토 의견 없음. 데이터 변경분만 처리.
    변경사항이 이미 있으면 그대로 사용, 없으면 새로 추출.
    Returns: (변경사항_요약, 변경건수)"""

    if 변경사항 is None:
        변경사항 = _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일)
    if not 변경사항:
        return "변경사항 추출 실패", 0

    변경건수 = 0
    변경요약 = []
    conn = sqlite3.connect(DB경로)

    try:
        # free-text 자체 업데이트
        방문기록_일괄수정(방문id, {"free_text": 새_free_text})

        # 활력징후 변경
        vs = 변경사항.get("활력징후_변경")
        if vs:
            필드 = {k: vs[k] for k in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"] if vs.get(k) is not None}
            if 필드:
                방문기록_일괄수정(방문id, 필드)
                변경건수 += 1
                변경요약.append(f"활력징후 수정: {필드}")

        # 처방요약 변경
        if 변경사항.get("처방요약_변경"):
            방문기록_일괄수정(방문id, {"처방요약": 변경사항["처방요약_변경"]})
            변경건수 += 1
            변경요약.append("처방요약 수정")

        # 변경된 항목 처리 (기존 무효화 + 새 레코드)
        for 항목 in 변경사항.get("변경", []):
            테이블 = 항목.get("테이블", "")
            기존 = 항목.get("기존", {})
            수정후 = 항목.get("수정후", {})
            시행일 = 항목.get("검사시행일", 방문일)

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 기존.get("검사항목"), 기존.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text 수정' WHERE 검사id=?", (r[0],))
                conn.commit()
                검사결과추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사항목", 기존.get("검사항목")),
                           수정후.get("결과값", ""), 수정후.get("단위", ""), 수정후.get("참고범위", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"검사결과 수정: {기존.get('검사항목')} {기존.get('결과값')} → {수정후.get('결과값')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text 수정' WHERE 진단id=?", (r[0],))
                conn.commit()
                진단추가(환자id, 방문id, 수정후.get("진단명", 기존.get("진단명")),
                        수정후.get("상태", "활성"), 수정후.get("비고", ""), 수정후.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 수정: {기존.get('진단명')} → {수정후.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text 수정' WHERE 처방id=?", (r[0],))
                conn.commit()
                처방추가(환자id, 방문id, 수정후.get("약품명", 기존.get("약품명")),
                        수정후.get("성분명", ""), 수정후.get("용량", ""),
                        수정후.get("용법", ""), 수정후.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 수정: {기존.get('약품명')} → {수정후.get('약품명')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 기존.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text 수정' WHERE 영상id=?", (r[0],))
                conn.commit()
                영상검사추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사종류", 기존.get("검사종류")),
                           수정후.get("결과요약", ""), 수정후.get("주요수치", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 수정: {기존.get('검사종류')}")

        # 추가된 항목 처리
        for 항목 in 변경사항.get("추가", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                검사결과추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사항목"), 데이터.get("결과값", ""),
                           데이터.get("단위", ""), 데이터.get("참고범위", ""),
                           방문id=방문id)
                _검사처방_시행완료_매칭(환자id, 데이터.get("검사시행일", 방문일), 데이터.get("검사항목", ""))
                변경건수 += 1
                변경요약.append(f"검사결과 추가: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                영상검사추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사종류"), 데이터.get("결과요약", ""),
                           데이터.get("주요수치", ""), 방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 추가: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                진단추가(환자id, 방문id, 데이터.get("진단명"), 데이터.get("상태", "활성"),
                        데이터.get("비고", ""), 데이터.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 추가: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                처방추가(환자id, 방문id, 데이터.get("약품명"), 데이터.get("성분명", ""),
                        데이터.get("용량", ""), 데이터.get("용법", ""), 데이터.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 추가: {데이터.get('약품명')}")

            elif 테이블 == "추적계획":
                추적계획추가(환자id, 방문id, 데이터.get("예정일", ""), 데이터.get("내용", ""))
                변경건수 += 1
                변경요약.append(f"추적계획 추가: {데이터.get('내용')}")

            elif 테이블 == "검사처방":
                검사처방추가(환자id, 방문id, 데이터.get("검사명", ""), 데이터.get("처방일", ""))
                변경건수 += 1
                변경요약.append(f"검사처방 추가: {데이터.get('검사명')}")

        # 삭제된 항목 처리 (무효화)
        for 항목 in 변경사항.get("삭제", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 데이터.get("검사항목"), 데이터.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 검사id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"검사결과 삭제: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 데이터.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 영상id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"영상검사 삭제: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 진단id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"진단 삭제: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 처방id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"처방 삭제: {데이터.get('약품명')}")

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"업데이트 오류: {e}", 0
    finally:
        conn.close()

    요약텍스트 = "\n".join(변경요약) if 변경요약 else "변경사항 없음"
    return 요약텍스트, 변경건수


def 차트_재분석_저장(환자id, 방문id, 새_free_text, 방문일):
    """free-text 수정 후 AI 재분석. 기존 데이터 무효화 후 재추출/저장.
    Streamlit 호환 (input() 사용 안 함).
    Returns: (extraction_data, 저장건수) or (None, 0)"""

    # 1. 이 방문에 연결된 기존 데이터 전부 무효화
    conn = sqlite3.connect(DB경로)
    try:
        for 테이블 in ["진단", "추적계획", "처방", "검사처방"]:
            conn.execute(
                f"UPDATE {테이블} SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
                (방문id,)
            )
        conn.execute(
            "UPDATE 검사결과 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.execute(
            "UPDATE 영상검사 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.commit()
    finally:
        conn.close()

    # 2. free-text 업데이트
    방문기록_일괄수정(방문id, {"free_text": 새_free_text})

    # 3. AI 재분석 (차트분석 함수 직접 호출, input() 없음)
    분석결과 = 차트분석(환자id, 새_free_text, 방문일)
    if not 분석결과:
        return None, 0

    extraction = 분석결과.get("extraction", {})
    if not extraction:
        return None, 0

    # 4. 전체 항목 자동 승인하여 저장
    approved_data = {}
    approved_data["vitals"] = extraction.get("vitals", {})
    approved_data["lifestyle"] = extraction.get("lifestyle", {})
    approved_data["diagnoses"] = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    approved_data["lab_results"] = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    approved_data["imaging"] = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    approved_data["prescriptions"] = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    approved_data["tracking"] = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    approved_data["test_orders"] = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    approved_data["prescription_summary"] = extraction.get("prescription_summary", "")
    approved_data["patient_info"] = {k: v for k, v in extraction.get("patient_info", {}).items() if v and v.get("변경유형")}

    저장건수 = 분석결과_저장(환자id, 방문id, 새_free_text, approved_data)
    방문기록_일괄수정(방문id, {"분석완료": 1})

    return extraction, 저장건수
def _parse_json_response(text):
    """AI 응답에서 JSON 파싱 (마크다운 코드블록 제거 포함)"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f" [오류] AI 응답을 JSON으로 파싱할 수 없습니다.")
        print(f" 원본 응답:\n{text[:500]}")
        return None



def _익명화_api호출(system, 프롬프트, 매핑, max_tokens=4096):
    """익명화된 프롬프트로 API 호출 후 복원. Returns: 응답텍스트 or None"""
    응답 = api_재시도(lambda: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": 프롬프트}]
    ))
    if not 응답:
        return None
    텍스트 = api_복원(응답.content[0].text.strip(), 매핑)
    return 텍스트


# ============================================================
# 공공 DB 조회 헬퍼 (차트분석 내부용)
# ============================================================

# 흔한 내과 진단명 → 영문 변환 테이블
_진단명_영문 = {
    "고혈압": "hypertension",
    "고지혈증": "dyslipidemia",
    "당뇨": "diabetes mellitus",
    "당뇨전단계": "prediabetes",
    "갑상선기능저하증": "hypothyroidism",
    "갑상선기능항진증": "hyperthyroidism",
    "통풍": "gout",
    "골다공증": "osteoporosis",
    "만성콩팥병": "chronic kidney disease",
    "심방세동": "atrial fibrillation",
    "심부전": "heart failure",
    "관상동맥질환": "coronary artery disease",
    "뇌졸중": "stroke",
    "빈혈": "anemia",
    "지방간": "fatty liver",
}


def _free_text에서_약품명_추출(free_text):
    """free-text에서 약품명 패턴 간단 추출 (영문 소문자 + 숫자mg 조합).
    완벽하지 않아도 됨 — AI가 나중에 정확히 추출함."""
    import re
    패턴 = r'\b[a-z]{4,}(?:\s*\d+\s*mg)?\b'
    후보 = re.findall(패턴, free_text.lower())
    제외목록 = {"with", "that", "this", "from", "have", "been", "will", "also",
               "than", "more", "less", "after", "before", "normal", "blood",
               "free", "text", "note", "plan", "done", "left", "right"}
    seen = set()
    약품목록 = []
    for w in 후보:
        w = w.strip()
        if w not in seen and w not in 제외목록:
            seen.add(w)
            약품목록.append(w)
        if len(약품목록) >= 5:
            break
    return 약품목록


def _free_text에서_pubmed_검색어_추출(free_text):
    """free-text에서 진단명을 찾아 영문 검색어 생성."""
    for 한글, 영문 in _진단명_영문.items():
        if 한글 in free_text:
            return f"{영문} treatment guideline"
    return None


def _공공DB_조회(free_text):
    """처방 안전성(DUR/e약은요/급여) + PubMed 조회.
    Returns: (공공DB결과_문자열, 조회성공여부)"""
    try:
        약품목록 = _free_text에서_약품명_추출(free_text)
        검색어 = _free_text에서_pubmed_검색어_추출(free_text)

        안전성결과 = 처방_안전성_조회(약품목록) if 약품목록 else {}
        pubmed결과 = pubmed_검색(검색어) if 검색어 else []

        dur_정보 = {약품: v["dur"] for 약품, v in 안전성결과.items()}
        약품정보 = {약품: v["약품정보"] for 약품, v in 안전성결과.items()}
        급여정보 = {약품: v["급여정보"] for 약품, v in 안전성결과.items()}

        조회결과 = (
            "[공공 DB 조회 결과 — 참고하여 검토 의견에 반영하세요]\n\n"
            "[DUR 정보]\n" + json.dumps(dur_정보, ensure_ascii=False, indent=2) + "\n\n"
            "[약품 정보 (e약은요)]\n" + json.dumps(약품정보, ensure_ascii=False, indent=2) + "\n\n"
            "[급여 정보]\n" + json.dumps(급여정보, ensure_ascii=False, indent=2) + "\n\n"
            "[PubMed 검색 결과]\n" + json.dumps(pubmed결과, ensure_ascii=False, indent=2) + "\n\n"
            "위 정보를 검토 의견(💡), 법적 확인(⚖), 설명의무에 활용하세요.\n"
            "DUR에서 병용금기가 발견되면 반드시 ⚖ 법적 확인사항에 포함하세요.\n"
            "PubMed 논문은 관련 있는 것만 검토 의견에 포함하세요.\n"
            "급여 정보가 있으면 처방 관련 제안에 급여 여부를 명시하세요."
        )

        return 조회결과, True

    except Exception as e:
        print(f"  ⚠ 공공 DB 조회 실패: {e}")
        return "[공공 DB 조회 결과 — 조회 실패 또는 해당 정보 없음. 내부 지식으로 판단하세요.]", False


# ============================================================
# Step 2: 1번째 API — 분석 + 추출 + 제안
# ============================================================
def 차트분석(환자id, free_text, 방문일=None):
    """AI 분석: 데이터 추출 + 검토의견 + 법적확인 + 설명의무 전부 수행.
    Returns: dict(extraction, suggestions, legal, informed_consent) or None"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    나이 = 나이계산(기록["환자"]["생년월일"])
    if 나이 is not None:
        기록["환자"]["나이"] = f"{나이}세"

    # 공공 DB 조회 (AI API 호출 전)
    공공DB_문자열, 조회성공 = _공공DB_조회(free_text)
    if not 조회성공:
        print("  ⚠ 공공 DB 조회 실패. AI 내부 지식으로 검토합니다.")

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_free_text = free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else free_text

    패턴요약 = 의사패턴_요약생성()
    패턴요약_섹션 = f"\n[의사 진료 패턴 — 참고하여 맥락에 맞는 검토 의견 제시에 활용]\n{패턴요약}\n" if 패턴요약 else ""

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[오늘 free-text]
{익명_free_text}

{공공DB_문자열}{패턴요약_섹션}
위 free-text를 분석하여 기존 데이터와 비교한 뒤, 지정된 JSON 형식으로 출력하세요."""

    응답텍스트 = _익명화_api호출(SYSTEM_PROMPT, 프롬프트, 매핑)
    매핑 = None
    return _parse_json_response(응답텍스트)


# ============================================================
# Step 3: 제안 표시 + 승인 (extraction은 메모리 보관)
# ============================================================
def 제안확인(분석결과):
    """💡⚖설명의무 제안만 표시. extraction은 그대로 반환.
    Returns: (extraction, approved_texts: list[str])
             approved_texts가 비면 제안 없음 또는 전부 거부."""
    extraction = 분석결과.get("extraction", {})
    suggestions = 분석결과.get("suggestions", [])
    legal = 분석결과.get("legal", [])
    informed_consent = 분석결과.get("informed_consent", {})

    approved_texts = []
    has_any = bool(suggestions or legal or informed_consent.get("chart_text"))

    if not has_any:
        print("\n [AI 검토] 검토 의견 없음")
        return extraction, approved_texts

    print("\n=== AI 검토 결과 ===")

    # ── AI 검토 의견 (💡) ──
    if suggestions:
        print("\n── AI 검토 의견 ──")
        for i, s in enumerate(suggestions, 1):
            print(f"  💡 {i}. {s.get('content', '')} ({s.get('reason', '')})")
            chart_text = s.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 법적 확인사항 (⚖) ──
    if legal:
        print("\n── 법적 확인사항 ──")
        for i, l in enumerate(legal, 1):
            print(f"  ⚖ {i}. {l.get('content', '')} ({l.get('reason', '')})")
            chart_text = l.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 설명의무 기록 ──
    ic_text = informed_consent.get("chart_text", "")
    if ic_text:
        drugs = ", ".join(informed_consent.get("drugs", []))
        se = ", ".join(informed_consent.get("side_effects", []))
        print(f"\n── 설명의무 기록 ──")
        if drugs:
            print(f"   약물: {drugs}  |  부작용: {se}")
        print(f"   제안: \"{ic_text}\"")
        if input("   → 차트에 반영할까요? (y/n): ").strip().lower() == "y":
            approved_texts.append(ic_text)

    return extraction, approved_texts


# ============================================================
# Step 4: 승인된 chart_text를 free-text 아래에 추가 (API 없음)
# ============================================================
def 제안_free_text_추가(free_text, approved_texts):
    """승인된 chart_text들을 free_text 아래에 덧붙인다."""
    if not approved_texts:
        return free_text
    추가문구 = "\n".join(approved_texts)
    구분선 = "\n---\n" if free_text.strip() else ""
    return free_text + 구분선 + 추가문구


# ============================================================
# Step 5: 의사 직접 수정
# ============================================================
def 의사_최종수정(free_text):
    """차트를 의사에게 보여주고 직접 수정하게 한다.
    새 내용 입력 시 교체. 빈 줄 입력 시 원본 그대로 확정."""
    print("\n=== 최종 차트 확인 ===")
    print("─" * 50)
    print(free_text)
    print("─" * 50)
    print("수정이 필요하면 전체 내용을 다시 입력하세요.")
    print("(수정 없이 확정하려면 바로 Enter)")

    줄들 = []
    while True:
        줄 = input()
        if 줄 == "":
            break
        줄들.append(줄)

    return "\n".join(줄들) if 줄들 else free_text


# ============================================================
# Step 6 내부: 추출 데이터 요약 표시
# ============================================================
def _추출데이터_요약표시(extraction):
    """추출된 데이터를 한눈에 보기 출력"""
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"  [활력징후] {bp}{hr}{ht}{wt}{bmi}")

    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"  [생활습관] {', '.join(항목들)}")

    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"  [진단] {목록}")

    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"  [검사결과] {목록}")

    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"  [영상검사] {목록}")

    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"  [처방] {목록}")

    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"  [추적계획] {목록}")

    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"  [검사처방] {목록}")

    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"  [처방요약] {ps}")

    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if 변경 and 변경.get("변경유형") and 변경.get("새값"):
            print(f"  [환자정보-{항목}] ({변경['변경유형']}) {변경.get('새값', '')}")


# ============================================================
# Step 6 내부: 항목별 y/n 승인
# ============================================================
def _추출데이터_항목별_승인(extraction):
    """항목별 카테고리 단위로 y/n 질문. Returns: approved_data dict"""
    approved = {}

    # 활력징후
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기", "심박수", "키", "몸무게"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"\n  [활력징후] {bp}{hr}{ht}{wt}{bmi}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["vitals"] = vitals

    # 생활습관
    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"\n  [생활습관] {', '.join(항목들)}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lifestyle"] = lifestyle

    # 진단
    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"\n  [진단] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["diagnoses"] = diagnoses

    # 검사결과
    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"\n  [검사결과] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lab_results"] = labs

    # 영상검사
    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"\n  [영상검사] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["imaging"] = imaging

    # 처방
    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"\n  [처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescriptions"] = prescriptions

    # 추적계획
    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"\n  [추적계획] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["tracking"] = tracking

    # 검사처방
    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"\n  [검사처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["test_orders"] = test_orders

    # 처방요약
    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"\n  [처방요약] {ps}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescription_summary"] = ps

    # 환자정보
    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if not 변경 or not 변경.get("변경유형"):
            continue
        유형표시 = {"add": "추가", "modify": "수정", "remove": "삭제"}.get(변경.get("변경유형", ""), "변경")
        print(f"\n  [환자정보-{항목}] ({유형표시}) {변경.get('기존값', '')} → {변경.get('새값', '')}")
        if 변경.get("근거"):
            print(f"     근거: {변경['근거']}")
        if input("  → 업데이트할까요? (y/n): ").strip().lower() == "y":
            if "patient_info" not in approved:
                approved["patient_info"] = {}
            approved["patient_info"][항목] = 변경

    return approved


# ============================================================
# Step 6: 2번째 API — 재추출 (선택적)
# ============================================================
def 재추출(환자id, final_free_text, 방문일):
    """최종 확정 free-text로 데이터만 재추출 (2번째 API).
    Returns: extraction dict or None"""
    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_text = final_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else final_free_text

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[최종 확정 차트]
{익명_text}

위 최종 차트에서 데이터를 추출하세요."""

    응답텍스트 = _익명화_api호출(REEXTRACT_SYSTEM, 프롬프트, 매핑)
    매핑 = None
    결과 = _parse_json_response(응답텍스트)
    if 결과:
        return 결과.get("extraction", 결과)
    return None


# ============================================================
# Step 7: 테이블 저장
# ============================================================
def 분석결과_저장(환자id, 방문id, final_free_text, approved_data):
    """승인된 항목을 유형별로 테이블에 저장. Returns: 저장건수"""
    저장건수 = 0

    # --- 방문 테이블 일괄 업데이트 (free_text, 활력징후, 생활습관, 처방요약) ---
    # 방문기록수정()을 여러 번 호출하면 매번 새 레코드가 생성되므로
    # 한 번의 UPDATE로 처리하여 불필요한 레코드 복사 방지
    방문_업데이트 = {}
    vitals = approved_data.get("vitals", {})
    lifestyle = approved_data.get("lifestyle", {})
    ps = approved_data.get("prescription_summary", "")

    if final_free_text:
        방문_업데이트["free_text"] = final_free_text
    for 필드 in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"]:
        if vitals.get(필드) is not None:
            방문_업데이트[필드] = vitals[필드]
    for 필드 in ["흡연", "음주", "운동"]:
        if lifestyle.get(필드):
            방문_업데이트[필드] = lifestyle[필드]
    if ps:
        방문_업데이트["처방요약"] = ps

    if 방문_업데이트:
        방문기록_일괄수정(방문id, 방문_업데이트)
        저장건수 += 1
        if final_free_text:
            print(f"  → free_text 저장 완료")
        if vitals:
            bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
            print(f"  → 활력징후 저장: {bp}")
        if lifestyle:
            print(f"  → 생활습관 저장 완료")
        if ps:
            print(f"  → 처방요약 저장: {ps[:40]}{'...' if len(ps) > 40 else ''}")

    # --- 진단 ---
    for d in approved_data.get("diagnoses", []):
        진단추가(환자id, 방문id, d["진단명"], d.get("상태", "활성"), d.get("비고", ""), d.get("표준코드", None))
        저장건수 += 1
        print(f"  → 진단 저장: {d['진단명']} ({d.get('상태', '')})")

    # --- 검사결과 ---
    for k in approved_data.get("lab_results", []):
        검사결과추가(환자id, k.get("검사시행일", ""), k["검사항목"], k.get("결과값", ""),
                   k.get("단위", ""), k.get("참고범위", ""), 방문id=방문id)
        _검사처방_시행완료_매칭(환자id, k.get("검사시행일", ""), k["검사항목"])
        저장건수 += 1
        print(f"  → 검사결과 저장: {k['검사항목']} {k.get('결과값', '')}")

    # --- 영상검사 ---
    for e in approved_data.get("imaging", []):
        영상검사추가(환자id, e.get("검사시행일", ""), e["검사종류"], e.get("결과요약", ""),
                   e.get("주요수치", ""), 방문id=방문id)
        저장건수 += 1
        print(f"  → 영상검사 저장: {e['검사종류']}")

    # --- 처방 ---
    for p in approved_data.get("prescriptions", []):
        처방추가(환자id, 방문id, p.get("약품명", ""), p.get("성분명", ""), p.get("용량", ""), p.get("용법", ""), p.get("일수", 0))
        저장건수 += 1
        print(f"  → 처방 저장: {p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')}")

    # --- 추적계획 ---
    for t in approved_data.get("tracking", []):
        추적계획추가(환자id, 방문id, t.get("예정일", ""), t.get("내용", ""))
        저장건수 += 1
        print(f"  → 추적계획 저장: {t.get('내용', '')}")

    # --- 검사처방 ---
    # 처방일 fallback: AI가 처방일을 비워둔 경우 방문일로 대체
    _방문일_fallback = ""
    if approved_data.get("test_orders"):
        _conn = sqlite3.connect(DB경로)
        try:
            row = _conn.execute(
                "SELECT 방문일 FROM 방문 WHERE 방문id=? AND 유효여부=1", (방문id,)
            ).fetchone()
            if row:
                _방문일_fallback = row[0]
        finally:
            _conn.close()

    for o in approved_data.get("test_orders", []):
        처방일 = o.get("처방일", "") or _방문일_fallback
        검사처방추가(환자id, 방문id, o.get("검사명", ""), 처방일)
        저장건수 += 1
        print(f"  → 검사처방 저장: {o.get('검사명', '')} (예정: {처방일})")

    # --- 환자정보 업데이트 ---
    기존환자 = 환자전체기록조회(환자id)
    for 항목명, 변경 in approved_data.get("patient_info", {}).items():
        변경유형 = 변경.get("변경유형", "")
        새값 = 변경.get("새값", "")
        기존값 = 기존환자["환자"].get(항목명, "") if 기존환자 else ""

        if 변경유형 == "add":
            최종값 = (기존값 + ", " + 새값).strip(", ") if 기존값 else 새값
        elif 변경유형 == "modify":
            최종값 = 새값
        elif 변경유형 == "remove":
            최종값 = ""
        else:
            continue

        환자정보수정(환자id, 항목명, 최종값)
        저장건수 += 1
        print(f"  → {항목명} 업데이트: {최종값}")

    return 저장건수


# ============================================================
# 전체 흐름 orchestrator (main_system.py에서 호출)
# ============================================================
def 차트분석_저장_전체흐름(환자id, 방문id, free_text, 방문일=None):
    """Steps 2~7 전체 실행.
    방문id는 호출 전에 미리 생성되어 있어야 함.
    Returns: (final_free_text, 저장건수) or (None, 0) on failure"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    # Step 2: AI 분석
    print("\n [AI 분석 중...]")
    분석결과 = 차트분석(환자id, free_text, 방문일)
    if not 분석결과:
        print(" [오류] AI 분석 실패")
        return None, 0

    # Step 3: 제안 확인 (extraction 메모리 보관)
    extraction, approved_texts = 제안확인(분석결과)

    # Step 4 & 5: 제안이 있고 승인된 것이 있으면 붙이고 의사 수정
    final_free_text = free_text
    if approved_texts:
        final_free_text = 제안_free_text_추가(free_text, approved_texts)
        final_free_text = 의사_최종수정(final_free_text)
    # 제안 없으면 Steps 4, 5 건너뜀

    # Step 6: 추출 데이터 표시 → 재분석 여부 선택
    print("\n=== 테이블 저장 데이터 (최초 분석 기준) ===")
    _추출데이터_요약표시(extraction)

    재분석 = input("\n차트 수정으로 데이터가 바뀌었나요? AI로 재분석할까요? (y/n): ").strip().lower()
    if 재분석 == "y":
        print(" [재분석 중...]")
        재추출결과 = 재추출(환자id, final_free_text, 방문일)
        if 재추출결과:
            extraction = 재추출결과
            print(" [재분석 완료]")
        else:
            print(" [경고] 재분석 실패. 최초 추출 데이터 사용.")

    # 항목별 승인
    print("\n=== 항목별 저장 승인 ===")
    approved_data = _추출데이터_항목별_승인(extraction)

    # Step 7: 저장
    print("\n [저장 중...]")
    저장건수 = 분석결과_저장(환자id, 방문id, final_free_text, approved_data)
    print(f"\n 총 {저장건수}건 저장 완료.")

    return final_free_text, 저장건수


# ============================================================
# 헬퍼: 검사처방 시행완료 자동 매칭
# ============================================================
def _검사처방_시행완료_매칭(환자id, 검사시행일, 검사항목):
    """검사결과 저장 시 매칭되는 미시행 검사처방을 시행여부=1로 업데이트."""
    conn = sqlite3.connect(DB경로)
    try:
        미시행 = conn.execute(
            "SELECT 처방검사id, 검사명 FROM 검사처방 "
            "WHERE 환자id=? AND 시행여부=0 AND 유효여부=1",
            (환자id,)
        ).fetchall()
        for row in 미시행:
            처방검사id, 검사명 = row[0], row[1]
            if 검사항목 in 검사명 or 검사명 in 검사항목:
                conn.execute(
                    "UPDATE 검사처방 SET 시행여부=1 WHERE 처방검사id=?",
                    (처방검사id,)
                )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 차트 수정 함수 (기존 차트분석_저장_전체흐름()과 별개)
# ============================================================
def _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일):
    """free-text 수정 전후를 비교하여 변경사항만 추출한다. 저장하지 않음.
    Returns: dict (변경, 추가, 삭제, 활력징후_변경, 처방요약_변경) 또는 None"""

    시스템_프롬프트 = """당신은 의료 차트 데이터 비교 어시스턴트입니다.
수정 전후의 free-text를 비교하여 변경된 의료 데이터만 추출하세요.
새로운 제안이나 검토 의견은 절대 하지 마세요.
변경/추가/삭제된 데이터만 JSON으로 출력하세요.

JSON 형식:
{
  "변경": [
    {"테이블": "검사결과", "기존": {"검사항목": "HbA1c", "결과값": "9.5"}, "수정후": {"검사항목": "HbA1c", "결과값": "8.5"}, "검사시행일": "260301"}
  ],
  "추가": [
    {"테이블": "검사결과", "데이터": {"검사항목": "TG", "결과값": "150", "단위": "mg/dL", "검사시행일": "260301"}}
  ],
  "삭제": [
    {"테이블": "검사결과", "데이터": {"검사항목": "LDL", "결과값": "160", "검사시행일": "260301"}}
  ],
  "활력징후_변경": {"수축기": 140, "이완기": 88} 또는 null,
  "처방요약_변경": "변경된 처방요약" 또는 null
}
변경이 없는 항목은 빈 배열로.
활력징후_변경, 처방요약_변경은 변경 없으면 null로.
순수 JSON만 출력. 마크다운이나 설명 없이."""

    프롬프트 = f"""[방문일: {방문일}]

[수정 전 free-text]
{기존_free_text}

[수정 후 free-text]
{새_free_text}

위 두 텍스트를 비교하여 변경된 의료 데이터만 추출하세요."""

    # 익명화 처리
    기록 = 환자전체기록조회(환자id)
    if 기록:
        익명기록, 매핑 = api_익명화(기록)
        랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
        실제이름 = 매핑.get(랜덤id) if 랜덤id else None
        익명_기존 = 기존_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 기존_free_text
        익명_새 = 새_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 새_free_text
        익명_프롬프트 = 프롬프트.replace(기존_free_text, 익명_기존).replace(새_free_text, 익명_새)
    else:
        매핑 = {}
        익명_프롬프트 = 프롬프트

    # API 호출
    응답 = _익명화_api호출(시스템_프롬프트, 익명_프롬프트, 매핑)
    매핑 = None  # 매핑 메모리 해제

    if not 응답:
        return None

    변경사항 = _parse_json_response(응답)
    return 변경사항  # 파싱 실패 시 None, 성공 시 dict


def 차트_데이터만_수정(환자id, 방문id, 기존_free_text, 새_free_text, 방문일, 변경사항=None):
    """free-text 수정 시 변경된 데이터만 감지하여 테이블을 업데이트한다.
    AI 제안/검토 의견 없음. 데이터 변경분만 처리.
    변경사항이 이미 있으면 그대로 사용, 없으면 새로 추출.
    Returns: (변경사항_요약, 변경건수)"""

    if 변경사항 is None:
        변경사항 = _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일)
    if not 변경사항:
        return "변경사항 추출 실패", 0

    변경건수 = 0
    변경요약 = []
    conn = sqlite3.connect(DB경로)

    try:
        # free-text 자체 업데이트
        방문기록_일괄수정(방문id, {"free_text": 새_free_text})

        # 활력징후 변경
        vs = 변경사항.get("활력징후_변경")
        if vs:
            필드 = {k: vs[k] for k in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"] if vs.get(k) is not None}
            if 필드:
                방문기록_일괄수정(방문id, 필드)
                변경건수 += 1
                변경요약.append(f"활력징후 수정: {필드}")

        # 처방요약 변경
        if 변경사항.get("처방요약_변경"):
            방문기록_일괄수정(방문id, {"처방요약": 변경사항["처방요약_변경"]})
            변경건수 += 1
            변경요약.append("처방요약 수정")

        # 변경된 항목 처리 (기존 무효화 + 새 레코드)
        for 항목 in 변경사항.get("변경", []):
            테이블 = 항목.get("테이블", "")
            기존 = 항목.get("기존", {})
            수정후 = 항목.get("수정후", {})
            시행일 = 항목.get("검사시행일", 방문일)

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 기존.get("검사항목"), 기존.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text 수정' WHERE 검사id=?", (r[0],))
                conn.commit()
                검사결과추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사항목", 기존.get("검사항목")),
                           수정후.get("결과값", ""), 수정후.get("단위", ""), 수정후.get("참고범위", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"검사결과 수정: {기존.get('검사항목')} {기존.get('결과값')} → {수정후.get('결과값')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text 수정' WHERE 진단id=?", (r[0],))
                conn.commit()
                진단추가(환자id, 방문id, 수정후.get("진단명", 기존.get("진단명")),
                        수정후.get("상태", "활성"), 수정후.get("비고", ""), 수정후.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 수정: {기존.get('진단명')} → {수정후.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text 수정' WHERE 처방id=?", (r[0],))
                conn.commit()
                처방추가(환자id, 방문id, 수정후.get("약품명", 기존.get("약품명")),
                        수정후.get("성분명", ""), 수정후.get("용량", ""),
                        수정후.get("용법", ""), 수정후.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 수정: {기존.get('약품명')} → {수정후.get('약품명')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 기존.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text 수정' WHERE 영상id=?", (r[0],))
                conn.commit()
                영상검사추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사종류", 기존.get("검사종류")),
                           수정후.get("결과요약", ""), 수정후.get("주요수치", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 수정: {기존.get('검사종류')}")

        # 추가된 항목 처리
        for 항목 in 변경사항.get("추가", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                검사결과추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사항목"), 데이터.get("결과값", ""),
                           데이터.get("단위", ""), 데이터.get("참고범위", ""),
                           방문id=방문id)
                _검사처방_시행완료_매칭(환자id, 데이터.get("검사시행일", 방문일), 데이터.get("검사항목", ""))
                변경건수 += 1
                변경요약.append(f"검사결과 추가: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                영상검사추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사종류"), 데이터.get("결과요약", ""),
                           데이터.get("주요수치", ""), 방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 추가: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                진단추가(환자id, 방문id, 데이터.get("진단명"), 데이터.get("상태", "활성"),
                        데이터.get("비고", ""), 데이터.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 추가: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                처방추가(환자id, 방문id, 데이터.get("약품명"), 데이터.get("성분명", ""),
                        데이터.get("용량", ""), 데이터.get("용법", ""), 데이터.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 추가: {데이터.get('약품명')}")

            elif 테이블 == "추적계획":
                추적계획추가(환자id, 방문id, 데이터.get("예정일", ""), 데이터.get("내용", ""))
                변경건수 += 1
                변경요약.append(f"추적계획 추가: {데이터.get('내용')}")

            elif 테이블 == "검사처방":
                검사처방추가(환자id, 방문id, 데이터.get("검사명", ""), 데이터.get("처방일", ""))
                변경건수 += 1
                변경요약.append(f"검사처방 추가: {데이터.get('검사명')}")

        # 삭제된 항목 처리 (무효화)
        for 항목 in 변경사항.get("삭제", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 데이터.get("검사항목"), 데이터.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 검사id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"검사결과 삭제: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 데이터.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 영상id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"영상검사 삭제: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 진단id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"진단 삭제: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 처방id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"처방 삭제: {데이터.get('약품명')}")

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"업데이트 오류: {e}", 0
    finally:
        conn.close()

    요약텍스트 = "\n".join(변경요약) if 변경요약 else "변경사항 없음"
    return 요약텍스트, 변경건수


def 차트_재분석_저장(환자id, 방문id, 새_free_text, 방문일):
    """free-text 수정 후 AI 재분석. 기존 데이터 무효화 후 재추출/저장.
    Streamlit 호환 (input() 사용 안 함).
    Returns: (extraction_data, 저장건수) or (None, 0)"""

    # 1. 이 방문에 연결된 기존 데이터 전부 무효화
    conn = sqlite3.connect(DB경로)
    try:
        for 테이블 in ["진단", "추적계획", "처방", "검사처방"]:
            conn.execute(
                f"UPDATE {테이블} SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
                (방문id,)
            )
        conn.execute(
            "UPDATE 검사결과 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.execute(
            "UPDATE 영상검사 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.commit()
    finally:
        conn.close()

    # 2. free-text 업데이트
    방문기록_일괄수정(방문id, {"free_text": 새_free_text})

    # 3. AI 재분석 (차트분석 함수 직접 호출, input() 없음)
    분석결과 = 차트분석(환자id, 새_free_text, 방문일)
    if not 분석결과:
        return None, 0

    extraction = 분석결과.get("extraction", {})
    if not extraction:
        return None, 0

    # 4. 전체 항목 자동 승인하여 저장
    approved_data = {}
    approved_data["vitals"] = extraction.get("vitals", {})
    approved_data["lifestyle"] = extraction.get("lifestyle", {})
    approved_data["diagnoses"] = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    approved_data["lab_results"] = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    approved_data["imaging"] = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    approved_data["prescriptions"] = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    approved_data["tracking"] = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    approved_data["test_orders"] = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    approved_data["prescription_summary"] = extraction.get("prescription_summary", "")
    approved_data["patient_info"] = {k: v for k, v in extraction.get("patient_info", {}).items() if v and v.get("변경유형")}

    저장건수 = 분석결과_저장(환자id, 방문id, 새_free_text, approved_data)
    방문기록_일괄수정(방문id, {"분석완료": 1})

    return extraction, 저장건수
def _parse_json_response(text):
    """AI 응답에서 JSON 파싱 (마크다운 코드블록 제거 포함)"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f" [오류] AI 응답을 JSON으로 파싱할 수 없습니다.")
        print(f" 원본 응답:\n{text[:500]}")
        return None



def _익명화_api호출(system, 프롬프트, 매핑, max_tokens=4096):
    """익명화된 프롬프트로 API 호출 후 복원. Returns: 응답텍스트 or None"""
    응답 = api_재시도(lambda: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": 프롬프트}]
    ))
    if not 응답:
        return None
    텍스트 = api_복원(응답.content[0].text.strip(), 매핑)
    return 텍스트


# ============================================================
# 공공 DB 조회 헬퍼 (차트분석 내부용)
# ============================================================

# 흔한 내과 진단명 → 영문 변환 테이블
_진단명_영문 = {
    "고혈압": "hypertension",
    "고지혈증": "dyslipidemia",
    "당뇨": "diabetes mellitus",
    "당뇨전단계": "prediabetes",
    "갑상선기능저하증": "hypothyroidism",
    "갑상선기능항진증": "hyperthyroidism",
    "통풍": "gout",
    "골다공증": "osteoporosis",
    "만성콩팥병": "chronic kidney disease",
    "심방세동": "atrial fibrillation",
    "심부전": "heart failure",
    "관상동맥질환": "coronary artery disease",
    "뇌졸중": "stroke",
    "빈혈": "anemia",
    "지방간": "fatty liver",
}


def _free_text에서_약품명_추출(free_text):
    """free-text에서 약품명 패턴 간단 추출 (영문 소문자 + 숫자mg 조합).
    완벽하지 않아도 됨 — AI가 나중에 정확히 추출함."""
    import re
    패턴 = r'\b[a-z]{4,}(?:\s*\d+\s*mg)?\b'
    후보 = re.findall(패턴, free_text.lower())
    제외목록 = {"with", "that", "this", "from", "have", "been", "will", "also",
               "than", "more", "less", "after", "before", "normal", "blood",
               "free", "text", "note", "plan", "done", "left", "right"}
    seen = set()
    약품목록 = []
    for w in 후보:
        w = w.strip()
        if w not in seen and w not in 제외목록:
            seen.add(w)
            약품목록.append(w)
        if len(약품목록) >= 5:
            break
    return 약품목록


def _free_text에서_pubmed_검색어_추출(free_text):
    """free-text에서 진단명을 찾아 영문 검색어 생성."""
    for 한글, 영문 in _진단명_영문.items():
        if 한글 in free_text:
            return f"{영문} treatment guideline"
    return None


def _공공DB_조회(free_text):
    """처방 안전성(DUR/e약은요/급여) + PubMed 조회.
    Returns: (공공DB결과_문자열, 조회성공여부)"""
    try:
        약품목록 = _free_text에서_약품명_추출(free_text)
        검색어 = _free_text에서_pubmed_검색어_추출(free_text)

        안전성결과 = 처방_안전성_조회(약품목록) if 약품목록 else {}
        pubmed결과 = pubmed_검색(검색어) if 검색어 else []

        dur_정보 = {약품: v["dur"] for 약품, v in 안전성결과.items()}
        약품정보 = {약품: v["약품정보"] for 약품, v in 안전성결과.items()}
        급여정보 = {약품: v["급여정보"] for 약품, v in 안전성결과.items()}

        조회결과 = (
            "[공공 DB 조회 결과 — 참고하여 검토 의견에 반영하세요]\n\n"
            "[DUR 정보]\n" + json.dumps(dur_정보, ensure_ascii=False, indent=2) + "\n\n"
            "[약품 정보 (e약은요)]\n" + json.dumps(약품정보, ensure_ascii=False, indent=2) + "\n\n"
            "[급여 정보]\n" + json.dumps(급여정보, ensure_ascii=False, indent=2) + "\n\n"
            "[PubMed 검색 결과]\n" + json.dumps(pubmed결과, ensure_ascii=False, indent=2) + "\n\n"
            "위 정보를 검토 의견(💡), 법적 확인(⚖), 설명의무에 활용하세요.\n"
            "DUR에서 병용금기가 발견되면 반드시 ⚖ 법적 확인사항에 포함하세요.\n"
            "PubMed 논문은 관련 있는 것만 검토 의견에 포함하세요.\n"
            "급여 정보가 있으면 처방 관련 제안에 급여 여부를 명시하세요."
        )

        return 조회결과, True

    except Exception as e:
        print(f"  ⚠ 공공 DB 조회 실패: {e}")
        return "[공공 DB 조회 결과 — 조회 실패 또는 해당 정보 없음. 내부 지식으로 판단하세요.]", False


# ============================================================
# Step 2: 1번째 API — 분석 + 추출 + 제안
# ============================================================
def 차트분석(환자id, free_text, 방문일=None):
    """AI 분석: 데이터 추출 + 검토의견 + 법적확인 + 설명의무 전부 수행.
    Returns: dict(extraction, suggestions, legal, informed_consent) or None"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    나이 = 나이계산(기록["환자"]["생년월일"])
    if 나이 is not None:
        기록["환자"]["나이"] = f"{나이}세"

    # 공공 DB 조회 (AI API 호출 전)
    공공DB_문자열, 조회성공 = _공공DB_조회(free_text)
    if not 조회성공:
        print("  ⚠ 공공 DB 조회 실패. AI 내부 지식으로 검토합니다.")

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_free_text = free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else free_text

    패턴요약 = 의사패턴_요약생성()
    패턴요약_섹션 = f"\n[의사 진료 패턴 — 참고하여 맥락에 맞는 검토 의견 제시에 활용]\n{패턴요약}\n" if 패턴요약 else ""

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[오늘 free-text]
{익명_free_text}

{공공DB_문자열}{패턴요약_섹션}
위 free-text를 분석하여 기존 데이터와 비교한 뒤, 지정된 JSON 형식으로 출력하세요."""

    응답텍스트 = _익명화_api호출(SYSTEM_PROMPT, 프롬프트, 매핑)
    매핑 = None
    return _parse_json_response(응답텍스트)


# ============================================================
# Step 3: 제안 표시 + 승인 (extraction은 메모리 보관)
# ============================================================
def 제안확인(분석결과):
    """💡⚖설명의무 제안만 표시. extraction은 그대로 반환.
    Returns: (extraction, approved_texts: list[str])
             approved_texts가 비면 제안 없음 또는 전부 거부."""
    extraction = 분석결과.get("extraction", {})
    suggestions = 분석결과.get("suggestions", [])
    legal = 분석결과.get("legal", [])
    informed_consent = 분석결과.get("informed_consent", {})

    approved_texts = []
    has_any = bool(suggestions or legal or informed_consent.get("chart_text"))

    if not has_any:
        print("\n [AI 검토] 검토 의견 없음")
        return extraction, approved_texts

    print("\n=== AI 검토 결과 ===")

    # ── AI 검토 의견 (💡) ──
    if suggestions:
        print("\n── AI 검토 의견 ──")
        for i, s in enumerate(suggestions, 1):
            print(f"  💡 {i}. {s.get('content', '')} ({s.get('reason', '')})")
            chart_text = s.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 법적 확인사항 (⚖) ──
    if legal:
        print("\n── 법적 확인사항 ──")
        for i, l in enumerate(legal, 1):
            print(f"  ⚖ {i}. {l.get('content', '')} ({l.get('reason', '')})")
            chart_text = l.get("chart_text", "")
            if chart_text:
                print(f"     제안: \"{chart_text}\"")
            if input("     → 차트에 반영할까요? (y/n): ").strip().lower() == "y" and chart_text:
                approved_texts.append(chart_text)

    # ── 설명의무 기록 ──
    ic_text = informed_consent.get("chart_text", "")
    if ic_text:
        drugs = ", ".join(informed_consent.get("drugs", []))
        se = ", ".join(informed_consent.get("side_effects", []))
        print(f"\n── 설명의무 기록 ──")
        if drugs:
            print(f"   약물: {drugs}  |  부작용: {se}")
        print(f"   제안: \"{ic_text}\"")
        if input("   → 차트에 반영할까요? (y/n): ").strip().lower() == "y":
            approved_texts.append(ic_text)

    return extraction, approved_texts


# ============================================================
# Step 4: 승인된 chart_text를 free-text 아래에 추가 (API 없음)
# ============================================================
def 제안_free_text_추가(free_text, approved_texts):
    """승인된 chart_text들을 free_text 아래에 덧붙인다."""
    if not approved_texts:
        return free_text
    추가문구 = "\n".join(approved_texts)
    구분선 = "\n---\n" if free_text.strip() else ""
    return free_text + 구분선 + 추가문구


# ============================================================
# Step 5: 의사 직접 수정
# ============================================================
def 의사_최종수정(free_text):
    """차트를 의사에게 보여주고 직접 수정하게 한다.
    새 내용 입력 시 교체. 빈 줄 입력 시 원본 그대로 확정."""
    print("\n=== 최종 차트 확인 ===")
    print("─" * 50)
    print(free_text)
    print("─" * 50)
    print("수정이 필요하면 전체 내용을 다시 입력하세요.")
    print("(수정 없이 확정하려면 바로 Enter)")

    줄들 = []
    while True:
        줄 = input()
        if 줄 == "":
            break
        줄들.append(줄)

    return "\n".join(줄들) if 줄들 else free_text


# ============================================================
# Step 6 내부: 추출 데이터 요약 표시
# ============================================================
def _추출데이터_요약표시(extraction):
    """추출된 데이터를 한눈에 보기 출력"""
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"  [활력징후] {bp}{hr}{ht}{wt}{bmi}")

    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"  [생활습관] {', '.join(항목들)}")

    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"  [진단] {목록}")

    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"  [검사결과] {목록}")

    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"  [영상검사] {목록}")

    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"  [처방] {목록}")

    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"  [추적계획] {목록}")

    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"  [검사처방] {목록}")

    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"  [처방요약] {ps}")

    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if 변경 and 변경.get("변경유형") and 변경.get("새값"):
            print(f"  [환자정보-{항목}] ({변경['변경유형']}) {변경.get('새값', '')}")


# ============================================================
# Step 6 내부: 항목별 y/n 승인
# ============================================================
def _추출데이터_항목별_승인(extraction):
    """항목별 카테고리 단위로 y/n 질문. Returns: approved_data dict"""
    approved = {}

    # 활력징후
    vitals = extraction.get("vitals", {})
    if any(vitals.get(k) for k in ["수축기", "이완기", "심박수", "키", "몸무게"]):
        bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr = f"-{vitals['심박수']}" if vitals.get("심박수") else ""
        ht = f", 키 {vitals['키']}cm" if vitals.get("키") else ""
        wt = f", 체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f", BMI {vitals['BMI']}" if vitals.get("BMI") else ""
        print(f"\n  [활력징후] {bp}{hr}{ht}{wt}{bmi}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["vitals"] = vitals

    # 생활습관
    lifestyle = extraction.get("lifestyle", {})
    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        print(f"\n  [생활습관] {', '.join(항목들)}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lifestyle"] = lifestyle

    # 진단
    diagnoses = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    if diagnoses:
        목록 = " / ".join(f"{d['진단명']}({d.get('상태', '')})" for d in diagnoses)
        print(f"\n  [진단] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["diagnoses"] = diagnoses

    # 검사결과
    labs = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    if labs:
        목록 = " / ".join(f"{l['검사항목']} {l.get('결과값', '')}{l.get('단위', '')}" for l in labs)
        print(f"\n  [검사결과] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["lab_results"] = labs

    # 영상검사
    imaging = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    if imaging:
        목록 = " / ".join(f"{i['검사종류']}" for i in imaging)
        print(f"\n  [영상검사] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["imaging"] = imaging

    # 처방
    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    if prescriptions:
        목록 = " / ".join(
            f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            for p in prescriptions
        )
        print(f"\n  [처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescriptions"] = prescriptions

    # 추적계획
    tracking = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    if tracking:
        목록 = " / ".join(f"{t.get('내용', '')} 예정 {t.get('예정일', '')}" for t in tracking)
        print(f"\n  [추적계획] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["tracking"] = tracking

    # 검사처방
    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    if test_orders:
        목록 = " / ".join(f"{o.get('검사명', '')} 예정 {o.get('처방일', '')}" for o in test_orders)
        print(f"\n  [검사처방] {목록}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["test_orders"] = test_orders

    # 처방요약
    ps = extraction.get("prescription_summary", "")
    if ps:
        print(f"\n  [처방요약] {ps}")
        if input("  → 저장할까요? (y/n): ").strip().lower() == "y":
            approved["prescription_summary"] = ps

    # 환자정보
    pi = extraction.get("patient_info", {})
    for 항목 in ["가족력", "약부작용이력"]:
        변경 = pi.get(항목, {})
        if not 변경 or not 변경.get("변경유형"):
            continue
        유형표시 = {"add": "추가", "modify": "수정", "remove": "삭제"}.get(변경.get("변경유형", ""), "변경")
        print(f"\n  [환자정보-{항목}] ({유형표시}) {변경.get('기존값', '')} → {변경.get('새값', '')}")
        if 변경.get("근거"):
            print(f"     근거: {변경['근거']}")
        if input("  → 업데이트할까요? (y/n): ").strip().lower() == "y":
            if "patient_info" not in approved:
                approved["patient_info"] = {}
            approved["patient_info"][항목] = 변경

    return approved


# ============================================================
# Step 6: 2번째 API — 재추출 (선택적)
# ============================================================
def 재추출(환자id, final_free_text, 방문일):
    """최종 확정 free-text로 데이터만 재추출 (2번째 API).
    Returns: extraction dict or None"""
    기록 = 환자전체기록조회(환자id)
    if not 기록:
        return None

    익명기록, 매핑 = api_익명화(기록)
    랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
    실제이름 = 매핑.get(랜덤id) if 랜덤id else None
    익명_text = final_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else final_free_text

    프롬프트 = f"""[기존 환자 데이터]
{json.dumps(익명기록, ensure_ascii=False, indent=2)}

[이 차트의 방문일: {방문일}]
[최종 확정 차트]
{익명_text}

위 최종 차트에서 데이터를 추출하세요."""

    응답텍스트 = _익명화_api호출(REEXTRACT_SYSTEM, 프롬프트, 매핑)
    매핑 = None
    결과 = _parse_json_response(응답텍스트)
    if 결과:
        return 결과.get("extraction", 결과)
    return None


# ============================================================
# Step 7: 테이블 저장
# ============================================================
def 분석결과_저장(환자id, 방문id, final_free_text, approved_data):
    """승인된 항목을 유형별로 테이블에 저장. Returns: 저장건수"""
    저장건수 = 0

    # --- 방문 테이블 일괄 업데이트 (free_text, 활력징후, 생활습관, 처방요약) ---
    # 방문기록수정()을 여러 번 호출하면 매번 새 레코드가 생성되므로
    # 한 번의 UPDATE로 처리하여 불필요한 레코드 복사 방지
    방문_업데이트 = {}
    vitals = approved_data.get("vitals", {})
    lifestyle = approved_data.get("lifestyle", {})
    ps = approved_data.get("prescription_summary", "")

    if final_free_text:
        방문_업데이트["free_text"] = final_free_text
    for 필드 in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"]:
        if vitals.get(필드) is not None:
            방문_업데이트[필드] = vitals[필드]
    for 필드 in ["흡연", "음주", "운동"]:
        if lifestyle.get(필드):
            방문_업데이트[필드] = lifestyle[필드]
    if ps:
        방문_업데이트["처방요약"] = ps

    if 방문_업데이트:
        방문기록_일괄수정(방문id, 방문_업데이트)
        저장건수 += 1
        if final_free_text:
            print(f"  → free_text 저장 완료")
        if vitals:
            bp = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
            print(f"  → 활력징후 저장: {bp}")
        if lifestyle:
            print(f"  → 생활습관 저장 완료")
        if ps:
            print(f"  → 처방요약 저장: {ps[:40]}{'...' if len(ps) > 40 else ''}")

    # --- 진단 ---
    for d in approved_data.get("diagnoses", []):
        진단추가(환자id, 방문id, d["진단명"], d.get("상태", "활성"), d.get("비고", ""), d.get("표준코드", None))
        저장건수 += 1
        print(f"  → 진단 저장: {d['진단명']} ({d.get('상태', '')})")

    # --- 검사결과 ---
    for k in approved_data.get("lab_results", []):
        검사결과추가(환자id, k.get("검사시행일", ""), k["검사항목"], k.get("결과값", ""),
                   k.get("단위", ""), k.get("참고범위", ""), 방문id=방문id)
        _검사처방_시행완료_매칭(환자id, k.get("검사시행일", ""), k["검사항목"])
        저장건수 += 1
        print(f"  → 검사결과 저장: {k['검사항목']} {k.get('결과값', '')}")

    # --- 영상검사 ---
    for e in approved_data.get("imaging", []):
        영상검사추가(환자id, e.get("검사시행일", ""), e["검사종류"], e.get("결과요약", ""),
                   e.get("주요수치", ""), 방문id=방문id)
        저장건수 += 1
        print(f"  → 영상검사 저장: {e['검사종류']}")

    # --- 처방 ---
    for p in approved_data.get("prescriptions", []):
        처방추가(환자id, 방문id, p.get("약품명", ""), p.get("성분명", ""), p.get("용량", ""), p.get("용법", ""), p.get("일수", 0))
        저장건수 += 1
        print(f"  → 처방 저장: {p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')}")

    # --- 추적계획 ---
    for t in approved_data.get("tracking", []):
        추적계획추가(환자id, 방문id, t.get("예정일", ""), t.get("내용", ""))
        저장건수 += 1
        print(f"  → 추적계획 저장: {t.get('내용', '')}")

    # --- 검사처방 ---
    # 처방일 fallback: AI가 처방일을 비워둔 경우 방문일로 대체
    _방문일_fallback = ""
    if approved_data.get("test_orders"):
        _conn = sqlite3.connect(DB경로)
        try:
            row = _conn.execute(
                "SELECT 방문일 FROM 방문 WHERE 방문id=? AND 유효여부=1", (방문id,)
            ).fetchone()
            if row:
                _방문일_fallback = row[0]
        finally:
            _conn.close()

    for o in approved_data.get("test_orders", []):
        처방일 = o.get("처방일", "") or _방문일_fallback
        검사처방추가(환자id, 방문id, o.get("검사명", ""), 처방일)
        저장건수 += 1
        print(f"  → 검사처방 저장: {o.get('검사명', '')} (예정: {처방일})")

    # --- 환자정보 업데이트 ---
    기존환자 = 환자전체기록조회(환자id)
    for 항목명, 변경 in approved_data.get("patient_info", {}).items():
        변경유형 = 변경.get("변경유형", "")
        새값 = 변경.get("새값", "")
        기존값 = 기존환자["환자"].get(항목명, "") if 기존환자 else ""

        if 변경유형 == "add":
            최종값 = (기존값 + ", " + 새값).strip(", ") if 기존값 else 새값
        elif 변경유형 == "modify":
            최종값 = 새값
        elif 변경유형 == "remove":
            최종값 = ""
        else:
            continue

        환자정보수정(환자id, 항목명, 최종값)
        저장건수 += 1
        print(f"  → {항목명} 업데이트: {최종값}")

    return 저장건수


# ============================================================
# 전체 흐름 orchestrator (main_system.py에서 호출)
# ============================================================
def 차트분석_저장_전체흐름(환자id, 방문id, free_text, 방문일=None):
    """Steps 2~7 전체 실행.
    방문id는 호출 전에 미리 생성되어 있어야 함.
    Returns: (final_free_text, 저장건수) or (None, 0) on failure"""
    if not 방문일:
        방문일 = datetime.today().strftime("%y%m%d")

    # Step 2: AI 분석
    print("\n [AI 분석 중...]")
    분석결과 = 차트분석(환자id, free_text, 방문일)
    if not 분석결과:
        print(" [오류] AI 분석 실패")
        return None, 0

    # Step 3: 제안 확인 (extraction 메모리 보관)
    extraction, approved_texts = 제안확인(분석결과)

    # Step 4 & 5: 제안이 있고 승인된 것이 있으면 붙이고 의사 수정
    final_free_text = free_text
    if approved_texts:
        final_free_text = 제안_free_text_추가(free_text, approved_texts)
        final_free_text = 의사_최종수정(final_free_text)
    # 제안 없으면 Steps 4, 5 건너뜀

    # Step 6: 추출 데이터 표시 → 재분석 여부 선택
    print("\n=== 테이블 저장 데이터 (최초 분석 기준) ===")
    _추출데이터_요약표시(extraction)

    재분석 = input("\n차트 수정으로 데이터가 바뀌었나요? AI로 재분석할까요? (y/n): ").strip().lower()
    if 재분석 == "y":
        print(" [재분석 중...]")
        재추출결과 = 재추출(환자id, final_free_text, 방문일)
        if 재추출결과:
            extraction = 재추출결과
            print(" [재분석 완료]")
        else:
            print(" [경고] 재분석 실패. 최초 추출 데이터 사용.")

    # 항목별 승인
    print("\n=== 항목별 저장 승인 ===")
    approved_data = _추출데이터_항목별_승인(extraction)

    # Step 7: 저장
    print("\n [저장 중...]")
    저장건수 = 분석결과_저장(환자id, 방문id, final_free_text, approved_data)
    print(f"\n 총 {저장건수}건 저장 완료.")

    return final_free_text, 저장건수


# ============================================================
# 헬퍼: 검사처방 시행완료 자동 매칭
# ============================================================
def _검사처방_시행완료_매칭(환자id, 검사시행일, 검사항목):
    """검사결과 저장 시 매칭되는 미시행 검사처방을 시행여부=1로 업데이트."""
    conn = sqlite3.connect(DB경로)
    try:
        미시행 = conn.execute(
            "SELECT 처방검사id, 검사명 FROM 검사처방 "
            "WHERE 환자id=? AND 시행여부=0 AND 유효여부=1",
            (환자id,)
        ).fetchall()
        for row in 미시행:
            처방검사id, 검사명 = row[0], row[1]
            if 검사항목 in 검사명 or 검사명 in 검사항목:
                conn.execute(
                    "UPDATE 검사처방 SET 시행여부=1 WHERE 처방검사id=?",
                    (처방검사id,)
                )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 차트 수정 함수 (기존 차트분석_저장_전체흐름()과 별개)
# ============================================================
def _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일):
    """free-text 수정 전후를 비교하여 변경사항만 추출한다. 저장하지 않음.
    Returns: dict (변경, 추가, 삭제, 활력징후_변경, 처방요약_변경) 또는 None"""

    시스템_프롬프트 = """당신은 의료 차트 데이터 비교 어시스턴트입니다.
수정 전후의 free-text를 비교하여 변경된 의료 데이터만 추출하세요.
새로운 제안이나 검토 의견은 절대 하지 마세요.
변경/추가/삭제된 데이터만 JSON으로 출력하세요.

JSON 형식:
{
  "변경": [
    {"테이블": "검사결과", "기존": {"검사항목": "HbA1c", "결과값": "9.5"}, "수정후": {"검사항목": "HbA1c", "결과값": "8.5"}, "검사시행일": "260301"}
  ],
  "추가": [
    {"테이블": "검사결과", "데이터": {"검사항목": "TG", "결과값": "150", "단위": "mg/dL", "검사시행일": "260301"}}
  ],
  "삭제": [
    {"테이블": "검사결과", "데이터": {"검사항목": "LDL", "결과값": "160", "검사시행일": "260301"}}
  ],
  "활력징후_변경": {"수축기": 140, "이완기": 88} 또는 null,
  "처방요약_변경": "변경된 처방요약" 또는 null
}
변경이 없는 항목은 빈 배열로.
활력징후_변경, 처방요약_변경은 변경 없으면 null로.
순수 JSON만 출력. 마크다운이나 설명 없이."""

    프롬프트 = f"""[방문일: {방문일}]

[수정 전 free-text]
{기존_free_text}

[수정 후 free-text]
{새_free_text}

위 두 텍스트를 비교하여 변경된 의료 데이터만 추출하세요."""

    # 익명화 처리
    기록 = 환자전체기록조회(환자id)
    if 기록:
        익명기록, 매핑 = api_익명화(기록)
        랜덤id = next((k for k in 매핑 if k.startswith("PT_")), None)
        실제이름 = 매핑.get(랜덤id) if 랜덤id else None
        익명_기존 = 기존_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 기존_free_text
        익명_새 = 새_free_text.replace(실제이름, 랜덤id) if (실제이름 and 랜덤id) else 새_free_text
        익명_프롬프트 = 프롬프트.replace(기존_free_text, 익명_기존).replace(새_free_text, 익명_새)
    else:
        매핑 = {}
        익명_프롬프트 = 프롬프트

    # API 호출
    응답 = _익명화_api호출(시스템_프롬프트, 익명_프롬프트, 매핑)
    매핑 = None  # 매핑 메모리 해제

    if not 응답:
        return None

    변경사항 = _parse_json_response(응답)
    return 변경사항  # 파싱 실패 시 None, 성공 시 dict


def 차트_데이터만_수정(환자id, 방문id, 기존_free_text, 새_free_text, 방문일, 변경사항=None):
    """free-text 수정 시 변경된 데이터만 감지하여 테이블을 업데이트한다.
    AI 제안/검토 의견 없음. 데이터 변경분만 처리.
    변경사항이 이미 있으면 그대로 사용, 없으면 새로 추출.
    Returns: (변경사항_요약, 변경건수)"""

    if 변경사항 is None:
        변경사항 = _변경사항_추출(환자id, 방문id, 기존_free_text, 새_free_text, 방문일)
    if not 변경사항:
        return "변경사항 추출 실패", 0

    변경건수 = 0
    변경요약 = []
    conn = sqlite3.connect(DB경로)

    try:
        # free-text 자체 업데이트
        방문기록_일괄수정(방문id, {"free_text": 새_free_text})

        # 활력징후 변경
        vs = 변경사항.get("활력징후_변경")
        if vs:
            필드 = {k: vs[k] for k in ["수축기", "이완기", "심박수", "키", "몸무게", "BMI"] if vs.get(k) is not None}
            if 필드:
                방문기록_일괄수정(방문id, 필드)
                변경건수 += 1
                변경요약.append(f"활력징후 수정: {필드}")

        # 처방요약 변경
        if 변경사항.get("처방요약_변경"):
            방문기록_일괄수정(방문id, {"처방요약": 변경사항["처방요약_변경"]})
            변경건수 += 1
            변경요약.append("처방요약 수정")

        # 변경된 항목 처리 (기존 무효화 + 새 레코드)
        for 항목 in 변경사항.get("변경", []):
            테이블 = 항목.get("테이블", "")
            기존 = 항목.get("기존", {})
            수정후 = 항목.get("수정후", {})
            시행일 = 항목.get("검사시행일", 방문일)

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 기존.get("검사항목"), 기존.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text 수정' WHERE 검사id=?", (r[0],))
                conn.commit()
                검사결과추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사항목", 기존.get("검사항목")),
                           수정후.get("결과값", ""), 수정후.get("단위", ""), 수정후.get("참고범위", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"검사결과 수정: {기존.get('검사항목')} {기존.get('결과값')} → {수정후.get('결과값')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text 수정' WHERE 진단id=?", (r[0],))
                conn.commit()
                진단추가(환자id, 방문id, 수정후.get("진단명", 기존.get("진단명")),
                        수정후.get("상태", "활성"), 수정후.get("비고", ""), 수정후.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 수정: {기존.get('진단명')} → {수정후.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 기존.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text 수정' WHERE 처방id=?", (r[0],))
                conn.commit()
                처방추가(환자id, 방문id, 수정후.get("약품명", 기존.get("약품명")),
                        수정후.get("성분명", ""), 수정후.get("용량", ""),
                        수정후.get("용법", ""), 수정후.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 수정: {기존.get('약품명')} → {수정후.get('약품명')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 기존.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text 수정' WHERE 영상id=?", (r[0],))
                conn.commit()
                영상검사추가(환자id, 수정후.get("검사시행일", 시행일),
                           수정후.get("검사종류", 기존.get("검사종류")),
                           수정후.get("결과요약", ""), 수정후.get("주요수치", ""),
                           방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 수정: {기존.get('검사종류')}")

        # 추가된 항목 처리
        for 항목 in 변경사항.get("추가", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                검사결과추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사항목"), 데이터.get("결과값", ""),
                           데이터.get("단위", ""), 데이터.get("참고범위", ""),
                           방문id=방문id)
                _검사처방_시행완료_매칭(환자id, 데이터.get("검사시행일", 방문일), 데이터.get("검사항목", ""))
                변경건수 += 1
                변경요약.append(f"검사결과 추가: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                영상검사추가(환자id, 데이터.get("검사시행일", 방문일),
                           데이터.get("검사종류"), 데이터.get("결과요약", ""),
                           데이터.get("주요수치", ""), 방문id=방문id)
                변경건수 += 1
                변경요약.append(f"영상검사 추가: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                진단추가(환자id, 방문id, 데이터.get("진단명"), 데이터.get("상태", "활성"),
                        데이터.get("비고", ""), 데이터.get("표준코드", None))
                변경건수 += 1
                변경요약.append(f"진단 추가: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                처방추가(환자id, 방문id, 데이터.get("약품명"), 데이터.get("성분명", ""),
                        데이터.get("용량", ""), 데이터.get("용법", ""), 데이터.get("일수", 0))
                변경건수 += 1
                변경요약.append(f"처방 추가: {데이터.get('약품명')}")

            elif 테이블 == "추적계획":
                추적계획추가(환자id, 방문id, 데이터.get("예정일", ""), 데이터.get("내용", ""))
                변경건수 += 1
                변경요약.append(f"추적계획 추가: {데이터.get('내용')}")

            elif 테이블 == "검사처방":
                검사처방추가(환자id, 방문id, 데이터.get("검사명", ""), 데이터.get("처방일", ""))
                변경건수 += 1
                변경요약.append(f"검사처방 추가: {데이터.get('검사명')}")

        # 삭제된 항목 처리 (무효화)
        for 항목 in 변경사항.get("삭제", []):
            테이블 = 항목.get("테이블", "")
            데이터 = 항목.get("데이터", {})

            if 테이블 == "검사결과":
                rows = conn.execute(
                    "SELECT 검사id FROM 검사결과 WHERE 환자id=? AND 검사항목=? AND 결과값=? AND 유효여부=1",
                    (환자id, 데이터.get("검사항목"), 데이터.get("결과값"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 검사결과 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 검사id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"검사결과 삭제: {데이터.get('검사항목')} {데이터.get('결과값')}")

            elif 테이블 == "영상검사":
                rows = conn.execute(
                    "SELECT 영상id FROM 영상검사 WHERE 환자id=? AND 검사종류=? AND 유효여부=1",
                    (환자id, 데이터.get("검사종류"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 영상검사 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 영상id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"영상검사 삭제: {데이터.get('검사종류')}")

            elif 테이블 == "진단":
                rows = conn.execute(
                    "SELECT 진단id FROM 진단 WHERE 환자id=? AND 방문id=? AND 진단명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("진단명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 진단 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 진단id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"진단 삭제: {데이터.get('진단명')}")

            elif 테이블 == "처방":
                rows = conn.execute(
                    "SELECT 처방id FROM 처방 WHERE 환자id=? AND 방문id=? AND 약품명=? AND 유효여부=1",
                    (환자id, 방문id, 데이터.get("약품명"))
                ).fetchall()
                for r in rows:
                    conn.execute("UPDATE 처방 SET 유효여부=0, 정정사유='free-text에서 삭제됨' WHERE 처방id=?", (r[0],))
                    변경건수 += 1
                변경요약.append(f"처방 삭제: {데이터.get('약품명')}")

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"업데이트 오류: {e}", 0
    finally:
        conn.close()

    요약텍스트 = "\n".join(변경요약) if 변경요약 else "변경사항 없음"
    return 요약텍스트, 변경건수


def 차트_재분석_저장(환자id, 방문id, 새_free_text, 방문일):
    """free-text 수정 후 AI 재분석. 기존 데이터 무효화 후 재추출/저장.
    Streamlit 호환 (input() 사용 안 함).
    Returns: (extraction_data, 저장건수) or (None, 0)"""

    # 1. 이 방문에 연결된 기존 데이터 전부 무효화
    conn = sqlite3.connect(DB경로)
    try:
        for 테이블 in ["진단", "추적계획", "처방", "검사처방"]:
            conn.execute(
                f"UPDATE {테이블} SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
                (방문id,)
            )
        conn.execute(
            "UPDATE 검사결과 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.execute(
            "UPDATE 영상검사 SET 유효여부=0, 정정사유='재분석에 의한 무효화' WHERE 방문id=? AND 유효여부=1",
            (방문id,)
        )
        conn.commit()
    finally:
        conn.close()

    # 2. free-text 업데이트
    방문기록_일괄수정(방문id, {"free_text": 새_free_text})

    # 3. AI 재분석 (차트분석 함수 직접 호출, input() 없음)
    분석결과 = 차트분석(환자id, 새_free_text, 방문일)
    if not 분석결과:
        return None, 0

    extraction = 분석결과.get("extraction", {})
    if not extraction:
        return None, 0

    # 4. 전체 항목 자동 승인하여 저장
    approved_data = {}
    approved_data["vitals"] = extraction.get("vitals", {})
    approved_data["lifestyle"] = extraction.get("lifestyle", {})
    approved_data["diagnoses"] = [d for d in extraction.get("diagnoses", []) if d.get("구분") != "기존참조"]
    approved_data["lab_results"] = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    approved_data["imaging"] = [i for i in extraction.get("imaging", []) if i.get("구분") != "기존참조"]
    approved_data["prescriptions"] = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    approved_data["tracking"] = [t for t in extraction.get("tracking", []) if t.get("구분") != "기존참조"]
    approved_data["test_orders"] = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    approved_data["prescription_summary"] = extraction.get("prescription_summary", "")
    approved_data["patient_info"] = {k: v for k, v in extraction.get("patient_info", {}).items() if v and v.get("변경유형")}

    저장건수 = 분석결과_저장(환자id, 방문id, 새_free_text, approved_data)
    방문기록_일괄수정(방문id, {"분석완료": 1})

    return extraction, 저장건수
