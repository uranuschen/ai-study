-- 仅供用户在 ragdb 中手动执行，为已经按 01_schema.sql 建好的六张新版表补充中文备注。
-- 不需要删除或重建表；此文件只更新备注，不修改字段定义或业务数据。
-- 旧版同名表字段不完整，不能使用本文件把旧结构升级为新结构。
BEGIN;

-- 原始文档表：保存一篇业务资料的一个版本，以及原始 JSON、租户、权限、来源和向量化状态。
COMMENT ON TABLE public.kb_documents IS '原始文档表：保存一篇业务资料的一个版本，以及原始 JSON、租户、权限、来源和向量化状态。';
COMMENT ON COLUMN public.kb_documents.id IS '文档版本的唯一编号 UUID，由程序根据租户、业务标识和版本生成。';
COMMENT ON COLUMN public.kb_documents.tenant_id IS '租户或公司标识，例如 acme、beta；用于隔离不同公司的资料。';
COMMENT ON COLUMN public.kb_documents.external_id IS '业务文档编号，例如 FIN-TRAVEL、ORDER-A1002；同一文档不同版本共用此编号。';
COMMENT ON COLUMN public.kb_documents.title IS '文档标题，用于展示来源，并为 JSON 文档的向量化正文提供标题信息。';
COMMENT ON COLUMN public.kb_documents.content IS '用于切分和向量化的完整可读正文；JSON 输入由标题和 vector_fields 指定字段组合生成。';
COMMENT ON COLUMN public.kb_documents.payload IS '原始业务 JSON 对象，保留订单、退款或制度等结构化数据；普通文件默认空对象。';
COMMENT ON COLUMN public.kb_documents.metadata IS '文档附加信息 JSON，例如 page 页码、sheet 表名、row 行号、section 章节、entity_ids 业务编号和 vector_fields 向量化字段列表。';
COMMENT ON COLUMN public.kb_documents.business_module IS '业务模块，例如 finance 财务、hr 人事、support 售后；用于检索前过滤。';
COMMENT ON COLUMN public.kb_documents.doc_type IS '文档类型，例如 policy 制度、process 流程、faq 问答、record 业务记录、template 模板。';
COMMENT ON COLUMN public.kb_documents.security_level IS '资料保密级别：0 公开、1 内部、2 受限、3 机密；只能读取不高于用户授权级别的资料，所有级别仍受租户隔离。';
COMMENT ON COLUMN public.kb_documents.version IS '文档版本号，例如 1.0、2026.1；同租户同业务编号同版本唯一，内容变化应使用新版本。';
COMMENT ON COLUMN public.kb_documents.is_latest IS '是否当前发布版本：true 为现行版本，false 为历史版本；问答只检索现行且 ready 的文档。';
COMMENT ON COLUMN public.kb_documents.source IS '资料来源，例如原文件路径、制度目录或 ERP/订单/A1002；用于答案溯源。';
COMMENT ON COLUMN public.kb_documents.tags IS '冗余标签字符串数组，格式为 维度:代码，例如 module:finance-travel；与文档标签关联表同步，便于过滤。';
COMMENT ON COLUMN public.kb_documents.content_hash IS '文档内容及业务属性的 SHA-256 指纹，64 位十六进制文本；重复导入时检查同版本资料是否变化。';
COMMENT ON COLUMN public.kb_documents.index_status IS '向量化状态：pending 表示只保存原文、尚未完成向量入库；ready 表示父子块及向量已完整保存，可以检索。';
COMMENT ON COLUMN public.kb_documents.pipeline_fingerprint IS '记录切分大小、重叠、父块大小和向量模型的处理配置；用于判断已有向量是否适配当前配置，pending 时可为空。';
COMMENT ON COLUMN public.kb_documents.created_at IS '该文档版本首次写入数据库的时间，含时区，默认当前时间。';
COMMENT ON COLUMN public.kb_documents.updated_at IS '应用最近更新该文档记录的时间；入库程序更新状态或发布标记时维护，没有自动更新时间触发器。';

-- 文档父块表：保存较大的原文片段及其字符位置，供子块关联；当前父块不单独生成向量。
COMMENT ON TABLE public.kb_parent_chunks IS '文档父块表：保存较大的原文片段及其字符位置，供子块关联；当前父块不单独生成向量。';
COMMENT ON COLUMN public.kb_parent_chunks.id IS '父块唯一编号 UUID，由文档编号和父块序号生成。';
COMMENT ON COLUMN public.kb_parent_chunks.document_id IS '所属文档版本编号，关联 kb_documents.id。';
COMMENT ON COLUMN public.kb_parent_chunks.tenant_id IS '所属租户，必须与文档表中的租户一致，防止跨租户关联。';
COMMENT ON COLUMN public.kb_parent_chunks.parent_index IS '父块在当前文档中的顺序编号，从 0 开始；同一文档内不能重复。';
COMMENT ON COLUMN public.kb_parent_chunks.content IS '父块的原始正文片段，范围通常比子块更大。';
COMMENT ON COLUMN public.kb_parent_chunks.start_char IS '父块在完整文档 content 中的起始字符位置，从 0 开始，包含此位置；不是字节或 token 位置。';
COMMENT ON COLUMN public.kb_parent_chunks.end_char IS '父块在完整文档 content 中的结束字符位置，不包含此位置；可用 content[start_char:end_char] 还原片段。';

