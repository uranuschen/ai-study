from agent_learning.workflows import business_tool, conditional_route, single_node, state_flow


# 保留基础课程的独立演示入口。
class LessonService:
    # 小图启动时编译，执行时只传业务输入。
    def __init__(self, tenant_id, data_file):
        # 身份来自服务端。
        self.tenant_id = tenant_id
        # 单节点示例不访问模型。
        self.single_graph = single_node.build_graph()
        # 两节点示例演示 State 传值。
        self.state_graph = state_flow.build_graph()
        # 条件路由示例只调用本地函数。
        self.route_graph = conditional_route.build_graph()
        # 业务 Tool 示例只读 JSON。
        self.business_graph = business_tool.build_graph(data_file)

    # 单节点回显。
    def run_single_node(self, question: str) -> dict:
        # 只挑出回答，不返回内部状态。
        result = self.single_graph.invoke({"question": question})
        # 返回演示结果。
        return {"answer": result["answer"]}

    # 展示前后节点通过 State 传值。
    def run_state_flow(self, question: str) -> dict:
        # 第一个节点清理问题，第二个节点读取它。
        result = self.state_graph.invoke({"question": question})
        # clean_question 是本课要观察的业务中间值。
        return {"clean_question": result["clean_question"], "answer": result["answer"]}

    # 普通输入或统计字数工具分支。
    def run_conditional_route(self, question: str) -> dict:
        # 路由由图中的规则决定。
        result = self.route_graph.invoke({"question": question})
        # 只返回最终回答。
        return {"answer": result["answer"]}

    # 展示工具查询成功与失败时的业务回答。
    def run_business_tool(self, order_id: str) -> dict:
        # 请求不能指定租户或数据路径。
        result = self.business_graph.invoke({"question": order_id, "tenant_id": self.tenant_id})
        # 返回回答和业务查询结果。
        return {"answer": result["answer"], "result": result["tool_result"]}
