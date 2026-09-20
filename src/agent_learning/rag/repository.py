import json
from uuid import NAMESPACE_URL, uuid5
from agent_learning.core.models import Hit, SearchFilter
from agent_learning.core.providers import validate_vectors
from agent_learning.rag.ingestion import document_hash


# 方法功能：对业务键稳定编码，生成重复执行不变的 UUID。
# 输入：组成业务标识的多个值；输出：UUID 字符串。
# 业务键生成稳定 UUID，避免重复导入产生新记录。
def stable_id(*parts):
    # JSON 编码消除连接符歧义。
    return str(uuid5(NAMESPACE_URL, json.dumps(parts, ensure_ascii=False)))


# 方法功能：为向量和关键词路径生成相同的权限、版本、标签与实体过滤条件。
# 输入：SearchFilter 和模型名；输出：WHERE 条件字符串与绑定参数列表。
# 两路检索必须复用同一条件构造函数。
def filter_sql(filters, model):
    # 先约束权限与版本。
    clauses = ["d.tenant_id = %s", "c.tenant_id = %s", "d.security_level <= %s", "d.is_latest", "d.index_status = 'ready'", "c.embedding_model = %s"]
    # 所有值均绑定参数。
    parameters = [filters.tenant_id, filters.tenant_id, filters.max_security_level, model]
    # 列名只来自代码白名单。
    for value, column in [(filters.business_module, "d.business_module"), (filters.doc_type, "d.doc_type")]:
        # 可选业务条件。
        if value is not None:
            # 拼接固定列名。
            clauses.append(f"{column} = %s")
            # 用户输入不拼接到 SQL。
            parameters.append(value)
    # 标签要求全部包含。
    if filters.tags:
        # 使用 GIN 支持的包含操作符。
        clauses.append("d.tags @> %s::text[]")
        # 传递数组参数。
        parameters.append(list(filters.tags))
    # 精确查找结构化业务实体。
    if filters.entity_id:
        # 避免正文 LIKE 误命中。
        clauses.append("d.metadata @> %s::jsonb")
        # JSON 数组包含匹配。
        parameters.append(json.dumps({"entity_ids": [filters.entity_id]}))
    # 返回 SQL 模板及参数。
    return " AND ".join(clauses), parameters


