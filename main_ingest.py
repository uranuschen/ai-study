import json
import sys
from pathlib import Path

# 当前项目根目录。
BASE_DIR = Path(__file__).resolve().parent
# 让直接运行的脚本可以找到 src 中的共用代码。
sys.path.insert(0, str(BASE_DIR / "src"))

from agent_learning.core.config import load_settings
from agent_learning.cli import build_ingestion_pipeline


# 修改这里，选择需要导入的文件。
FILE_PATH = BASE_DIR / "data" / "enterprise_documents.json"
# 文件没有指定租户时，使用这个默认值。
TENANT_ID = "acme"
# False 只预览；用户准备好表后可改为 True，生成向量并入库。
WRITE_TO_DB = True


# 方法功能：读取配置，调用入库流程，打印每篇资料的处理结果。
# 输入：上方文件路径、租户和写入开关；输出：控制台中的处理摘要。
def main():
    # 读取 .env.db 的数据库配置和 .env 的 DeepSeek 配置。
    settings = load_settings()
    # 准备文件加载、切分和可选的入库对象。
    pipeline = build_ingestion_pipeline(settings, write=WRITE_TO_DB)
    # 执行资料加载、切分和可选写入。
    results = pipeline.run(FILE_PATH, tenant_id=TENANT_ID, write=WRITE_TO_DB)
    # 查看每篇文档的块数量和状态。
    print(json.dumps(results, ensure_ascii=False, indent=2))


# 点击 IDE 的 Run 或 Debug 时执行。
if __name__ == "__main__":
    # 不需要填写 ingest 等命令行参数。
    main()


# 录入后的数据记录条数
# -- 28
# SELECT * FROM kb_documents
# -- 48
# SELECT * FROM kb_document_tags
# -- 19
# SELECT * FROM kb_tags
# -- 8 
# SELECT * FROM kb_tag_dimensions
# --30
# SELECT * FROM kb_chunks
# --28
# SELECT * FROM kb_parent_chunks