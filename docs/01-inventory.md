# 旧文件与旧表盘点

本次没有连接数据库。表判断依据用户截图与本地代码，不能据此断言真实数据库行数、约束或额外字段。

## 旧代码

| 旧位置 | 发现的问题 | 新位置 |
|---|---|---|
| python_basic/rag/db.py 及多个脚本 | 硬编码连接配置，多个独立连接入口 | core/config.py、rag/repository.py |
| document_ingest_pipeline.py | 加载、切分、建表、删除旧记录和写入聚集在同一脚本 | loaders.py、chunking.py、ingestion.py、独立 SQL |
| prefilter_test.py | embed_passages 重复定义，示例数据与查询混在一起 | providers.py、SearchFilter、repository.py |
| hybird_test.py | 固定内存数据，未与实际库的混合问答集成 | retrieval.py 的独立 BM25、融合和混合召回 |
| vector_search_test.py | 加载模型、连接数据库、问答循环在顶层执行 | 延迟加载模型、显式 CLI、RAGPipeline |
| document_loader_* / chunk_* | 多种临时实验重复实现加载或切分 | DocumentLoader、DocumentChunker |
| python_basic/llm | API、消息、记忆等阶段练习 | 复用 LLM 兼容接口；Memory 留在历史代码 |
| python_basic/toolcalling / order_* | 早期 Python / Tool Calling 学习成果 | 原样保留，当前不迁移到 RAG 运行路径 |

## 备份方式

`old/snapshot_20260918/` 保存 70 个原始文件，含 `python_basic/`、`rag/`、原 requirements 和原 .gitignore。`manifest.json` 记录逐文件 SHA-256，创建时已校验副本。排除了缓存和 `.DS_Store`。`.env`、`.venv`、密钥没有复制。课程 Excel 保持原位。

采用复制备份，原目录没有移动或删除，因此便于对照。新代码、测试、入口均只指向 `src/`，不要再执行旧 `*_test.py` 来验证新系统：部分旧文件在导入或运行时会直接访问数据库。

## 旧表状态

| 截图中的旧表 | 处理建议 | 新结构对应 |
|---|---|---|
| public.documents | **停用候选**：只有 id / content / embedding，无法完整表达租户和来源 | kb_documents + kb_chunks |
| public.rag_documents | **停用候选**：有 source / metadata，但缺乏统一版本与父子块 | kb_documents + kb_parent_chunks + kb_chunks |
| public.kb_documents | **旧结构停用候选**：保留其租户、业务、版本等设计思想，原文与块需要拆开；与新表同名 | 重建后的 public.kb_documents 与关联子表 |

新表现已按用户现有目录统一放在 `ragdb` 数据库的 `public` schema。旧 `documents`、`rag_documents` 不参与新流程；旧 `kb_documents` 与新版原文表同名但字段结构不同，必须由用户自行处理旧表后再执行建表文件，不能直接复用旧结构。项目没有生成 DROP 脚本，也未执行删除。之前的 `rag_learning` 只是 schema 名，不是数据库名；本次只修改文件，不自动搬迁已存在的数据库对象。

协作限制：未经用户明确同意不接触数据库，不删除目录，不执行 Git/SVN。
