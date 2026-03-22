# JSON과 Dictionary 활용해서 저장하기
import json  # JSON 기능 가져오기: json을 쓰려면 그냥 쓸 수 없고 꼭 가져와서 써야 함.
# JSON은 일종의 상용구라고 생각하면 됨. 형식이 지정된 목록임.

# Dictionary 만들기
환자목록 = [
    {"이름": "김철수", "나이": 58, "진단": "고혈압", "수축기": 145, "이완기": 92},
    {"이름": "이영희", "나이": 45, "진단": "당뇨", "수축기": 128, "이완기": 82},
]

# 파일 쓰기 기능
파일 = open("환자데이터.json", "w")  # '환자데이터'라는 json '파일'을 열어서/만들어서 쓸 준비를 해라.
json.dump(환자목록, 파일, ensure_ascii=False, indent=2)  # 환자목록의 서식과 내용을 인식하고 정리해서 '파일'에 저장해라 / 한글 깨짐 방지 / 보기 좋게 정리
파일.close()

print("===File has been successfully saved!===")
print()

# 파일 내용 읽기
파일 = open("환자데이터.json", "r")
불러온목록 = json.load(파일)  # json은 파일.read를 쓰지 않고 json.load 명령을 써야 함.
파일.close()

print("===불러온 환자 데이터===")
for 환자 in 불러온목록:
    print(f"{환자['이름']}/{환자['나이']}세/{환자['진단']}")
