students = [
    {"name": "Tom", "score": 85},
    {"name": "Jack", "score": 92},
    {"name": "Alice", "score": 76},
    {"name": "Bob", "score": 58}
]

total=0
for stu in students:
    print(f"名字：{stu['name']} 成绩：{stu['score']}")
    total+=stu["score"]

print(total)
print(total/len(students))

for stu in students:
    if stu["score"]>=90:
        print(f"{stu['name']} 优秀")
    if stu["score"]< 60:
        print(f"{stu['name']} 不及格")
