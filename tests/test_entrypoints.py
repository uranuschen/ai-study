import unittest
from unittest.mock import Mock, patch
import main_ingest
import main_ask
from agent_learning.core.config import Settings


# 类职责：确认直接运行入口把顶部变量传给正确流程，外部调用全部用替身。
# 不读取真实 .env，也不运行真实入库或问答。
class EntryTests(unittest.TestCase):
    # 方法功能：验证默认入库入口关闭写入，并把文件路径传入主流程。
    # 防止直接 Debug 意外写库。
    def test_ingestion_defaults_to_preview(self):
        # 替代真实入库流程。
        pipeline = Mock()
        # 返回可打印的空结果。
        pipeline.run.return_value = []
        # 使用内存中的默认配置，不读取环境文件。
        settings = Settings()
        # 阻止真实流程调用。
        with patch.object(main_ingest, "load_settings", return_value=settings), patch.object(main_ingest, "build_ingestion_pipeline", return_value=pipeline) as build, patch("builtins.print"):
            # 测试入口参数传递。
            main_ingest.main()
        # 默认必须为预览。
        self.assertFalse(main_ingest.WRITE_TO_DB)
        # 不创建写库对象。
        build.assert_called_once_with(settings, write=False)
        # 路径和开关正确。
        pipeline.run.assert_called_once_with(main_ingest.FILE_PATH, tenant_id=main_ingest.TENANT_ID, write=False)

    # 方法功能：验证问答入口使用文件顶部的问题和权限条件。
    # 不连接数据库或模型。
    def test_question_and_filter_are_passed_to_pipeline(self):
        # 替代真实问答流程。
        pipeline = Mock()
        # 返回可打印的固定内容。
        pipeline.ask.return_value = {"answer": "测试回答"}
        # 替代所有外部入口。
        with patch.object(main_ask, "load_settings", return_value=Settings()), patch.object(main_ask, "build_pipeline", return_value=pipeline), patch("builtins.print"):
            # 只执行参数组装。
            main_ask.main()
        # 检查最终调用参数。
        question, filters = pipeline.ask.call_args.args
        # 问题直接来自顶部变量。
        self.assertEqual(question, main_ask.QUESTION)
        # 租户没有丢失。
        self.assertEqual(filters.tenant_id, main_ask.TENANT_ID)
        # 权限条件没有丢失。
        self.assertEqual(filters.max_security_level, main_ask.SECURITY_LEVEL)


# 支持单独运行离线测试。
if __name__ == "__main__":
    # 使用标准库框架。
    unittest.main()
