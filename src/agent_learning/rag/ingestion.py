import hashlib
import json
from agent_learning.core.providers import validate_vectors


# 方法功能：计算文档正文、JSON、来源和权限信息的稳定哈希，用于同版本幂等检查。
# 输入：Document；输出：SHA-256 十六进制字符串。
# 对实际业务内容计算幂等指纹。
def document_hash(document):
    # 使用普通字典保存正文、JSON、标签和权限字段。
    data = document.to_dict()
    # 发布状态可以随新版本改变。
    data.pop("is_latest")
    # 稳定序列化后哈希。
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


# 类职责：资料入库总流程：加载文档、校验、父子切分，并按 write 开关决定是否向量化和保存。
# 第一个主流程：读取 → 切分 → 向量化 → 原子入库。
class IngestionPipeline:
    # 方法功能：保存入库流程用到的几个普通对象。
    # 输入：loader、chunker、embedder、repository；输出：完成初始化的入库流程。
    # 直接接收需要调用的对象。
    def __init__(self, loader, chunker, embedder=None, repository=None):
        # 统一保存组件。
        self.loader, self.chunker, self.embedder, self.repository = loader, chunker, embedder, repository

    # 方法功能：遍历输入文档进行校验和切分，write=True 时再计算向量并原子保存。
    # 输入：文件路径、默认租户和写入开关；输出：每篇文档的版本、块数量与处理状态列表。
    # 默认只预览，不接触数据库或模型。
    def run(self, path, tenant_id="acme", write=False):
        # 将不同文件转成统一文档。
        documents = self.loader.load(path, tenant_id)
        # 拒绝空导入文件。
        if not documents:
            # 不报告虚假成功。
            raise ValueError("文件中没有可导入记录")
        # 保存每篇处理摘要。
        results = []
        # 检查一个文件内的重复版本。
        seen = set()
        # 逐篇文档处理，事务粒度为单文档。
        for document in documents:
            # 幂等业务键。
            key = (document.tenant_id, document.external_id, document.version)
            # 重复业务键通常意味着数据错误。
            if key in seen:
                # 不静默覆盖。
                raise ValueError(f"输入存在重复版本: {key}")
            # 记录已处理键。
            seen.add(key)
            # 检查必填字段。
            if not all([document.external_id.strip(), document.title.strip(), document.tenant_id.strip(), document.version.strip()]):
                # 尽早校验。
                raise ValueError("external_id/title/tenant_id/version 不能为空")
            # 检查权限和发布标记。
            if not 0 <= document.security_level <= 3 or not isinstance(document.is_latest, bool):
                # 防止类型误用。
                raise ValueError("security_level 必须为 0..3，is_latest 必须为布尔值")
            # 校验冗余标签。
            if not isinstance(document.tags, list) or not all(isinstance(tag, str) and ":" in tag for tag in document.tags):
                # 与标签字典约定一致。
                raise ValueError("tags 必须是 dimension:value 字符串数组")
            # 统一执行父子切分。
            parents, chunks = self.chunker.split(document.content)
            # 默认只是预览。
            status = "preview"
            # 只有用户显式开启才写数据库。
            if write:
                # 需要完整入库依赖。
                if self.embedder is None or self.repository is None:
                    # 防止半配置运行。
                    raise ValueError("写入需要 embedder 和 repository")
                # 批量计算子块向量。
                vectors = self.embedder.passages([chunk.content for chunk in chunks])
                # 再次验证依赖输出。
                validate_vectors(vectors, len(chunks), self.embedder.dimension)
                # 记录切分与模型版本。
                fingerprint = f"char-v1:{self.chunker.chunk_size}:{self.chunker.overlap}:{self.chunker.parent_size}:{self.embedder.model_name}"
                # 单篇事务保存。
                status = self.repository.save(document, parents, chunks, vectors, self.embedder.model_name, fingerprint)
            # 不输出完整敏感正文。
            results.append({"external_id": document.external_id, "version": document.version, "parents": len(parents), "chunks": len(chunks), "status": status})
        # 返回可检查的入库结果。
        return results
