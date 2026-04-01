# Day4-1: 파일에 데이터 저장하고 읽기
# === 파일에 쓰기 (write) ===
# open 기능과 w 명령: open은 지정하는 파일을 열어서 어떤 행동을 할 수 있게 해주는 기능/w는 write(쓰기) 명령
파일 = open("메모.txt", "w")
파일.write("첫 번째 환자: 김철수, 고혈압\n")
파일.write("두 번째 환자: 이영희, 당뇨\n")
파일.close()

print("파일 저장 완료")
print("")

# === 파일 읽기 (read) ===
파일 = open("메모.txt", "r")
내용 = 파일.read()
파일.close()

print("===저장된 내용===")
print(내용)