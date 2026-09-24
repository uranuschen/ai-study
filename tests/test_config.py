import os
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_learning.core.config import Settings, load_settings


# 类职责：验证数据库配置优先级和敏感字段隐藏，不读取真实配置或连接数据库。
# 配置加载回归测试。
class SettingsTests(unittest.TestCase):
    # 方法功能：模拟两个配置文件的加载，确认数据库文件优先于原 .env。
    # 输入：模拟环境和配置值；输出：对加载顺序、文件路径及转换结果的断言。
    # 不读取项目真实 .env。
    def test_database_file_priority_and_project_paths(self):
        # 定位期望项目路径。
        root = Path(__file__).resolve().parents[1]
        # 仅用于测试的连接串。
        database_url = "postgresql://test:test-password@localhost:5432/ragdb"

        # 方法功能：代替 dotenv 读取，根据文件名注入模拟变量。
        # 输入：配置文件路径和 override 开关；输出：无返回，只更新隔离的测试环境。
        # 完全替代文件读取。
        def fake_load(path, override=False):
            # 后读文件不得覆盖前面的值。
            self.assertFalse(override)
            # 模拟独立数据库配置。
            if path.name == ".env.db":
                # 先读入数据库文件的值。
                os.environ.setdefault("DATABASE_URL", database_url)
            # 模拟旧 .env 文件。
            else:
                # 不能覆盖前面的数据库目标。
                os.environ.setdefault("DATABASE_URL", "postgresql://unused/old_db")
                # 验证原模型配置继续可用。
                os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
                # 检查数值类型转换。
                os.environ.setdefault("RECALL_K", "25")

        # 隔离真实环境和配置文件。
        with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv", side_effect=fake_load) as loader:
            # 运行真实加载顺序和类型转换。
            settings = load_settings()
        # 数据库文件优先。
        self.assertEqual(settings.database_url, database_url)
        # 旧密钥变量兼容。
        self.assertEqual(settings.llm_api_key, "test-key")
        # 文本转换为整数。
        self.assertEqual(settings.recall_k, 25)
        # 始终加载项目内的两个确定路径。
        self.assertEqual([call.args[0] for call in loader.call_args_list], [root / ".env.db", root / ".env"])

    # 方法功能：确认 IDE 或系统显式配置的 DATABASE_URL 保持最高优先级。
    # 输入：隔离的系统环境；输出：URL 不被配置文件覆盖的断言。
    # 不读取真实配置文件。
    def test_system_environment_has_priority(self):
        # 模拟用户显式环境变量。
        url = "postgresql://test:environment-password@localhost:5432/custom_db"

        # 方法功能：模拟文件提供另一个数据库连接，但遵守不覆盖已有变量的规则。
        # 模拟 dotenv 的默认语义。
        def fake_load(path, override=False):
            # 已有值不受影响。
            os.environ.setdefault("DATABASE_URL", "postgresql://ignored/ragdb")

        # 模拟 IDE 环境。
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=True), patch("dotenv.load_dotenv", side_effect=fake_load):
            # 读取优先级最高的系统值。
            settings = load_settings()
        # 保留显式环境配置。
        self.assertEqual(settings.database_url, url)

    # 方法功能：检查调试打印配置对象时不会显示数据库密码或模型密钥。
    # 输入：包含测试凭证的 Settings；输出：repr 隐藏敏感字段的断言。
    # 防止调试时无意输出凭证。
    def test_repr_hides_credentials(self):
        # 测试数据不用于连接。
        settings = Settings(database_url="postgresql://test:private-password@localhost/ragdb", llm_api_key="private-key")
        # 模拟日志和 IDE 表示。
        text = repr(settings)
        # 隐藏数据库连接串。
        self.assertNotIn("private-password", text)
        # 隐藏模型密钥。
        self.assertNotIn("private-key", text)

    # 方法功能：在线模型默认超时不变，本地模型可以设置更长等待时间。
    def test_llm_timeout(self):
        # 当前在线调用仍使用 60 秒。
        self.assertEqual(Settings().llm_timeout, 60)
        # 本地模型允许更长的等待时间。
        self.assertEqual(Settings(llm_timeout=180).llm_timeout, 180)
        # 非正数超时立即报错。
        with self.assertRaises(ValueError):
            # 不创建无效的调用配置。
            Settings(llm_timeout=0)


# 仅在直接执行文件时运行测试。
if __name__ == "__main__":
    # 使用标准库框架，不访问数据库。
    unittest.main()
