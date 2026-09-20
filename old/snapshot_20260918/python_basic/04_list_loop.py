f=["a","b","c"]
for item in f:
    if item=="b":
        print(f"水果：{item}")

source=[85, 92, 67, 78, 96]
for s in source:
    print(f"成绩：{s}")

for s in source:
    if s>=90:
        print(f"优秀：{s}")

total=0
for s in source:
    total+=s

print(total)