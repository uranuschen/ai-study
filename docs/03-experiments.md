# RAG 手动调试与实验

使用 `POST /api/rag/preview` 检查文件加载与父子块切分。`chunk_size`、`chunk_overlap`、`parent_size`、召回数量、精排阈值和 Prompt 仍在现有组件与配置中，调整时保持一次只改一个核心参数。

用户准备好知识库后，通过 `POST /api/rag/ask` 使用相同问题比较答案、实际引用和资料不足时的拒答，不生成运行追踪或成本统计。

`data/evaluation_cases.json` 与 `scripts/evaluate.py` 保留为已学的手动评测资料；脚本默认只预览题目，真实服务评测必须由用户显式开启并运行。当前不再提供 make test 或独立 test 文件。

入口与参数见 [FastAPI](20-fastapi.md)。
