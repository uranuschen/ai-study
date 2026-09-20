from agent import Agent


agent = Agent()


while True:

    question = input("你：")

    if question == "exit":
        break

    answer = agent.run(question)

    print("AI：", answer)




####### 异常 ####### 
from java_exception_analyzer import JavaExceptionAnalyzer


analyzer = JavaExceptionAnalyzer()


error_stack = """
java.lang.NullPointerException
    at com.demo.order.OrderService.createOrder(OrderService.java:52)
    at com.demo.order.OrderController.create(OrderController.java:31)
"""


result = analyzer.analyze(error_stack)


if result:
    print("异常类型：", result.exception_type)
    print("异常位置：", result.location)
    print("根因：", result.root_cause)
    print("解决方案：", result.solutions)
    print("风险等级：", result.risk_level)