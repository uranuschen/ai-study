import json
from pathlib import Path
from agent_learning.cli import build_pipeline
from agent_learning.core.config import load_settings
from agent_learning.core.models import SearchFilter
from agent_learning.rag.loaders import DocumentLoader
from agent_learning.rag.repository import stable_id


# 默认只列出题目；用户准备好数据库后才改为 True。
RUN_LIVE = False


# 方法功能：真模型评测由用户显式运行，默认仅列出评测用例。
# 真模型评测由用户显式运行，默认仅列出评测用例。
def main():
    # 定位项目根目录。
    root = Path(__file__).resolve().parents[1]
    # 读取固定评测集。
    cases = json.loads((root / "data/evaluation_cases.json").read_text(encoding="utf-8"))
    # 默认预览无需数据库和模型。
    if not RUN_LIVE:
        # 展示测试目标。
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        # 不初始化模型。
        return
    # 只有 live 模式创建真实流程。
    pipeline = build_pipeline(load_settings())
    # 映射原文业务 ID。
    documents = DocumentLoader().load(root / "data/enterprise_documents.json")
    # 与数据库 UUID 一致。
    identities = {stable_id(doc.tenant_id, doc.external_id, doc.version): doc.external_id for doc in documents}
    # 收集每题检查结果。
    results = []
    # 顺序执行以便定位失败题。
    for case in cases:
        # 模拟可信权限。
        filters = SearchFilter(case["tenant"], case["security"], case.get("module"), tags=tuple(case.get("tags", [])))
        # 运行完整问答。
        result = pipeline.ask(case["question"], filters)
        # 解析被引用的业务文档。
        cited = {identities.get(item["document_id"]) for item in result["citations"]}
        # 这些规则只作为自动回归提示。
        checks = {"status": result["status"] == case["expected_status"], "required_terms": all(term in result["answer"] for term in case["required_terms"]), "forbidden_terms": all(term not in result["answer"] for term in case["forbidden_terms"]), "source_hit": not case["expected_documents"] or bool(cited & set(case["expected_documents"]))}
        # 保留失败信息供人工复核。
        results.append({"id": case["id"], "passed": all(checks.values()), "checks": checks, "result": result})
    # 输出评测报告，不写数据库。
    print(json.dumps({"passed": sum(row["passed"] for row in results), "total": len(results), "details": results}, ensure_ascii=False, indent=2))


# 仅在用户执行脚本时运行。
if __name__ == "__main__":
    # 启动评测。
    main()
