# 类职责：统一的原始文档结构。
# 使用普通类保存数据，与旧代码的类写法一致。
class Document:
    # 方法功能：把传入参数保存为对象属性，供后续流程使用。
    def __init__(
        # 当前对象。
        self,
        # 同租户内稳定的业务标识。
        external_id,
        # 文档标题。
        title,
        # 用于切分和向量化的可读文本。
        content,
        # 租户来自可信导入配置。
        tenant_id='acme',
        # 业务模块。
        business_module='general',
        # 文档类型。
        doc_type='reference',
        # 0 公开、1 内部、2 受限、3 机密。
        security_level=1,
        # 同版本内容不可静默覆盖。
        version='1.0',
        # 是否当前发布版本。
        is_latest=True,
        # 原文件或业务系统来源。
        source='',
        # 页码、章节等定位字段。
        metadata=None,
        # 原始 JSON 对象。
        payload=None,
        # dimension:value 格式的冗余标签。
        tags=None,
    ):
        # 同租户内稳定的业务标识。
        self.external_id = external_id
        # 文档标题。
        self.title = title
        # 用于切分和向量化的可读文本。
        self.content = content
        # 租户来自可信导入配置。
        self.tenant_id = tenant_id
        # 业务模块。
        self.business_module = business_module
        # 文档类型。
        self.doc_type = doc_type
        # 0 公开、1 内部、2 受限、3 机密。
        self.security_level = security_level
        # 同版本内容不可静默覆盖。
        self.version = version
        # 是否当前发布版本。
        self.is_latest = is_latest
        # 原文件或业务系统来源。
        self.source = source
        # 页码、章节等定位字段。
        self.metadata = dict(metadata) if metadata is not None else dict()
        # 原始 JSON 对象。
        self.payload = dict(payload) if payload is not None else dict()
        # dimension:value 格式的冗余标签。
        self.tags = list(tags) if tags is not None else list()

    # 方法功能：把对象字段转换为普通字典，用于 JSON、调试或创建副本。
    # 返回明确列出的字段，不使用自动转换机制。
    def to_dict(self):
        # 字段名与数据结构一一对应。
        return {
            # 同租户内稳定的业务标识。
            "external_id": self.external_id,
            # 文档标题。
            "title": self.title,
            # 用于切分和向量化的可读文本。
            "content": self.content,
            # 租户来自可信导入配置。
            "tenant_id": self.tenant_id,
            # 业务模块。
            "business_module": self.business_module,
            # 文档类型。
            "doc_type": self.doc_type,
            # 0 公开、1 内部、2 受限、3 机密。
            "security_level": self.security_level,
            # 同版本内容不可静默覆盖。
            "version": self.version,
            # 是否当前发布版本。
            "is_latest": self.is_latest,
            # 原文件或业务系统来源。
            "source": self.source,
            # 页码、章节等定位字段。
            "metadata": self.metadata,
            # 原始 JSON 对象。
            "payload": self.payload,
            # dimension:value 格式的冗余标签。
            "tags": self.tags,
        }


# 类职责：权限和用户显式选择的业务过滤。
# 使用普通类保存数据，与旧代码的类写法一致。
class SearchFilter:
    # 方法功能：把传入参数保存为对象属性，供后续流程使用。
    def __init__(
        # 当前对象。
        self,
        # 不允许由问题改写覆盖。
        tenant_id,
        # 实际服务应由登录身份决定。
        max_security_level=1,
        # 可选模块。
        business_module=None,
        # 可选类型。
        doc_type=None,
        # 多标签采用 AND 匹配。
        tags=(),
        # 精确业务实体编号。
        entity_id=None,
    ):
        # 不允许由问题改写覆盖。
        self.tenant_id = tenant_id
        # 实际服务应由登录身份决定。
        self.max_security_level = max_security_level
        # 可选模块。
        self.business_module = business_module
        # 可选类型。
        self.doc_type = doc_type
        # 多标签采用 AND 匹配。
        self.tags = tags
        # 精确业务实体编号。
        self.entity_id = entity_id
        # 检查授权范围。
        if not self.tenant_id.strip() or not 0 <= self.max_security_level <= 3:
            # 拒绝无效过滤。
            raise ValueError("tenant_id 必填，security_level 必须为 0..3")

    # 方法功能：把对象字段转换为普通字典，用于 JSON、调试或创建副本。
    # 返回明确列出的字段，不使用自动转换机制。
    def to_dict(self):
        # 字段名与数据结构一一对应。
        return {
            # 不允许由问题改写覆盖。
            "tenant_id": self.tenant_id,
            # 实际服务应由登录身份决定。
            "max_security_level": self.max_security_level,
            # 可选模块。
            "business_module": self.business_module,
            # 可选类型。
            "doc_type": self.doc_type,
            # 多标签采用 AND 匹配。
            "tags": self.tags,
            # 精确业务实体编号。
            "entity_id": self.entity_id,
        }


