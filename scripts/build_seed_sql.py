import json
from pathlib import Path
from agent_learning.rag.ingestion import document_hash
from agent_learning.rag.loaders import DocumentLoader
from agent_learning.rag.repository import stable_id


# 方法功能：把样例值转换为 SQL 字面量，仅用于离线生成初始化脚本文本。
# 输入：Python 标量或字符串；输出：经过单引号转义的 SQL 文本。
# 生成静态 SQL 文本；从不连接数据库。
def literal(value):
    # SQL 空值。
    if value is None:
        # 保留空值语义。
        return "NULL"
    # SQL 布尔字面量。
    if isinstance(value, bool):
        # 不输出 Python 大写布尔值。
        return "true" if value else "false"
    # 数值不用单引号。
    if isinstance(value, (int, float)):
        # 输出数值文本。
        return str(value)
    # 标准 SQL 字符串转义。
    return "'" + str(value).replace("'", "''") + "'"


# 方法功能：通过统一 Loader 加载企业 JSON，生成原文、标签和关联记录的初始化 SQL。
# 输入：企业 JSON 文件路径；输出：完整 SQL 字符串，不执行 SQL。
# 从同一 JSON 生成与入库代码一致的初始化原文。
def build_seed(path):
    # 使用统一投影与来源规则。
    documents = DocumentLoader().load(path)
    # 明确执行边界。
    lines = ["-- 虚构企业数据，仅供学习。此文件只初始化原文和标签，真实向量由用户执行 ingest --write 生成。", "-- 不存在占位向量；导入后 index_status=pending，不能立即做向量问答。", "BEGIN;", "SET LOCAL standard_conforming_strings = on;"]
    # 多维度标签设计。
    dimensions = {"module": "业务模块", "region": "地区", "audience": "适用人群", "lifecycle": "生命周期"}
    # 可读标签名称。
    names = {"finance":"财务", "finance-travel":"财务/差旅", "hr":"人事", "it":"信息技术", "security":"安全", "procurement":"采购", "sales":"销售", "support":"售后", "legal":"法务", "product":"产品", "cn":"中国", "employee":"员工", "manager":"管理人员", "active":"处理中", "closed":"已关闭"}
    # 每个租户独立字典。
    for tenant in sorted({doc.tenant_id for doc in documents}):
        # 初始化标签维度。
        for code, name in dimensions.items():
            # 可重复执行。
            lines.append(f"INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ({literal(tenant)},{literal(code)},{literal(name)}) ON CONFLICT DO NOTHING;")
        # 补齐父级财务标签。
        tags = sorted({tag for doc in documents if doc.tenant_id == tenant for tag in doc.tags} | {"module:finance"})
        # 字典顺序保证 finance 父标签先创建。
        for tag in tags:
            # 分离维度与取值。
            dimension, code = tag.split(":", 1)
            # 示例父子层级。
            parent = stable_id(tenant, "tag", "module:finance") if tag == "module:finance-travel" else None
            # 组合标签字段。
            values = [stable_id(tenant, "tag", tag), tenant, dimension, code, names.get(code, code), parent]
            # 写入字典文本。
            lines.append("INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES (" + ",".join(map(literal, values)) + ") ON CONFLICT DO NOTHING;")
    # 一条业务记录对应一个原文版本。
    for doc in documents:
        # 与仓储使用相同 UUID。
        identifier = stable_id(doc.tenant_id, doc.external_id, doc.version)
        # 保留完整结构化字段。
        values = [identifier, doc.tenant_id, doc.external_id, doc.title, doc.content, json.dumps(doc.payload, ensure_ascii=False), json.dumps(doc.metadata, ensure_ascii=False), doc.business_module, doc.doc_type, doc.security_level, doc.version, doc.is_latest, doc.source, document_hash(doc)]
        # 标签冗余数组。
        tags_sql = "ARRAY[" + ",".join(map(literal, doc.tags)) + "]::text[]"
        # 不覆盖已有版本。
        lines.append("INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES (" + ",".join(map(literal, values)) + "," + tags_sql + ") ON CONFLICT (tenant_id,external_id,version) DO NOTHING;")
        # 写入规范化关联表，保持生成顺序稳定。
        for tag in sorted(set(doc.tags)):
            # 引用同租户字典。
            values = [identifier, stable_id(doc.tenant_id, "tag", tag), doc.tenant_id]
            # 关联幂等。
            lines.append("INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES (" + ",".join(map(literal, values)) + ") ON CONFLICT DO NOTHING;")
    # 初始化保持原子性。
    lines.append("COMMIT;")
    # 生成完整 SQL。
    return "\n".join(lines) + "\n"


# 用户或项目维护者手动生成文本。
if __name__ == "__main__":
    # 与调用工作目录无关。
    root = Path(__file__).resolve().parents[1]
    # 初始化 SQL 单独保存。
    output = root / "sql" / "02_seed_documents.sql"
    # 只写本地文件。
    output.write_text(build_seed(root / "data" / "enterprise_documents.json"), encoding="utf-8")
    # 明确实际操作。
    print(f"已生成 {output.name}，未连接数据库")
