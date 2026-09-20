# 数据库名称、表位置与账号配置

## 账号密码改哪里

修改项目根目录 **`.env.db`**。已按用户提供的旧 `DB_CONFIG` 填入本地学习配置：

```dotenv
DATABASE_URL=postgresql://rag:rag123456@localhost:5432/ragdb
```

| URL 部分 | 对应旧 DB_CONFIG | 当前值 |
|---|---|---|
| 主机 | host | localhost |
| 端口 | port | 5432 |
| 数据库 | database | ragdb |
| 用户 | user | rag |
| 密码 | password | 用户提供的旧本地学习密码，保存在 `.env.db` |

这里只集中保存连接配置，没有更改数据库服务端账号或密码，也没有连接数据库。用户若曾修改服务端口令，需要同步调整此文件。已有 `.env` 未读取或改写；该文件继续用于 LLM 密钥与模型参数。

## rag_learning 和 ragdb 不是同一种名称

截图层级应理解为：

```text
docker-ragdb                 数据库工具里的连接显示名
└── ragdb                    PostgreSQL 数据库名
    └── public               schema：数据库内存放表的命名空间
        ├── kb_documents     新版原文表
        ├── kb_parent_chunks 父块表
        ├── kb_chunks        子块和向量表
        ├── kb_tag_dimensions 标签维度表
        ├── kb_tags          标签字典与父子标签
        └── kb_document_tags 文档标签关联表
```

上一版 `rag_learning.kb_documents` 表示“rag_learning schema 下的 kb_documents 表”，并没有创建一个名为 rag_learning 的数据库。现在代码与 SQL 已统一改为 `public.kb_documents` 等 public 下的表。

旧截图里的 `public.kb_documents` 与新版原文表同名、结构不同。按你原来的计划自行处理旧表后，再执行新建表 SQL 和初始化 SQL。脚本不负责删除旧表，也不负责迁移已建立的 rag_learning schema 或其中的数据。

## 配置怎样进入数据库连接

```text
根目录 .env.db 的 DATABASE_URL
  → load_settings()
  → cli.py 创建 PostgresRepository(settings.database_url, ...)
  → PostgresRepository.get_connection()
  → psycopg2.connect(...)
```

`load_settings()` 加载顺序为系统 / IDE 环境变量、`.env.db`、`.env`，优先使用先出现的值。如果改 `.env.db` 后仍连接旧地址，先检查 IDE 是否单独设置了 `DATABASE_URL`。配置对象打印时隐藏数据库 URL 与 LLM 密钥。

改配置和创建仓储对象本身不连接数据库。入库默认预览，只有用户在 main_ingest.py 中设置 `WRITE_TO_DB=True` 并运行才写入；问答由用户运行 main_ask.py 后使用只读事务查询。

## 类和方法说明

新源码中的每个类已标明“类职责”，方法已标明“方法功能”；核心方法补充输入和输出说明。原有逐语句中文注释保留。建议先读 `IngestionPipeline.run()` 和 `RAGPipeline.ask()`，再单步进入各个组件。

协作限制仍然有效：未经用户明确同意，不操作数据库、不删除目录，不能执行任何 Git/SVN 操作。
