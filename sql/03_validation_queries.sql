-- 用户完成建表、初始化和向量化之后，可手动执行这些只读检查。
-- 此文件不会被程序自动执行。
SELECT extversion FROM pg_extension WHERE extname = 'vector';
SELECT tenant_id, index_status, count(*) FROM public.kb_documents GROUP BY tenant_id, index_status ORDER BY tenant_id, index_status;
SELECT embedding_model, vector_dims(embedding) AS dimensions, count(*) FROM public.kb_chunks GROUP BY embedding_model, vector_dims(embedding);
SELECT d.external_id, d.version, d.is_latest, count(c.id) AS chunks FROM public.kb_documents d LEFT JOIN public.kb_chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.tenant_id,d.external_id,d.version;
-- 以下三个查询应返回零行。
SELECT tenant_id,external_id FROM public.kb_documents WHERE is_latest GROUP BY tenant_id,external_id HAVING count(*) > 1;
SELECT c.id FROM public.kb_chunks c JOIN public.kb_documents d ON d.id=c.document_id WHERE c.tenant_id<>d.tenant_id;
SELECT d.id FROM public.kb_documents d WHERE d.index_status='ready' AND NOT EXISTS (SELECT 1 FROM public.kb_chunks c WHERE c.document_id=d.id);
-- 检查冗余 tags 与规范标签关联是否一致；应返回零行。
SELECT d.id FROM public.kb_documents d WHERE
    ARRAY(SELECT DISTINCT unnest(d.tags) ORDER BY 1) IS DISTINCT FROM
    ARRAY(SELECT t.dimension_code || ':' || t.code FROM public.kb_document_tags dt JOIN public.kb_tags t ON t.id=dt.tag_id WHERE dt.document_id=d.id ORDER BY 1);
-- 对 20~30 条原文，顺序扫描可能比 HNSW 更合理，不强制优化器选择索引。
SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname;