# 类职责：封装 PostgreSQL 数据操作，负责事务、幂等入库、标签关联和两路检索的授权数据读取。
# 只在显式调用方法时连接数据库。
class PostgresRepository:
    # 方法功能：保存数据库连接配置和向量维度，构造实例时不连接数据库。
    # 输入：数据库连接 URL 与向量维度；输出：完成初始化的仓储。
    # 导入模块不会建表。
    def __init__(self, database_url, dimension=512):
        # 保存连接参数。
        self.database_url, self.dimension = database_url, dimension

    # 方法功能：创建一个普通数据库连接；调用方在 finally 中关闭。
    # 输入：readonly 是否只读；输出：psycopg2 连接对象。
    # 沿用旧代码 get_connection 的思路。
    def get_connection(self, readonly=True):
        import psycopg2
        # 没有配置就不连接。
        if not self.database_url:
            # 提示配置文件。
            raise ValueError("请在 .env.db 配置 DATABASE_URL")
        # 创建连接。
        connection = psycopg2.connect(self.database_url, connect_timeout=5)
        # 设置连接的读取权限。
        try:
            # 问答默认只读。
            connection.set_session(readonly=readonly)
            # 由调用方执行 SQL 和关闭连接。
            return connection
        # 设置失败时不遗留连接。
        except Exception:
            # 释放已经打开的连接。
            connection.close()
            # 把原错误交给调用者。
            raise

    # 方法功能：校验已有版本，以单文档事务写原文、标签和父子块，最后标记 ready。
    # 输入：文档、父子块、向量、模型名和流水线指纹；输出：indexed 或 unchanged；冲突时抛出异常。
    # 每篇文档及所有子块原子写入。
    def save(self, document, parents, chunks, vectors, model, fingerprint):
        from psycopg2.extras import Json
        # 防止数据库部分写入才发现向量错误。
        validate_vectors(vectors, len(chunks), self.dimension)
        # 稳定版本 ID。
        identifier = stable_id(document.tenant_id, document.external_id, document.version)
        # 对文档完整内容做幂等检测。
        content_hash = document_hash(document)
        # 显式打开连接。
        connection = self.get_connection(readonly=False)
        # 无论 SQL 成功还是失败，最后都关闭连接。
        try:
            # 驱动在成功时提交，异常时回滚。
            with connection:
                # 所有数据共享一个事务。
                with connection.cursor() as cursor:
                    # 串行化同一文档的版本发布。
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (json.dumps([document.tenant_id, document.external_id]),))
                    # 检查已有版本。
                    cursor.execute("SELECT id, content_hash, index_status, pipeline_fingerprint FROM public.kb_documents WHERE tenant_id=%s AND external_id=%s AND version=%s FOR UPDATE", (document.tenant_id, document.external_id, document.version))
                    # 可能是 SQL 初始化的 pending 原文。
                    existing = cursor.fetchone()
                    # 同版本内容或权限发生改变。
                    if existing and existing[1] != content_hash:
                        # 保留历史。
                        raise ValueError("同版本内容不同，请提升 version；不自动覆盖历史资料")
                    # 已完整入库时进行幂等判断。
                    if existing and existing[2] == "ready":
                        # 切分或模型配置变了。
                        if existing[3] != fingerprint:
                            # 防止混用旧块。
                            raise ValueError("切分或模型参数已变化，请提升 version 后重建向量")
                        # 不重复写入。
                        return "unchanged"
                    # 使用初始化 SQL 已生成的 ID。
                    if existing:
                        # 转换 UUID 为文本。
                        identifier = str(existing[0])
                    # 新版本先更新同文档的发布状态。
                    if not existing:
                        # 历史版本导入不改变最新版本。
                        if document.is_latest:
                            # 同事务发布新版本。
                            cursor.execute("UPDATE public.kb_documents SET is_latest=false, updated_at=now() WHERE tenant_id=%s AND external_id=%s AND is_latest", (document.tenant_id, document.external_id))
                        # 保存原文及 JSON。
                        cursor.execute("""INSERT INTO public.kb_documents
                            (id, tenant_id, external_id, title, content, payload, metadata, business_module, doc_type, security_level, version, is_latest, source, tags, content_hash)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (identifier, document.tenant_id, document.external_id, document.title, document.content, Json(document.payload), Json(document.metadata), document.business_module, document.doc_type, document.security_level, document.version, document.is_latest, document.source, document.tags, content_hash))
                    # 同事务维护标签字典关联。
                    for tag in set(document.tags):
                        # 解析明确的标签代码。
                        dimension, code = tag.split(":", 1)
                        # 只使用已存在的标签字典。
                        cursor.execute("SELECT id FROM public.kb_tags WHERE tenant_id=%s AND dimension_code=%s AND code=%s", (document.tenant_id, dimension, code))
                        # 查找规范标签。
                        row = cursor.fetchone()
                        # 不静默制造未定义标签。
                        if row is None:
                            # 用户先更新字典或使用现有标签。
                            raise ValueError(f"标签字典未注册: {tag}")
                        # 幂等同步关联。
                        cursor.execute("INSERT INTO public.kb_document_tags (document_id, tag_id, tenant_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (identifier, row[0], document.tenant_id))
                    # 保存大粒度父块。
                    for parent in parents:
                        # 不自动删除已有数据。
                        cursor.execute("INSERT INTO public.kb_parent_chunks (id,document_id,tenant_id,parent_index,content,start_char,end_char) VALUES (%s,%s,%s,%s,%s,%s,%s)", (stable_id(identifier, "parent", parent.index), identifier, document.tenant_id, parent.index, parent.content, parent.start, parent.end))
                    # 保存实际检索子块。
                    for chunk, vector in zip(chunks, vectors):
                        # 向量用参数绑定后显式转换。
                        cursor.execute("""INSERT INTO public.kb_chunks
                            (id,document_id,tenant_id,parent_id,chunk_index,content,start_char,end_char,metadata,embedding,embedding_model)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s)""", (stable_id(identifier, "chunk", chunk.index), identifier, document.tenant_id, stable_id(identifier, "parent", chunk.parent_index), chunk.index, chunk.content, chunk.start, chunk.end, Json({"start": chunk.start, "end": chunk.end}), json.dumps(vector), model))
                    # 最后标记为可检索，失败时全部回滚。
                    cursor.execute("UPDATE public.kb_documents SET index_status='ready', pipeline_fingerprint=%s, updated_at=now() WHERE id=%s", (fingerprint, identifier))
        # 像旧代码一样显式释放连接。
        finally:
            # 不遗留连接或事务。
            connection.close()
        # 完整事务成功才返回。
        return "indexed"

    # 方法功能：把数据库字典行转换为检索阶段共用的数据对象。
    # 输入：数据库结果字典；输出：一个 Hit。
    # 将数据库行转换为统一 Hit。
    def _hit(self, row: dict) -> Hit:
        # 数值转换为普通 Python 类型。
        return Hit(id=str(row["id"]), document_id=str(row["document_id"]), content=row["content"], title=row["title"], source=row["source"], metadata=row["metadata"], vector_score=float(row.get("vector_score", 0)))

    # 方法功能：返回两路查询共用的投影字段，统一合并文档来源与子块位置。
    # 输入：无额外参数；输出：固定 SELECT SQL 片段。
    # 两路查询共享来源字段。
    def _select(self):
        # 子块偏移覆盖原文同名字段。
        # ||是合并的语法 多个json合并成一个
        return "SELECT c.id,c.document_id,c.content,d.title,d.source,d.metadata || c.metadata || jsonb_build_object('version',d.version) AS metadata"

    # 方法功能：在权限和元数据条件内执行 pgvector 余弦距离 Top-K 查询。
    # 输入：查询向量、过滤器、模型名和 K；输出：按距离排序的 Hit 列表。
    # 数据库余弦距离检索。
    def vector_search(self, vector: list[float], filters: SearchFilter, model: str, k: int) -> list[Hit]:
        from psycopg2.extras import RealDictCursor
        # 校验查询向量。
        validate_vectors([vector], 1, self.dimension)
        # 与关键词语料一致的过滤条件。
        # 拼接条件，where是语句，parameters是具体的值
        where, parameters = filter_sql(filters, model)
        # 参数化向量字符串。
        encoded = json.dumps(vector)
        # 距离表达式保持升序以匹配索引。
        sql = self._select() + ",1-(c.embedding <=> %s::vector) AS vector_score FROM public.kb_chunks c JOIN public.kb_documents d ON d.id=c.document_id WHERE " + where + " ORDER BY c.embedding <=> %s::vector LIMIT %s"
        # 显式打开连接。
        connection = self.get_connection(readonly=True)
        # 无论 SQL 成功还是失败，最后都关闭连接。
        try:
            # 驱动在成功时提交，异常时回滚。
            with connection:
                # 直接使用列名。
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    # 提高过滤场景的候选搜索量。
                    # HNSW 是向量的近似检索。ef_search默认是40
                    # LOCAL是当前事务，事务关闭会还原成默认值40
                    # ef_search这里的意思是召回数：比如召唤附近100条记录。这里值越大越准，但是消耗越大。
                    cursor.execute("SET LOCAL hnsw.ef_search = 100")
                    # 绑定全部动态值。
                    # 4个参数对应 第一个对应拼接sql里的cos的向量，第二个是where后的参数，第三个是order by后的向量，k是limit
                    # *parameters 这里的* 解包，把参数列出来。如果和%参数个数不一致，会报错。
                    cursor.execute(sql, [encoded, *parameters, encoded, k])
                    # 返回统一召回结果。 这里是游标查到多行数据，就放到hit里，是一个对象，就是多个hit
                    return [self._hit(row) for row in cursor.fetchall()]

        # 像旧代码一样显式释放连接。
        finally:
            # 不遗留连接或事务。
            connection.close()
    # 方法功能：读取与向量查询相同授权范围的全部小语料，供 Python 计算 BM25。
    # 输入：过滤器、模型名和语料上限；输出：Hit 语料列表；超出上限明确报错。
    # 为小规模中文 BM25 提供完整过滤语料。
    def lexical_corpus(self, filters: SearchFilter, model: str, limit: int) -> list[Hit]:
        from psycopg2.extras import RealDictCursor
        # 严格复用权限、实体、版本过滤。
        where, parameters = filter_sql(filters, model)
        # 多取一条用于检测超限。
        sql = self._select() + " FROM public.kb_chunks c JOIN public.kb_documents d ON d.id=c.document_id WHERE " + where + " ORDER BY c.id LIMIT %s"
        # 显式打开连接。
        connection = self.get_connection(readonly=True)
        # 无论 SQL 成功还是失败，最后都关闭连接。
        try:
            # 驱动在成功时提交，异常时回滚。
            with connection:
                # 按名称读取字段。
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    # 不静默截断 BM25 语料。
                    cursor.execute(sql, [*parameters, limit + 1])
                    # 获取过滤后的记录。
                    rows = cursor.fetchall()
        # 像旧代码一样显式释放连接。
        finally:
            # 不遗留连接或事务。
            connection.close()
        # 显式报告内存版容量限制。
        if len(rows) > limit:
            # 不悄悄降低召回率。
            raise ValueError("BM25 过滤后语料超过上限，请缩小过滤范围或改用独立关键词索引")
        # BM25 只看授权语料。
        return [self._hit(row) for row in rows]
