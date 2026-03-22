import json
import os

DB경로 = os.path.join(os.path.dirname(__file__), "환자DB.json")

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

def 환자브리핑(환자):
    print(f" 이름: {환자['이름']}")
    print(f" 나이: {환자['나이']}")
    print(f" 진단: {환자['진단']}")
    print(f" 혈압: {환자['수축기']} / {환자['이완기']} mmHg")
    print(f" 판정: {혈압판정(환자['수축기'], 환자['이완기'])}")
    print("")

def 저장하기(환자목록):
    파일 = open(DB경로, "w")
    json.dump(환자목록, 파일, ensure_ascii=False, indent=2)
    파일.close()
    print("-> 저장완료!")

def 불러오기():
    try:
        if os.path.exists(DB경로):
            파일 = open(DB경로, "r")
            환자목록 = json.load(파일)
            파일.close()
            print(f"-> 기존 데이터 {len(환자목록)}명 불러옴!")
            return 환자목록
        else:
            print("-> 기존 데이터 없음. 새로 시작합니다.")
            return []
    except json.JSONDecodeError:
        print("데이터 파일이 손상되었습니다. 새로 시작합니다.")
        return []

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

def 통계보기(환자목록):
    if len(환자목록) == 0:
        print("등록된 환자가 없습니다.")
        return

    전체환자수 = len(환자목록)
    평균나이 = sum(환자["나이"] for 환자 in 환자목록) / 전체환자수

    진단별 = {}
    for 환자 in 환자목록:
        진단 = 환자["진단"]
        진단별[진단] = 진단별.get(진단, 0) + 1

    고혈압환자수 = sum(
        1 for 환자 in 환자목록
        if 혈압판정(환자["수축기"], 환자["이완기"]) != "정상 혈압"
    )
    고혈압비율 = 고혈압환자수 / 전체환자수 * 100

    print("\n=== 통계 ===")
    print(f" 전체 환자 수: {전체환자수}명")
    print(f" 평균 나이: {평균나이:.1f}세")
    print("\n [진단별 환자 수]")
    for 진단, 수 in 진단별.items():
        print(f"  {진단}: {수}명")
    print(f"\n 고혈압 비율 (정상 혈압 제외): {고혈압환자수}명 / {전체환자수}명 ({고혈압비율:.1f}%)")
    print("")