# 类职责：子块保留父块及原文偏移。
# 使用普通类保存数据，与旧代码的类写法一致。
class Chunk:
    # 方法功能：把传入参数保存为对象属性，供后续流程使用。
    def __init__(
        # 当前对象。
        self,
        # 文档内子块序号。
        index,
        # 文档内父块序号。
        parent_index,
        # 子块正文。
        content,
        # 原文起始字符位置。
        start,
        # 原文结束位置，不包含该字符。
        end,
    ):
        # 文档内子块序号。
        self.index = index
        # 文档内父块序号。
        self.parent_index = parent_index
        # 子块正文。
        self.content = content
        # 原文起始字符位置。
        self.start = start
        # 原文结束位置，不包含该字符。
        self.end = end

    # 方法功能：把对象字段转换为普通字典，用于 JSON、调试或创建副本。
    # 返回明确列出的字段，不使用自动转换机制。
    def to_dict(self):
        # 字段名与数据结构一一对应。
        return {
            # 文档内子块序号。
            "index": self.index,
            # 文档内父块序号。
            "parent_index": self.parent_index,
            # 子块正文。
            "content": self.content,
            # 原文起始字符位置。
            "start": self.start,
            # 原文结束位置，不包含该字符。
            "end": self.end,
        }


# 类职责：各检索阶段共用同一结构。
# 使用普通类保存数据，与旧代码的类写法一致。
class Hit:
    # 方法功能：把传入参数保存为对象属性，供后续流程使用。
    def __init__(
        # 当前对象。
        self,
        # 数据库子块 ID。
        id,
        # 原始文档 ID。
        document_id,
        # 子块正文。
        content,
        # 引用标题。
        title='',
        # 引用来源。
        source='',
        # 来源位置和实体信息。
        metadata=None,
        # 余弦相似度。
        vector_score=0.0,
        # BM25 原始分数。
        bm25_score=0.0,
        # 融合排名分数。
        fusion_score=0.0,
        # Sigmoid 后的重排分数，不是答案正确率。
        rerank_score=0.0,
    ):
        # 数据库子块 ID。
        self.id = id
        # 原始文档 ID。
        self.document_id = document_id
        # 子块正文。
        self.content = content
        # 引用标题。
        self.title = title
        # 引用来源。
        self.source = source
        # 来源位置和实体信息。
        self.metadata = dict(metadata) if metadata is not None else dict()
        # 余弦相似度。
        self.vector_score = vector_score
        # BM25 原始分数。
        self.bm25_score = bm25_score
        # 融合排名分数。
        self.fusion_score = fusion_score
        # Sigmoid 后的重排分数，不是答案正确率。
        self.rerank_score = rerank_score

    # 方法功能：把对象字段转换为普通字典，用于 JSON、调试或创建副本。
    # 返回明确列出的字段，不使用自动转换机制。
    def to_dict(self):
        # 字段名与数据结构一一对应。
        return {
            # 数据库子块 ID。
            "id": self.id,
            # 原始文档 ID。
            "document_id": self.document_id,
            # 子块正文。
            "content": self.content,
            # 引用标题。
            "title": self.title,
            # 引用来源。
            "source": self.source,
            # 来源位置和实体信息。
            "metadata": self.metadata,
            # 余弦相似度。
            "vector_score": self.vector_score,
            # BM25 原始分数。
            "bm25_score": self.bm25_score,
            # 融合排名分数。
            "fusion_score": self.fusion_score,
            # Sigmoid 后的重排分数，不是答案正确率。
            "rerank_score": self.rerank_score,
        }

