# RAG 阶段实验

本目录只记录实验方案，不复制 core / rag 的实现。复用根目录 `make preview`、`make test` 和 `scripts/evaluate.py`。

建议先固定 28 条原文和 15 个问题，记录默认参数的完整结果，再依次改变 Chunk、Recall-K、融合方式、精排阈值和 Prompt。每次注明数据版本、模型版本、改变项、失败题与原因。详见 `docs/03-experiments.md`。

不要运行旧目录的 `*_test.py` 作为新项目测试；它们可能连接或修改数据库。未经用户明确同意不接触数据库，不删除目录，不执行 Git/SVN。
