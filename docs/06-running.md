# 运行与调试

统一启动命令：

```bash
.venv/bin/python -B main_api.py
```

接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。IDE 解释器选择项目的 `.venv/bin/python`，直接 Run / Debug 根目录 `main_api.py`。

启动只创建普通服务对象与图，不建表、不执行入库、不访问数据库或模型。资料预览和基础课程接口可离线运行；问答会访问已有知识库和模型，入库接口会向已有表写入。实际写入只由调用方显式发起。

API 参数示例位于每个接口上方的中文注释，完整操作见 [FastAPI 调用与断点](20-fastapi.md)。

保留三个手动脚本：`main_ingest.py` 默认只预览；`main_ask.py` 执行独立 RAG；`main_workflow.py` 是和 API 共用 Service 的简短 Console。原来的五个逐课 Console 入口已合并，核心图仍在 `src/agent_learning/workflows/`。

从 API 方法进入 Service，再进入核心方法即可调试。应用不生成执行日志、用量、费用或耗时统计。相关测试文件已移除，验证采用临时离线核查，不自动访问真实数据库或 LLM。
