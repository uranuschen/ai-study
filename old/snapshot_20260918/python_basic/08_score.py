scores = [85, 92, 67, 78, 96, 55]

print(len(scores))
total = 0
for s in scores:
    total+=s

print(total)
print(total/len(scores))
print(max(scores))
print(min(scores))

for s in scores:
    if s>=90:
        print(f"优秀{s}")
    elif s>=60:
        print(f"及格{s}")
    elif s<60:
        print(f"不及格{s}")
