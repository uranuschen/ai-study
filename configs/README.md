# 配置来源

数据库连接使用根目录 `.env.db`，已按用户给出的旧 DB_CONFIG 填写；模型和检索参数以 `.env.example` 为模板，保存在 `.env`。运行时由 `core/config.py 的 load_settings()` 按系统环境 > `.env.db` > `.env` 的顺序读取，已有值不会被后读文件覆盖。

关键参数：CHUNK_SIZE、CHUNK_OVERLAP、PARENT_SIZE、RECALL_K、CANDIDATE_K、TOP_K、FUSION、VECTOR_WEIGHT、MIN_VECTOR_SCORE、MIN_RERANK_SCORE、CONTEXT_CHARS、PER_CHUNK_CHARS、BM25_MAX_CHUNKS。

真实密钥和数据库凭证不放在本目录。数据库账号密码修改位置与数据库 / schema 区别见 `docs/08-db-config.md`。默认 LOCAL_FILES_ONLY=true；预览无需数据库和模型连接。
