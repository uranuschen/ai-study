import json
import sys
from pathlib import Path

# 当前项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# 让直接运行的脚本可以找到 src 中的共用代码。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.core.config import load_settings
from agent_learning.core.models import SearchFilter
from agent_learning.cli import build_pipeline


# 直接在这里修改问题。
QUESTION = "A1002 的退款到账了吗？"
# 当前用户的租户；不能从问题文字中改变。
TENANT_ID = "acme"
# 当前用户可以读取的最高资料级别。
SECURITY_LEVEL = 1
# None 不限制模块；只查财务时改为 "finance"。
BUSINESS_MODULE = None
# None 不限制文档类型；只查制度时改为 "policy"。
DOC_TYPE = None
# 可填写已有标签，如 ["module:finance-travel", "region:cn"]。
TAGS = []
# False 使用现有 DeepSeek；True 使用本机 Ollama。
USE_OLLAMA = False
# 本机已经安装的 Qwen 8B Q4 模型名称；也可改回 "deepseek-r1:7b"。
OLLAMA_MODEL = "qwen3:8b"


# 方法功能：准备查询条件，调用完整问答流程，输出答案和来源。
# 输入：上方问题和过滤条件；输出：答案、引用及各步骤统计。
# 可以在这个方法第一行打断点。
def main():
    # 读取数据库和现有在线模型配置。
    settings = load_settings()
    # 用户打开本地模型开关时，只替换回答模型的连接参数。
    if USE_OLLAMA:
        # Ollama 提供兼容 OpenAI 的本地接口。
        settings.llm_base_url = "http://127.0.0.1:11434/v1"
        # 使用本机已安装的模型名称。
        settings.llm_model = OLLAMA_MODEL
        # OpenAI 客户端需要非空值；本地 Ollama 不校验这个占位值。
        settings.llm_api_key = "ollama"
        # 本地模型首次加载可能超过在线接口的超时时间。
        settings.llm_timeout = 180
    # 把用户身份和查询范围放在一起。
    filters = SearchFilter(
        # 指定租户。
        tenant_id=TENANT_ID,
        # 指定可读取的资料级别。
        max_security_level=SECURITY_LEVEL,
        # 可选业务模块。
        business_module=BUSINESS_MODULE,
        # 可选资料类型。
        doc_type=DOC_TYPE,
        # 可选标签，多个标签要求同时满足。
        tags=TAGS,
    )
    # 准备检索、精排、上下文和模型调用对象。
    pipeline = build_pipeline(settings)
    # 从问题开始，按顺序执行到最终回答。
    result = pipeline.ask(QUESTION, filters)
    # 打印回答以及引用的原文。
    print(json.dumps(result, ensure_ascii=False, indent=2))


# 点击 IDE 的 Run 或 Debug 时执行。
if __name__ == "__main__":
    # 实际问答会只读查询数据库，并调用模型。
    main()
