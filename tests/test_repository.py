import json
import unittest
from unittest.mock import MagicMock, patch
from agent_learning.core.models import Document, SearchFilter
from agent_learning.rag.chunking import DocumentChunker
from agent_learning.rag.ingestion import document_hash
from agent_learning.rag.repository import PostgresRepository, stable_id


# 类职责：全部使用游标替身，不连接数据库。
# 全部使用游标替身，不连接数据库。
class RepositoryTests(unittest.TestCase):
    # 方法功能：每题使用独立游标记录。
    # 每题使用独立游标记录。
    def setUp(self):
        # 测试不会使用此连接字符串。
        self.repository = PostgresRepository("unused")
        # 捕获 SQL 及绑定参数。
        self.cursor = MagicMock()
        # 模拟数据库连接。
        self.connection = MagicMock()
        # 返回同一游标。
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        # 替换获取连接的方法。
        self.context = MagicMock(return_value=self.connection)
        # 注入假连接。
        self.repository.get_connection = self.context
        # 创建最小文档。
        self.document = Document("X", "标题", "订单说明")
        # 真实切分。
        self.parents, self.chunks = DocumentChunker().split(self.document.content)
        # 仅用于代码测试的合成非零向量，不写真实库。
        self.vectors = [[1.0] + [0.0] * 511]

    # 方法功能：统一调用真实仓储逻辑。
    # 统一调用真实仓储逻辑。
    def save(self):
        # 不模拟被测方法本身。
        return self.repository.save(self.document, self.parents, self.chunks, self.vectors, "test-model", "pipeline-v1")

    # 方法功能：验证列与参数数量及标记顺序。
    # 验证列与参数数量及标记顺序。
    def test_new_version_writes_complete_document(self):
        # 当前版本尚不存在。
        self.cursor.fetchone.return_value = None
        # 应保存完整文档。
        self.assertEqual(self.save(), "indexed")
        # 读取实际发出的 SQL。
        calls = self.cursor.execute.call_args_list
        # 检查所有动态参数占位。
        for call in calls:
            # 所有保存语句都携带参数。
            sql, parameters = call.args
            # 防止列 / 参数数量不匹配。
            self.assertEqual(sql.count("%s"), len(parameters))
        # 单独检查事务内语句。
        statements = [call.args[0] for call in calls]
        # 父块已保存。
        self.assertTrue(any("INSERT INTO public.kb_parent_chunks" in sql for sql in statements))
        # 子块已保存。
        self.assertTrue(any("INSERT INTO public.kb_chunks" in sql for sql in statements))
        # 必须最后才标记可查询。
        self.assertIn("index_status='ready'", statements[-1])
        # 只有保存使用可写事务。
        self.context.assert_called_once_with(readonly=False)

    # 方法功能：重复导入不能产生第二套块。
    # 重复导入不能产生第二套块。
    def test_repeat_same_version_is_idempotent(self):
        # 模拟已索引原文。
        self.cursor.fetchone.return_value = ("id", document_hash(self.document), "ready", "pipeline-v1")
        # 明确返回未改变。
        self.assertEqual(self.save(), "unchanged")
        # 收集 SQL。
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        # FOR UPDATE 行锁不等同于更新数据。
        self.assertFalse(any(sql.lstrip().startswith(("INSERT", "UPDATE")) for sql in statements))

    # 方法功能：避免同版本静默覆盖或混用旧向量。
    # 避免同版本静默覆盖或混用旧向量。
    def test_content_and_pipeline_changes_rejected(self):
        # 两种变化。
        for record in [("id", "different-hash", "ready", "pipeline-v1"), ("id", document_hash(self.document), "ready", "old-pipeline")]:
            # 注入已有版本。
            self.cursor.fetchone.return_value = record
            # 要求用户提升版本。
            with self.assertRaises(ValueError):
                # 运行幂等检查。
                self.save()

    # 方法功能：SQL 初始化原文需要由入库流程补齐向量。
    # SQL 初始化原文需要由入库流程补齐向量。
    def test_pending_seed_gets_real_chunks(self):
        # 模拟初始化后的状态。
        self.cursor.fetchone.return_value = (stable_id("acme", "X", "1.0"), document_hash(self.document), "pending", None)
        # 补齐已有原文。
        self.assertEqual(self.save(), "indexed")
        # 检查写入。
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        # 不重复插入父文档。
        self.assertFalse(any("INSERT INTO public.kb_documents" in sql for sql in statements))
        # 真实向量位置被写入。
        self.assertTrue(any("INSERT INTO public.kb_chunks" in sql for sql in statements))

    # 方法功能：保持冗余字段与字典关联一致。
    # 保持冗余字段与字典关联一致。
    def test_missing_tag_fails_before_chunk_writes(self):
        # 字典中不存在的标签。
        self.document.tags = ["module:unknown"]
        # 原文与标签均不存在。
        self.cursor.fetchone.return_value = None
        # 不自动制造标签。
        with self.assertRaisesRegex(ValueError, "标签字典未注册"):
            # 在事务内部明确失败。
            self.save()
        # 收集到失败位置为止的 SQL。
        statements = [call.args[0] for call in self.cursor.execute.call_args_list]
        # 失败前未写子块。
        self.assertFalse(any("INSERT INTO public.kb_chunks" in sql for sql in statements))

    # 方法功能：BM25 不能悄悄只看任意前几行。
    # BM25 不能悄悄只看任意前几行。
    def test_keyword_limit_fails_instead_of_truncating(self):
        # 返回上限之外的一条记录。
        self.cursor.fetchall.return_value = [{}, {}, {}]
        # 明确报告扩容需求。
        with self.assertRaisesRegex(ValueError, "超过上限"):
            # 模拟超限查询。
            self.repository.lexical_corpus(SearchFilter("acme"), "test-model", 2)

    # 方法功能：确保向量索引表达式和权限同时存在。
    # 确保向量索引表达式和权限同时存在。
    def test_query_sql_keeps_index_order_and_scope(self):
        # 模拟没有命中。
        self.cursor.fetchall.return_value = []
        # 真实 SQL 构造。
        self.repository.vector_search(self.vectors[0], SearchFilter("acme", tags=("module:finance",)), "test-model", 5)
        # 读取最后一次查询。
        sql, parameters = self.cursor.execute.call_args.args
        # 升序余弦距离可使用 HNSW。
        self.assertIn("ORDER BY c.embedding <=> %s::vector LIMIT %s", sql)
        # 不召回历史版本。
        self.assertIn("d.is_latest", sql)
        # 绑定数量一致。
        self.assertEqual(sql.count("%s"), len(parameters))
        # 查询向量未被改变。
        self.assertEqual(json.loads(parameters[0]), self.vectors[0])


# 类职责：测试普通连接的只读设置、异常传播和 finally 关闭。
# 全部使用替身，不连接真实数据库。
class ConnectionTests(unittest.TestCase):
    # 方法功能：异常必须传播并关闭连接。
    # 异常必须传播并关闭连接。
    def test_readonly_and_close_on_failure(self):
        # 替换数据库驱动创建的连接。
        connection = MagicMock()
        # 阻止真实数据库连接。
        with patch("psycopg2.connect", return_value=connection) as connect:
            # 创建被测仓储。
            repository = PostgresRepository("unused")
            # 保留原异常。
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                # 模拟执行 SQL 时失败。
                connection.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("test failure")
                # 检查真实查询方法的资源释放。
                repository.lexical_corpus(SearchFilter("acme"), "test-model", 10)
        # 问答默认只读。
        connection.set_session.assert_called_once_with(readonly=True)
        # 异常时仍关闭连接。
        connection.close.assert_called_once()
        # 异常交给事务上下文触发驱动回滚。
        self.assertIs(connection.__exit__.call_args.args[0], RuntimeError)


# 可单独运行测试。
if __name__ == "__main__":
    # 使用标准库框架。
    unittest.main()