-- 文档子块表：保存实际参与向量检索和 BM25 检索的小片段，以及来源位置和真实 Embedding 向量。
COMMENT ON TABLE public.kb_chunks IS '文档子块表：保存实际参与向量检索和 BM25 检索的小片段，以及来源位置和真实 Embedding 向量。';
COMMENT ON COLUMN public.kb_chunks.id IS '子块唯一编号 UUID，用于合并去重和答案引用定位。';
COMMENT ON COLUMN public.kb_chunks.document_id IS '所属文档版本编号，关联 kb_documents.id。';
COMMENT ON COLUMN public.kb_chunks.tenant_id IS '所属租户，必须与文档和父块的租户一致。';
COMMENT ON COLUMN public.kb_chunks.parent_id IS '所属父块编号，关联 kb_parent_chunks.id；父块必须属于同一文档和租户。';
COMMENT ON COLUMN public.kb_chunks.chunk_index IS '子块在整篇文档中的顺序编号，从 0 开始；不同父块下的子块仍使用文档内连续编号。';
COMMENT ON COLUMN public.kb_chunks.content IS '实际送入向量模型、BM25 和精排模型的子块正文。';
COMMENT ON COLUMN public.kb_chunks.start_char IS '子块在完整文档正文中的起始字符位置，从 0 开始并包含；不是相对父块的偏移。';
COMMENT ON COLUMN public.kb_chunks.end_char IS '子块在完整文档正文中的结束字符位置，不包含；用于定位原文范围。';
COMMENT ON COLUMN public.kb_chunks.metadata IS '子块附加定位信息 JSON，当前保存 start 和 end；查询时与文档的页码、章节等 metadata 合并。';
COMMENT ON COLUMN public.kb_chunks.embedding IS '子块正文生成的 512 维真实向量，使用余弦距离检索；不能用随机数组或全零向量占位。';
COMMENT ON COLUMN public.kb_chunks.embedding_model IS '生成向量所用的模型名称，例如 BAAI/bge-small-zh-v1.5；问题向量必须使用同一模型空间。';
COMMENT ON COLUMN public.kb_chunks.created_at IS '子块首次写入数据库的时间，含时区，默认当前时间。';

-- 标签维度表：定义每个租户有哪些分类角度，例如业务模块、地区、适用人群和生命周期。
COMMENT ON TABLE public.kb_tag_dimensions IS '标签维度表：定义每个租户有哪些分类角度，例如业务模块、地区、适用人群和生命周期。';
COMMENT ON COLUMN public.kb_tag_dimensions.tenant_id IS '标签维度所属租户，与 code 一起构成主键。';
COMMENT ON COLUMN public.kb_tag_dimensions.code IS '维度代码，例如 module、region、audience、lifecycle；用于程序匹配。';
COMMENT ON COLUMN public.kb_tag_dimensions.name IS '维度中文名称，例如业务模块、地区、适用人群、生命周期；用于阅读和展示。';

-- 标签字典表：保存具体标签及父子关系；例如 module 维度下 finance 为父标签，finance-travel 为子标签。
COMMENT ON TABLE public.kb_tags IS '标签字典表：保存具体标签及父子关系；例如 module 维度下 finance 为父标签，finance-travel 为子标签。';
COMMENT ON COLUMN public.kb_tags.id IS '标签唯一编号 UUID，供文档标签关联表引用。';
COMMENT ON COLUMN public.kb_tags.tenant_id IS '标签所属租户，标签及其父标签不能跨租户关联。';
COMMENT ON COLUMN public.kb_tags.dimension_code IS '标签所属维度代码，关联同租户 kb_tag_dimensions.code，例如 module。';
COMMENT ON COLUMN public.kb_tags.code IS '标签代码，例如 finance、finance-travel、cn；与维度组合后得到 module:finance 等冗余标签值。';
COMMENT ON COLUMN public.kb_tags.name IS '标签显示名称，例如财务、财务/差旅、中国。';
COMMENT ON COLUMN public.kb_tags.parent_id IS '父标签编号，关联本表 id；顶层标签为空，子标签的父级必须同租户、同维度，且不能直接指向自己。';
COMMENT ON COLUMN public.kb_tags.metadata IS '标签扩展信息 JSON，预留标签说明等附加属性，当前默认空对象。';

-- 文档标签关联表：记录哪些标签属于哪篇文档，一个文档可对应多个维度的多个标签。
COMMENT ON TABLE public.kb_document_tags IS '文档标签关联表：记录哪些标签属于哪篇文档，一个文档可对应多个维度的多个标签。';
COMMENT ON COLUMN public.kb_document_tags.document_id IS '被打标的文档版本编号，关联 kb_documents.id；与 tag_id 一起构成主键。';
COMMENT ON COLUMN public.kb_document_tags.tag_id IS '关联的具体标签编号，关联 kb_tags.id。';
COMMENT ON COLUMN public.kb_document_tags.tenant_id IS '关联关系所属租户，文档与标签必须属于这个相同租户。';
COMMENT ON COLUMN public.kb_document_tags.assigned_by IS '打标来源，默认 manual 表示人工指定；后续可记录自动打标方式，当前未实现自动打标。';
COMMENT ON COLUMN public.kb_document_tags.confidence IS '标签可信度，范围 0 到 1，默认 1；预留给自动打标使用，与向量相似度或精排分数无关。';
COMMIT;
