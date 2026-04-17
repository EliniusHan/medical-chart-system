# API 전송용 환자 데이터 익명화 모듈
# 매핑은 메모리에만 존재하며, 파일/DB/API로 절대 저장·전송하지 않음.
import random
import copy
from datetime import datetime


def api_익명화(환자데이터):
    """API 전송 전 환자 데이터를 익명화한다.

    반환: (익명화된 데이터, 매핑딕셔너리)
    매핑은 절대 API로 전송하지 않음!
    """
    매핑 = {}        # {랜덤키: 실제값}  — 복원용
    익명 = copy.deepcopy(환자데이터)

    랜덤id = None    # 이름 치환 ID (free_text 내 이름 치환에 재사용)

    # ── 환자 기본정보 ──
    if "환자" in 익명:
        환자 = 익명["환자"]
        # 메모는 AI로 전송하지 않음 (개인 노트, 익명화 대상 아님)
        환자.pop("메모", None)

        # 이름 → PT_XXXXX
        if 환자.get("이름"):
            랜덤id = f"PT_{random.randint(10000, 99999)}"
            매핑[랜덤id] = 환자["이름"]
            환자["이름"] = 랜덤id

        # 생년월일 → 나이대
        if 환자.get("생년월일"):
            try:
                연도 = int(str(환자["생년월일"])[:4])
                나이 = datetime.now().year - 연도
                나이대 = f"{(나이 // 10) * 10}대"
            except Exception:
                나이대 = "미상"
            매핑["__생년월일__"] = 환자["생년월일"]
            환자["생년월일"] = 나이대

        # 환자id → 랜덤 숫자
        if 환자.get("환자id") is not None:
            랜덤환자id = random.randint(100000, 999999)
            매핑["__환자id__"] = 환자["환자id"]
            매핑[str(랜덤환자id)] = str(환자["환자id"])
            환자["환자id"] = 랜덤환자id

        # 병록번호 → 랜덤 MRN
        if 환자.get("병록번호"):
            랜덤mrn = f"MRN_{random.randint(10000, 99999)}"
            매핑[랜덤mrn] = 환자["병록번호"]
            매핑["__병록번호__"] = 환자["병록번호"]
            환자["병록번호"] = 랜덤mrn

    # ── 방문 기록 free_text, 처방요약 내 이름/병록번호 치환 ──
    if 랜덤id:
        실제이름 = 매핑[랜덤id]
        for 방문 in 익명.get("방문", []):
            if 방문.get("free_text"):
                방문["free_text"] = 방문["free_text"].replace(실제이름, 랜덤id)
            if 방문.get("처방요약"):
                방문["처방요약"] = 방문["처방요약"].replace(실제이름, 랜덤id)

        # 영상검사 결과요약 내 이름 치환
        for 영상 in 익명.get("영상검사", []):
            if 영상.get("결과요약"):
                영상["결과요약"] = 영상["결과요약"].replace(실제이름, 랜덤id)

        # 처방 약품명/용법 내 이름 치환 (이름이 포함된 경우 대비)
        for 처방 in 익명.get("처방", []):
            for 필드 in ["약품명", "성분명", "용법"]:
                if 처방.get(필드):
                    처방[필드] = 처방[필드].replace(실제이름, 랜덤id)

        # 검사처방 검사명 내 이름 치환
        for 검사처방 in 익명.get("검사처방", []):
            if 검사처방.get("검사명"):
                검사처방["검사명"] = 검사처방["검사명"].replace(실제이름, 랜덤id)

    # ── free_text 등 내 병록번호 치환 ──
    if "__병록번호__" in 매핑:
        실제mrn = 매핑["__병록번호__"]
        랜덤mrn = 익명.get("환자", {}).get("병록번호", "")
        if 랜덤mrn:
            for 방문 in 익명.get("방문", []):
                if 방문.get("free_text"):
                    방문["free_text"] = 방문["free_text"].replace(실제mrn, 랜덤mrn)
                if 방문.get("처방요약"):
                    방문["처방요약"] = 방문["처방요약"].replace(실제mrn, 랜덤mrn)
            for 영상 in 익명.get("영상검사", []):
                if 영상.get("결과요약"):
                    영상["결과요약"] = 영상["결과요약"].replace(실제mrn, 랜덤mrn)

    return 익명, 매핑


def api_복원(응답텍스트, 매핑):
    """AI 응답에서 익명 ID를 실제 정보로 복원한다.
    복원 후 매핑은 반드시 None으로 폐기해야 함.
    """
    결과 = 응답텍스트
    for 랜덤id, 실제값 in 매핑.items():
        if 랜덤id.startswith("__"):   # __생년월일__, __환자id__ 등 내부 키 건너뜀
            continue
        결과 = 결과.replace(랜덤id, str(실제값))
    return 결과
