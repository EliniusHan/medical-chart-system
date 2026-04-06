"""환자DB.db 백업 스크립트.

실행: python backup.py
또는 main_system.py admin 메뉴에서 호출.

- 저장 위치: backup/
- 파일명: 환자DB_백업_YYYYMMDD_HHMMSS.db
- 최근 5개 백업만 유지 (오래된 것 자동 삭제)
"""
import os
import shutil
from datetime import datetime

DB경로    = os.path.join(os.path.dirname(__file__), "환자DB.db")
백업폴더  = os.path.join(os.path.dirname(__file__), "backup")
최대보관수 = 5


def DB백업():
    """DB를 타임스탬프 파일명으로 백업하고, 오래된 백업을 정리한다.
    성공 시 백업 파일 경로, 실패 시 None 반환.
    """
    if not os.path.exists(DB경로):
        print(" ⚠ 백업 대상 DB가 없습니다:", DB경로)
        return None

    os.makedirs(백업폴더, exist_ok=True)

    타임스탬프 = datetime.now().strftime("%Y%m%d_%H%M%S")
    파일명 = f"환자DB_백업_{타임스탬프}.db"
    저장경로 = os.path.join(백업폴더, 파일명)

    shutil.copy2(DB경로, 저장경로)
    print(f" 백업 완료: backup/{파일명}")

    # 오래된 백업 정리 (수정시간 기준 오름차순)
    백업목록 = sorted(
        [f for f in os.listdir(백업폴더) if f.startswith("환자DB_백업_") and f.endswith(".db")],
        key=lambda f: os.path.getmtime(os.path.join(백업폴더, f))
    )
    삭제대상 = 백업목록[:-최대보관수] if len(백업목록) > 최대보관수 else []
    for 파일 in 삭제대상:
        os.remove(os.path.join(백업폴더, 파일))
        print(f" 오래된 백업 삭제: {파일}")

    print(f" 현재 백업 {min(len(백업목록), 최대보관수)}개 유지 중")
    return 저장경로


if __name__ == "__main__":
    DB백업()
