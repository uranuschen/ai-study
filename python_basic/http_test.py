import requests

url = "https://abc123456789-test.com"
try:
    response = requests.get(url, timeout=5)
    response.raise_for_status()

    data = response.json()

    print("请求成功")
    print(data)

except requests.exceptions.Timeout:
    print("请求超时")

except requests.exceptions.HTTPError:
    print("HTTP错误")

except requests.exceptions.RequestException as e:
    print("请求异常：", e)