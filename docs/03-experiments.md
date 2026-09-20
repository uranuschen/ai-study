# 实验索引与验收

当前实验说明位于 `experiments/004_rag/README.md`，不为尚未学习的 Agent 建空框架。

## 离线回归

```bash
make test
make preview
PYTHONPATH=src .venv/bin/python -B scripts/evaluate.py
```

测试覆盖字符切分与原文偏移、JSON 投影、向量有效性、预览不调用外部依赖、BM25 数学公式、双路融合、参数化权限过滤、来源与预算、非法引用拒答和端到端组件组合。数据库、Embedding、CrossEncoder、LLM 等外部依赖使用替身或不调用。测试只收集 `tests/`，不执行旧目录的实验脚本。

## 用户初始化后的真实验收

先由用户将 scripts/evaluate.py 顶部的 RUN_LIVE 改为 True；默认 False 只显示题目。无需 --live 命令行参数。

```bash
# 仅用户手动执行；会查询数据库、加载模型并调用 LLM。
PYTHONPATH=src .venv/bin/python -B scripts/evaluate.py
```

固定 15 题保存在 `data/evaluation_cases.json`，涵盖新旧版本、同题跨租户、相同订单号隔离、退款实体、错误码、数值边界、多标签 AND、机密资料禁止与允许、未知实体和知识缺失。

输出逐题 status / required_terms / forbidden_terms / source_hit 检查结果。`source_hit` 表示最终引用命中期望文档之一，不等同于 Recall@K；关键词断言可能因等价表述失败，应人工复核。当前没有把“多个正确来源都找齐”当作已实现的多跳检索能力。

## 调参记录

| 实验 | 唯一改变项 | 观察内容 |
|---|---|---|
| C1 | CHUNK_SIZE 250 / 400 / 600 | 规则条件是否被切断，具体金额所在块是否召回 |
| C2 | CHUNK_OVERLAP 40 / 80 / 120 | 父子块边界与重叠冗余 |
| K1 | RECALL_K 10 / 20 / 40 | 候选命中与精排时间 |
| K2 | TOP_K 3 / 5 / 8（不超过 CANDIDATE_K） | 正确引用率、答案噪声与长度 |
| F1 | FUSION rrf / linear | 实体编号与同义问题两类结果 |
| F2 | VECTOR_WEIGHT 0 / 0.5 / 1，仅 linear | 关键词与语义贡献 |
| R1 | MIN_RERANK_SCORE 0.2 / 0.35 / 0.5 | 应答正确与错误拒答的平衡 |
| P1 | Prompt 证据和引用要求 | 未覆盖问题是否拒答，是否编造金额 |

Chunk 或 Embedding 参数变化需要给导入记录提升 version，不能沿用 ready 文档的旧向量。评测时记录模型名、参数、用例版本和运行日期；不要用 RRF 分数直接当拒答概率。

建议后续增加人工标注 chunk ID 的 Recall@K、MRR 和引用事实一致性评测，本阶段先把失败案例记录准确。

限制：未获同意不接触数据库，不删除目录，不执行 Git/SVN。
