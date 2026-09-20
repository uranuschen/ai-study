stu ={
    "name":"tom",
    "age":18,
    "source":85
}

print(stu)
print(stu["name"])
print(stu["age"])

stu["source"]=95
print(stu["source"])
stu["city"]="ShangHai"
stu.pop("age")
print(stu)

if stu["source"]>=90:
    print("tom成绩优秀")
else:
     print("tom继续加油")