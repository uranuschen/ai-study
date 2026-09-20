java_users = {"Tom", "Jack", "Bob", "Alice"}

python_users = {"Tom", "Bob", "Mike"}

print(java_users)
python_users.add("Jack")
print(java_users&python_users)
print(java_users|python_users)

print(len(java_users|python_users))

print(java_users - python_users)
