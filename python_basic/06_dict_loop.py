student = {
    "name": "Tom",
    "age": 30,
    "score": 95,
    "city": "Shanghai"
}

for key,value in student.items():
    print(f"{key}={value}")
    if key=="score":
        print(f"发现成绩：{value}")
  