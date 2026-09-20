# 技术决策

## 1. 保留 Python + PostgreSQL + pgvector

旧项目已经使用 BAAI/bge-small-zh-v1.5（512 维）和 BAAI/bge-reranker-base，优先复用已学内容。数据库只保存持久数据，Python 组织检索和模型调用。不引入工作流框架来包裹两条固定流程。

## 2. 原文、JSON、父块和向量分开

`payload` 保存原始 JSON，`metadata` 保存过滤和来源字段，`content` 保存 JSON 指定字段的可读投影。向量属于 `kb_chunks` 子块。父块保留关联，后续可尝试 small-to-big retrieval，本阶段不自动扩大上下文。

## 3. HNSW 与过滤索引

余弦距离使用 `vector_cosine_ops`；查询以 `ORDER BY embedding <=> query LIMIT k` 表达。元数据用 B-tree 与 JSONB / tags GIN 索引。小数据集优化器可能选择顺序扫描，这不代表索引失效。

HNSW 的过滤可能在近似扫描后减少结果，本实现设置事务内 `hnsw.ef_search=100`。pgvector 0.8+ 可进一步使用 iterative scan，但没有假定用户 Docker 中的扩展版本而默认开启。来源：[pgvector 官方说明](https://github.com/pgvector/pgvector#filtering)。

## 4. Python 中文 BM25

沿用 old/hybird_test.py 的 jieba 分词与 rank_bm25.BM25Okapi：先分词，创建索引，再调用 get_scores()。不再自己展开 BM25 公式。SQL 先应用权限过滤，再对授权的小语料评分。小语料的 BM25 原始分数可能为零或负数，因此依据是否实际命中查询词保留结果，不能简单丢掉所有非正分。

没有把 PostgreSQL `ts_rank` 叫做 BM25，也没有为并未使用的 SQL 全文路径创建装饰性 tsvector 索引。语料达到上限后明确报错，不先取向量 Top-K 再在这几条里做“关键词召回”。规模扩大后再选支持中文分析器的独立关键词索引。

## 5. 默认 RRF，可切换线性融合

RRF 使用一基排名，`sum(1/(60+rank))`，适合两路分数尺度不同。线性融合沿用旧代码的 min-max 归一化；仅一个命中或所有命中同分时统一记为 1，再计算 `alpha * vector + (1-alpha) * bm25`，缺失一路贡献为 0。两者都是排名分，不是答案置信度。先按 chunk ID 合并，不能跨文档仅按正文哈希合并而丢失来源。

## 6. 明确精排分数及拒答边界

CrossEncoder 真正对原问题与每个候选成对打分，直接使用旧环境 sentence-transformers 3.x 的构造参数配置 Sigmoid，不再动态检查模型参数名。Sigmoid 分数也不是已校准的正确率。参考：[Sentence Transformers CrossEncoder 文档](https://www.sbert.net/docs/package_reference/cross_encoder/model.html)。

低分或空证据不调用 LLM；模型明确报告不可回答时拒答；结构和引用非法也拒答。LLM 的事实判断仍然可能有误，当前校验只保证结构和引用边界，不声称已经证明每个事实都由证据蕴含。

## 7. 显式过滤优先

租户、最大安全等级和业务 / 标签过滤来自调用者。意图识别用于解释查询，不据此强制模块过滤，避免把跨部门问题错误缩小。实体编号可增加精确过滤，但不能覆盖可信租户和权限。自动打标与父标签递归展开暂不实现。

## 8. 数据库与文件操作边界

SQL 只交付文本；程序不会在启动时自动建表。导入默认预览，由用户在 main_ingest.py 中显式设定 `WRITE_TO_DB=True` 才写库。问答使用只读事务。没有 DROP、TRUNCATE、DELETE 数据库流程，没有目录清理命令，没有 Git/SVN 操作。学习项目暂不加入自动部署或 CI 数据库任务。


## 9. 按已学内容简化实现

使用普通类、字典、列表和明确的函数调用。移除 Protocol、dataclass、反射配置、自定义连接上下文和 argparse。入口参数直接写在 main_ingest.py / main_ask.py 顶部。数据库表和三个 SQL 文件不变，必要的父子关联、版本检查和向量维度约束继续遵守。
