-- 虚构企业数据，仅供学习。此文件只初始化原文和标签，真实向量由用户执行 ingest --write 生成。
-- 不存在占位向量；导入后 index_status=pending，不能立即做向量问答。
BEGIN;
SET LOCAL standard_conforming_strings = on;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('acme','module','业务模块') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('acme','region','地区') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('acme','audience','适用人群') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('acme','lifecycle','生命周期') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('619e0886-401e-57c8-94c5-f50c9bafaa93','acme','audience','employee','员工',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('7abda3f0-c27c-573c-898a-7cb1879743cb','acme','audience','manager','管理人员',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('ec4cc6aa-9c63-544d-907d-d6393c4dee5d','acme','lifecycle','active','处理中',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('6f92b41a-7e0e-56da-9ab5-fa9bc24fd38f','acme','lifecycle','closed','已关闭',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('2f08f532-61e6-5ccd-b182-c606364fdd40','acme','module','finance','财务',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('9268eec2-d1ee-5c7b-8595-3832ffb9e850','acme','module','finance-travel','财务/差旅','2f08f532-61e6-5ccd-b182-c606364fdd40') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('5d71ecb7-3266-5f4b-8d8d-d13c304c313d','acme','module','hr','人事',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('7e903e8c-5ee9-50bc-9859-86377117224f','acme','module','it','信息技术',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('b567ad85-64bf-5675-8f1b-236fbf797e4c','acme','module','legal','法务',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('dddb8901-70d7-5183-bc39-0fa741d45bc0','acme','module','procurement','采购',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('8eceb1d2-9abd-5936-b9de-735cc58badeb','acme','module','product','产品',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('aadcfbc3-056b-5a3d-987a-981da9fb53fa','acme','module','sales','销售',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('591b7f67-6b72-5302-8571-200104616430','acme','module','security','安全',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('6c46f4cf-ae69-545a-ab33-dcd8be179493','acme','module','support','售后',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('82160a90-599d-5a5b-8928-2bb7e8fe6c24','acme','region','cn','中国',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('beta','module','业务模块') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('beta','region','地区') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('beta','audience','适用人群') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tag_dimensions (tenant_id,code,name) VALUES ('beta','lifecycle','生命周期') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('347872bd-8b77-5169-b695-b291a3435160','beta','module','finance','财务',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('0755dd2c-ad11-50cc-8e45-db79de4a70a6','beta','module','finance-travel','财务/差旅','347872bd-8b77-5169-b695-b291a3435160') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('52e5e297-3138-51f1-a0a3-4188a4888daa','beta','module','sales','销售',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_tags (id,tenant_id,dimension_code,code,name,parent_id) VALUES ('94c6e75b-3275-5679-9f27-1f5b959c9c4d','beta','region','cn','中国',NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('017a2a72-b675-5a04-b49c-a0bbc4e7406e','acme','FIN-TRAVEL','差旅住宿报销制度（历史版）','差旅住宿报销制度（历史版）

本版本已失效，仅用于验证版本过滤。2025 年一线城市住宿上限为每人每晚 450 元。不得用于回答当前标准。

structured_data.一线城市上限: 450
structured_data.币种: "CNY"
structured_data.替代版本: "2026.1"','{"external_id": "FIN-TRAVEL", "title": "差旅住宿报销制度（历史版）", "tenant_id": "acme", "business_module": "finance", "doc_type": "policy", "version": "2025.1", "is_latest": false, "security_level": 1, "source": "财务部/差旅制度/2025", "tags": ["module:finance-travel", "region:cn"], "metadata": {"section": "住宿标准", "effective_date": "2025-01-01"}, "content": "本版本已失效，仅用于验证版本过滤。2025 年一线城市住宿上限为每人每晚 450 元。不得用于回答当前标准。", "structured_data": {"一线城市上限": 450, "币种": "CNY", "替代版本": "2026.1"}}','{"section": "住宿标准", "effective_date": "2025-01-01", "vector_fields": ["content", "structured_data"]}','finance','policy',1,'2025.1',false,'财务部/差旅制度/2025','b7ce6c39d0b30a57d06066cfb6977cf523f179a5abe932b2a7d4425fb462fe2c',ARRAY['module:finance-travel','region:cn']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('017a2a72-b675-5a04-b49c-a0bbc4e7406e','9268eec2-d1ee-5c7b-8595-3832ffb9e850','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('017a2a72-b675-5a04-b49c-a0bbc4e7406e','82160a90-599d-5a5b-8928-2bb7e8fe6c24','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('1b80f53c-bfb5-5c5a-90aa-c44f86e6dbe7','acme','FIN-TRAVEL','差旅住宿报销制度（现行版）','差旅住宿报销制度（现行版）

适用于星河科技 acme 的境内员工出差。一线城市住宿每人每晚不超过 600 元，其他城市不超过 400 元。跨地区项目连续驻场超过 14 晚，须在订房前获得部门负责人和财务经理双重审批。超标部分原则上个人承担，展会导致的价格上涨可事前提交三家酒店报价申请特批。不得把旧版 450 元标准作为现行标准。发票抬头须与签约主体一致，住宿发票、支付凭证、出差审批单缺一不可。

structured_data.住宿标准[0].地区: "一线城市"
structured_data.住宿标准[0].每晚人民币: 600
structured_data.住宿标准[1].地区: "其他城市"
structured_data.住宿标准[1].每晚人民币: 400
structured_data.例外: "展会期间凭三家酒店报价事前特批"
structured_data.长期驻场.审批人[0]: "部门负责人"
structured_data.长期驻场.审批人[1]: "财务经理"
structured_data.长期驻场.触发晚数: 14','{"external_id": "FIN-TRAVEL", "title": "差旅住宿报销制度（现行版）", "tenant_id": "acme", "business_module": "finance", "doc_type": "policy", "version": "2026.1", "security_level": 1, "source": "财务部/差旅制度/2026", "tags": ["module:finance-travel", "region:cn", "audience:employee"], "metadata": {"section": "第3章 住宿", "effective_date": "2026-01-01", "owner": "财务共享中心"}, "vector_fields": ["content", "structured_data"], "content": "适用于星河科技 acme 的境内员工出差。一线城市住宿每人每晚不超过 600 元，其他城市不超过 400 元。跨地区项目连续驻场超过 14 晚，须在订房前获得部门负责人和财务经理双重审批。超标部分原则上个人承担，展会导致的价格上涨可事前提交三家酒店报价申请特批。不得把旧版 450 元标准作为现行标准。发票抬头须与签约主体一致，住宿发票、支付凭证、出差审批单缺一不可。", "structured_data": {"住宿标准": [{"地区": "一线城市", "每晚人民币": 600}, {"地区": "其他城市", "每晚人民币": 400}], "长期驻场": {"触发晚数": 14, "审批人": ["部门负责人", "财务经理"]}, "例外": "展会期间凭三家酒店报价事前特批"}}','{"section": "第3章 住宿", "effective_date": "2026-01-01", "owner": "财务共享中心", "vector_fields": ["content", "structured_data"]}','finance','policy',1,'2026.1',true,'财务部/差旅制度/2026','395f16035459bd7141d2bb78f849728c7a0a4d70e51a4fd711631dd2a189e660',ARRAY['module:finance-travel','region:cn','audience:employee']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1b80f53c-bfb5-5c5a-90aa-c44f86e6dbe7','619e0886-401e-57c8-94c5-f50c9bafaa93','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1b80f53c-bfb5-5c5a-90aa-c44f86e6dbe7','9268eec2-d1ee-5c7b-8595-3832ffb9e850','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1b80f53c-bfb5-5c5a-90aa-c44f86e6dbe7','82160a90-599d-5a5b-8928-2bb7e8fe6c24','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('fcafac42-cf48-5ad2-9010-1ae3791544e3','acme','FIN-EXPENSE','差旅报销提交期限及退回处理','差旅报销提交期限及退回处理

员工应在出差结束后 15 个自然日内提交报销。财务在材料齐全后 5 个工作日内完成审核，审核通过后 3 个工作日内付款。材料退回后补件期限为 7 个自然日；超过期限需要重新提交申请。外币费用采用实际支付日的公司财务系统汇率，不使用申请日汇率。

structured_data.审核时限.单位: "工作日"
structured_data.审核时限.天数: 5
structured_data.提交时限.单位: "自然日"
structured_data.提交时限.天数: 15
structured_data.支付时限.单位: "工作日"
structured_data.支付时限.天数: 3','{"external_id": "FIN-EXPENSE", "title": "差旅报销提交期限及退回处理", "business_module": "finance", "doc_type": "process", "source": "财务部/报销操作手册", "tags": ["module:finance", "audience:employee"], "metadata": {"section": "提交和补件"}, "content": "员工应在出差结束后 15 个自然日内提交报销。财务在材料齐全后 5 个工作日内完成审核，审核通过后 3 个工作日内付款。材料退回后补件期限为 7 个自然日；超过期限需要重新提交申请。外币费用采用实际支付日的公司财务系统汇率，不使用申请日汇率。", "structured_data": {"提交时限": {"天数": 15, "单位": "自然日"}, "审核时限": {"天数": 5, "单位": "工作日"}, "支付时限": {"天数": 3, "单位": "工作日"}}}','{"section": "提交和补件", "vector_fields": ["content", "structured_data"]}','finance','process',1,'1.0',true,'财务部/报销操作手册','c9bc675f0d442ba2d48c51ed515ee456fd95baab67abe32f10303ccd92dabf0f',ARRAY['module:finance','audience:employee']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('fcafac42-cf48-5ad2-9010-1ae3791544e3','619e0886-401e-57c8-94c5-f50c9bafaa93','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('fcafac42-cf48-5ad2-9010-1ae3791544e3','2f08f532-61e6-5ccd-b182-c606364fdd40','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('3e864865-c801-5946-9785-a6bdf96d2d15','acme','FIN-INVOICE','电子发票重复报销与红冲规则','电子发票重复报销与红冲规则

同一电子发票号码与开票日期组合只能报销一次。红冲发票不得报销；部分红冲应附原票与红字票，并按剩余有效金额申请。公司名称、统一社会信用代码与报销主体不一致的发票退回重开。纸质打印件不替代原始电子文件。

structured_data.必需附件[0]: "原始电子发票"
structured_data.必需附件[1]: "支付凭证"
structured_data.查重键[0]: "发票号码"
structured_data.查重键[1]: "开票日期"','{"external_id": "FIN-INVOICE", "title": "电子发票重复报销与红冲规则", "business_module": "finance", "doc_type": "policy", "source": "财务部/发票规范", "tags": ["module:finance"], "metadata": {"section": "电子发票"}, "content": "同一电子发票号码与开票日期组合只能报销一次。红冲发票不得报销；部分红冲应附原票与红字票，并按剩余有效金额申请。公司名称、统一社会信用代码与报销主体不一致的发票退回重开。纸质打印件不替代原始电子文件。", "structured_data": {"查重键": ["发票号码", "开票日期"], "必需附件": ["原始电子发票", "支付凭证"]}}','{"section": "电子发票", "vector_fields": ["content", "structured_data"]}','finance','policy',1,'1.0',true,'财务部/发票规范','3af03632aa7835b7c350ade89d250ec42fb5289a1020e865ae2497bd39ce0e0f',ARRAY['module:finance']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('3e864865-c801-5946-9785-a6bdf96d2d15','2f08f532-61e6-5ccd-b182-c606364fdd40','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('1489fc14-d60b-5bf6-bb99-0f81d9c2e372','acme','FIN-PAYMENT','供应商付款审批分级','供应商付款审批分级

供应商付款低于 5 万元由部门负责人审批；5 万元至不足 20 万元增加财务经理审批；20 万元及以上增加财务总监审批。首次向供应商新账户付款，必须由采购与财务分别回拨验证账户。紧急付款也不得跳过账户复核。

structured_data.审批区间[0].审批: "部门负责人"
structured_data.审批区间[0].最低: 0
structured_data.审批区间[0].最高不含: 50000
structured_data.审批区间[1].审批: "部门负责人、财务经理"
structured_data.审批区间[1].最低: 50000
structured_data.审批区间[1].最高不含: 200000
structured_data.审批区间[2].审批: "部门负责人、财务经理、财务总监"
structured_data.审批区间[2].最低: 200000','{"external_id": "FIN-PAYMENT", "title": "供应商付款审批分级", "business_module": "finance", "doc_type": "policy", "security_level": 2, "source": "财务部/付款授权矩阵", "tags": ["module:finance", "audience:manager"], "metadata": {"section": "供应商付款"}, "content": "供应商付款低于 5 万元由部门负责人审批；5 万元至不足 20 万元增加财务经理审批；20 万元及以上增加财务总监审批。首次向供应商新账户付款，必须由采购与财务分别回拨验证账户。紧急付款也不得跳过账户复核。", "structured_data": {"审批区间": [{"最低": 0, "最高不含": 50000, "审批": "部门负责人"}, {"最低": 50000, "最高不含": 200000, "审批": "部门负责人、财务经理"}, {"最低": 200000, "审批": "部门负责人、财务经理、财务总监"}]}}','{"section": "供应商付款", "vector_fields": ["content", "structured_data"]}','finance','policy',2,'1.0',true,'财务部/付款授权矩阵','f2c405ddc4bc8cfde8d9dad6f730db50c78690cee0f685da811a7ae9681d27e2',ARRAY['module:finance','audience:manager']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1489fc14-d60b-5bf6-bb99-0f81d9c2e372','7abda3f0-c27c-573c-898a-7cb1879743cb','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1489fc14-d60b-5bf6-bb99-0f81d9c2e372','2f08f532-61e6-5ccd-b182-c606364fdd40','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('2648475f-cf39-5c43-a694-d16b5f1dbff3','acme','HR-ONBOARD','员工入职材料及办理流程','员工入职材料及办理流程

入职需提供身份证、学历证明、原单位离职证明及本人银行卡信息。HR 核验材料后签署劳动合同，IT 在收到工号后 1 个工作日内创建基础账户。岗位特殊系统权限须由直属主管另行申请，不随基础账户自动开通。

structured_data.材料[0]: "身份证"
structured_data.材料[1]: "学历证明"
structured_data.材料[2]: "离职证明"
structured_data.材料[3]: "银行卡信息"
structured_data.账号依赖: "工号已创建"','{"external_id": "HR-ONBOARD", "title": "员工入职材料及办理流程", "business_module": "hr", "doc_type": "process", "source": "人力资源部/入职手册", "tags": ["module:hr", "audience:employee"], "metadata": {"section": "入职首日"}, "content": "入职需提供身份证、学历证明、原单位离职证明及本人银行卡信息。HR 核验材料后签署劳动合同，IT 在收到工号后 1 个工作日内创建基础账户。岗位特殊系统权限须由直属主管另行申请，不随基础账户自动开通。", "structured_data": {"材料": ["身份证", "学历证明", "离职证明", "银行卡信息"], "账号依赖": "工号已创建"}}','{"section": "入职首日", "vector_fields": ["content", "structured_data"]}','hr','process',1,'1.0',true,'人力资源部/入职手册','6dfff082df1a43be44944a8e74c115a8baa75309a89eecec5673f7f2eabb770d',ARRAY['module:hr','audience:employee']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('2648475f-cf39-5c43-a694-d16b5f1dbff3','619e0886-401e-57c8-94c5-f50c9bafaa93','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('2648475f-cf39-5c43-a694-d16b5f1dbff3','5d71ecb7-3266-5f4b-8d8d-d13c304c313d','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('6b92182f-bcc5-51f7-a4cc-25fef50ee49b','acme','HR-LEAVE','内部学习用年假申请流程','内部学习用年假申请流程

年假余额以 HR 系统显示为准，本文不定义法定天数。连续休假 3 个工作日及以下由直属主管审批；超过 3 个工作日需部门负责人审批。原则上提前 5 个工作日申请，紧急情况补充原因说明。项目交接清单须在休假前提交。

structured_data.余额来源: "HR系统"
structured_data.常规提前申请工作日: 5','{"external_id": "HR-LEAVE", "title": "内部学习用年假申请流程", "business_module": "hr", "doc_type": "process", "source": "人力资源部/假期操作说明", "tags": ["module:hr", "audience:employee"], "metadata": {"section": "申请流程"}, "content": "年假余额以 HR 系统显示为准，本文不定义法定天数。连续休假 3 个工作日及以下由直属主管审批；超过 3 个工作日需部门负责人审批。原则上提前 5 个工作日申请，紧急情况补充原因说明。项目交接清单须在休假前提交。", "structured_data": {"常规提前申请工作日": 5, "余额来源": "HR系统"}}','{"section": "申请流程", "vector_fields": ["content", "structured_data"]}','hr','process',1,'1.0',true,'人力资源部/假期操作说明','b3f5b92541ba4093fee44287bf4182a6116934adcc6c5483b22a4e896256c2eb',ARRAY['module:hr','audience:employee']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('6b92182f-bcc5-51f7-a4cc-25fef50ee49b','619e0886-401e-57c8-94c5-f50c9bafaa93','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('6b92182f-bcc5-51f7-a4cc-25fef50ee49b','5d71ecb7-3266-5f4b-8d8d-d13c304c313d','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('27e34034-4e95-5a9c-b619-4677d63225fc','acme','HR-OFFBOARD','离职交接与账号停用','离职交接与账号停用

离职员工须完成业务文档、设备与客户联系人交接。IT 在最后工作日 18:00 停用交互登录，并移交业务共享资源所有权。管理员账号由安全团队在离职流程确认后优先回收。公司资产未归还应记录原因，不能通过保留员工登录权限解决交接问题。

structured_data.交接清单[0]: "电脑"
structured_data.交接清单[1]: "门禁卡"
structured_data.交接清单[2]: "文档所有权"
structured_data.交接清单[3]: "客户联系人"
structured_data.停用时间: "最后工作日18:00"','{"external_id": "HR-OFFBOARD", "title": "离职交接与账号停用", "business_module": "hr", "doc_type": "process", "source": "人力资源部/离职清单", "tags": ["module:hr", "module:it"], "metadata": {"section": "账号和资产"}, "content": "离职员工须完成业务文档、设备与客户联系人交接。IT 在最后工作日 18:00 停用交互登录，并移交业务共享资源所有权。管理员账号由安全团队在离职流程确认后优先回收。公司资产未归还应记录原因，不能通过保留员工登录权限解决交接问题。", "structured_data": {"停用时间": "最后工作日18:00", "交接清单": ["电脑", "门禁卡", "文档所有权", "客户联系人"]}}','{"section": "账号和资产", "vector_fields": ["content", "structured_data"]}','hr','process',1,'1.0',true,'人力资源部/离职清单','82b58318c6322bdc7c170d80d65d8c317ce042d514075e65f11e9b7c9cc7dbb6',ARRAY['module:hr','module:it']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('27e34034-4e95-5a9c-b619-4677d63225fc','5d71ecb7-3266-5f4b-8d8d-d13c304c313d','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('27e34034-4e95-5a9c-b619-4677d63225fc','7e903e8c-5ee9-50bc-9859-86377117224f','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('321919fa-cb89-5ad4-9085-71b0c117270d','acme','IT-VPN','VPN 开通与故障排查','VPN 开通与故障排查

VPN 开通需要直属主管审批和受管设备合规检查。登录必须启用多因素认证。错误码 VPN-403 表示账号没有远程访问授权，应提交 IT 工单；VPN-408 表示连接超时，先检查网络和客户端版本。不得通过共享他人账号临时访问。

structured_data.必需条件[0]: "主管审批"
structured_data.必需条件[1]: "受管设备"
structured_data.必需条件[2]: "多因素认证"
structured_data.错误码.VPN-403: "缺少授权"
structured_data.错误码.VPN-408: "连接超时"','{"external_id": "IT-VPN", "title": "VPN 开通与故障排查", "business_module": "it", "doc_type": "faq", "source": "IT服务台/VPN", "tags": ["module:it", "audience:employee"], "metadata": {"section": "远程接入"}, "content": "VPN 开通需要直属主管审批和受管设备合规检查。登录必须启用多因素认证。错误码 VPN-403 表示账号没有远程访问授权，应提交 IT 工单；VPN-408 表示连接超时，先检查网络和客户端版本。不得通过共享他人账号临时访问。", "structured_data": {"错误码": {"VPN-403": "缺少授权", "VPN-408": "连接超时"}, "必需条件": ["主管审批", "受管设备", "多因素认证"]}}','{"section": "远程接入", "vector_fields": ["content", "structured_data"]}','it','faq',1,'1.0',true,'IT服务台/VPN','d8014950625ca673978703c81dfdc4396deba3c66e04d14c3b886411d6888f97',ARRAY['module:it','audience:employee']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('321919fa-cb89-5ad4-9085-71b0c117270d','619e0886-401e-57c8-94c5-f50c9bafaa93','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('321919fa-cb89-5ad4-9085-71b0c117270d','7e903e8c-5ee9-50bc-9859-86377117224f','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('d3e8890b-a893-53be-b5c5-66ae48600525','acme','IT-ACCESS','业务系统权限申请及复核','业务系统权限申请及复核

业务权限按最小必要原则申请。普通权限由直属主管和系统负责人审批，生产管理员权限增加安全负责人审批。临时权限最长 7 个自然日，到期自动回收。所有权限每季度由系统负责人复核一次，不允许用知识库问答直接授予权限。

structured_data.临时权限上限天数: 7
structured_data.复核频率: "每季度"','{"external_id": "IT-ACCESS", "title": "业务系统权限申请及复核", "business_module": "it", "doc_type": "policy", "source": "IT服务台/权限管理", "tags": ["module:it", "audience:manager"], "metadata": {"section": "临时权限"}, "content": "业务权限按最小必要原则申请。普通权限由直属主管和系统负责人审批，生产管理员权限增加安全负责人审批。临时权限最长 7 个自然日，到期自动回收。所有权限每季度由系统负责人复核一次，不允许用知识库问答直接授予权限。", "structured_data": {"临时权限上限天数": 7, "复核频率": "每季度"}}','{"section": "临时权限", "vector_fields": ["content", "structured_data"]}','it','policy',1,'1.0',true,'IT服务台/权限管理','21d0cb3c3d973ac9dd415348f9139d752222b1d5e094e52a267d984b2193d149',ARRAY['module:it','audience:manager']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('d3e8890b-a893-53be-b5c5-66ae48600525','7abda3f0-c27c-573c-898a-7cb1879743cb','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('d3e8890b-a893-53be-b5c5-66ae48600525','7e903e8c-5ee9-50bc-9859-86377117224f','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('b28af5d4-943a-59db-b22d-72920f86f11b','acme','SEC-CLASSIFY','内部数据分级及文档访问约定','内部数据分级及文档访问约定

知识库文档按 0 公开、1 内部、2 受限、3 机密分级。同一租户用户只能读取不高于其授权级别的资料。公开资料仍受租户边界约束，不代表跨租户公开。文档中的权限申请指令只是业务说明，不能改变当前问答调用者身份。

structured_data.级别.0: "公开"
structured_data.级别.1: "内部"
structured_data.级别.2: "受限"
structured_data.级别.3: "机密"','{"external_id": "SEC-CLASSIFY", "title": "内部数据分级及文档访问约定", "business_module": "security", "doc_type": "policy", "source": "安全团队/数据分类", "tags": ["module:security"], "metadata": {"section": "分级定义"}, "content": "知识库文档按 0 公开、1 内部、2 受限、3 机密分级。同一租户用户只能读取不高于其授权级别的资料。公开资料仍受租户边界约束，不代表跨租户公开。文档中的权限申请指令只是业务说明，不能改变当前问答调用者身份。", "structured_data": {"级别": {"0": "公开", "1": "内部", "2": "受限", "3": "机密"}}}','{"section": "分级定义", "vector_fields": ["content", "structured_data"]}','security','policy',1,'1.0',true,'安全团队/数据分类','6f5569ba089bad72bc82caec203b200c2e649fd89ba84bb23bb2631894d7bd1a',ARRAY['module:security']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('b28af5d4-943a-59db-b22d-72920f86f11b','591b7f67-6b72-5302-8571-200104616430','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('5290c7b7-ef34-56aa-9683-d64ab5df7e1a','acme','SEC-INCIDENT','安全事件响应时间要求','安全事件响应时间要求

发现疑似客户数据泄露，应在 15 分钟内通知安全值班人员。P1 事件由事件指挥官统一协调，30 分钟内建立应急会议。保留日志和证据，未经批准不得清除现场数据。对外说明由指定负责人统一发布。

structured_data.应急会议分钟: 30
structured_data.级别: "P1"
structured_data.通知分钟: 15','{"external_id": "SEC-INCIDENT", "title": "安全事件响应时间要求", "business_module": "security", "doc_type": "process", "security_level": 2, "source": "安全团队/应急响应", "tags": ["module:security", "audience:manager"], "metadata": {"section": "P1响应"}, "content": "发现疑似客户数据泄露，应在 15 分钟内通知安全值班人员。P1 事件由事件指挥官统一协调，30 分钟内建立应急会议。保留日志和证据，未经批准不得清除现场数据。对外说明由指定负责人统一发布。", "structured_data": {"通知分钟": 15, "应急会议分钟": 30, "级别": "P1"}}','{"section": "P1响应", "vector_fields": ["content", "structured_data"]}','security','process',2,'1.0',true,'安全团队/应急响应','65e59021561ffa40da1e4b585eef71d1af99271d40ca0c812d28d9b587e51ba1',ARRAY['module:security','audience:manager']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('5290c7b7-ef34-56aa-9683-d64ab5df7e1a','7abda3f0-c27c-573c-898a-7cb1879743cb','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('5290c7b7-ef34-56aa-9683-d64ab5df7e1a','591b7f67-6b72-5302-8571-200104616430','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('4d98b026-da02-515c-913e-dc92a62eebf9','acme','BUY-THREE','采购询价与供应商选择规则','采购询价与供应商选择规则

单笔采购含税金额达到 3 万元，应取得至少三家有效报价。唯一来源采购需提交独家说明，由采购负责人及需求部门负责人共同批准。不得通过拆单规避比价门槛；同一项目七个自然日内的同类采购合并判断。

structured_data.合并判断自然日: 7
structured_data.最少报价家数: 3
structured_data.比价门槛元: 30000','{"external_id": "BUY-THREE", "title": "采购询价与供应商选择规则", "business_module": "procurement", "doc_type": "policy", "source": "采购部/采购制度", "tags": ["module:procurement"], "metadata": {"section": "比价门槛"}, "content": "单笔采购含税金额达到 3 万元，应取得至少三家有效报价。唯一来源采购需提交独家说明，由采购负责人及需求部门负责人共同批准。不得通过拆单规避比价门槛；同一项目七个自然日内的同类采购合并判断。", "structured_data": {"比价门槛元": 30000, "最少报价家数": 3, "合并判断自然日": 7}}','{"section": "比价门槛", "vector_fields": ["content", "structured_data"]}','procurement','policy',1,'1.0',true,'采购部/采购制度','cd270883fa09e92ea08fbe854fc37be7b4cee64b6c802bff73a4db160d50cb43',ARRAY['module:procurement']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('4d98b026-da02-515c-913e-dc92a62eebf9','dddb8901-70d7-5183-bc39-0fa741d45bc0','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('dd6ac53d-d9dc-59e7-ab6a-4fbc57088d8a','acme','BUY-ACCEPT','采购验收与分阶段付款模板','采购验收与分阶段付款模板

标准设备采购模板建议签约预付款 30%、到货初验 40%、最终验收 30%。最终验收需需求部门出具验收记录，涉及信息系统时增加 IT 测试报告。该比例仅用于新合同模板，已有合同必须按已签署条款执行。

structured_data.模板付款比例[0].百分比: 30
structured_data.模板付款比例[0].阶段: "签约"
structured_data.模板付款比例[1].百分比: 40
structured_data.模板付款比例[1].阶段: "到货初验"
structured_data.模板付款比例[2].百分比: 30
structured_data.模板付款比例[2].阶段: "最终验收"
structured_data.适用范围: "新签标准设备采购合同"','{"external_id": "BUY-ACCEPT", "title": "采购验收与分阶段付款模板", "business_module": "procurement", "doc_type": "template", "source": "采购部/标准合同附件", "tags": ["module:procurement", "module:finance"], "metadata": {"section": "验收付款"}, "content": "标准设备采购模板建议签约预付款 30%、到货初验 40%、最终验收 30%。最终验收需需求部门出具验收记录，涉及信息系统时增加 IT 测试报告。该比例仅用于新合同模板，已有合同必须按已签署条款执行。", "structured_data": {"模板付款比例": [{"阶段": "签约", "百分比": 30}, {"阶段": "到货初验", "百分比": 40}, {"阶段": "最终验收", "百分比": 30}], "适用范围": "新签标准设备采购合同"}}','{"section": "验收付款", "vector_fields": ["content", "structured_data"]}','procurement','template',1,'1.0',true,'采购部/标准合同附件','2c7ee97494f831e004cb11213680122a98603f3deaedffe971251e07fa0a5ad8',ARRAY['module:procurement','module:finance']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('dd6ac53d-d9dc-59e7-ab6a-4fbc57088d8a','2f08f532-61e6-5ccd-b182-c606364fdd40','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('dd6ac53d-d9dc-59e7-ab6a-4fbc57088d8a','dddb8901-70d7-5183-bc39-0fa741d45bc0','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('1d37dab0-d8ec-5c4e-b2bf-cb0cfbc222a4','acme','SALES-DISCOUNT','销售折扣审批规则','销售折扣审批规则

标准产品折扣小于 10% 由销售主管审批；10% 至 20% 含上限由销售总监审批；超过 20% 需要总经理审批。折扣按公开价与合同净价计算，不得把服务赠送隐藏在备注中规避审批。渠道合同另按渠道政策执行。

structured_data.排除: "渠道合同"
structured_data.适用: "标准产品直销"','{"external_id": "SALES-DISCOUNT", "title": "销售折扣审批规则", "business_module": "sales", "doc_type": "policy", "security_level": 2, "source": "销售运营/折扣授权", "tags": ["module:sales", "audience:manager"], "metadata": {"section": "标准产品"}, "content": "标准产品折扣小于 10% 由销售主管审批；10% 至 20% 含上限由销售总监审批；超过 20% 需要总经理审批。折扣按公开价与合同净价计算，不得把服务赠送隐藏在备注中规避审批。渠道合同另按渠道政策执行。", "structured_data": {"适用": "标准产品直销", "排除": "渠道合同"}}','{"section": "标准产品", "vector_fields": ["content", "structured_data"]}','sales','policy',2,'1.0',true,'销售运营/折扣授权','a9d9ce4a8024ded7dd4cf50298dc9e579c01387982ae6f7140df6aa552dae213',ARRAY['module:sales','audience:manager']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1d37dab0-d8ec-5c4e-b2bf-cb0cfbc222a4','7abda3f0-c27c-573c-898a-7cb1879743cb','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1d37dab0-d8ec-5c4e-b2bf-cb0cfbc222a4','aadcfbc3-056b-5a3d-987a-981da9fb53fa','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('3485abfa-db2c-5bb3-bfee-5b3bc487b786','acme','SUPPORT-SLA','企业客户工单 SLA','企业客户工单 SLA

企业版客户 P1 故障首次响应不超过 30 分钟，目标恢复时间为 4 小时；P2 首次响应不超过 2 小时，目标恢复时间为 1 个工作日。目标恢复时间不是赔偿承诺，赔偿以客户合同为准。计划维护窗口不计入可用性统计，但应提前 3 个工作日通知客户。

structured_data.P1.响应分钟: 30
structured_data.P1.目标恢复小时: 4
structured_data.P2.响应小时: 2
structured_data.P2.目标恢复工作日: 1','{"external_id": "SUPPORT-SLA", "title": "企业客户工单 SLA", "business_module": "support", "doc_type": "policy", "source": "客户支持/SLA", "tags": ["module:support"], "metadata": {"section": "企业版服务"}, "content": "企业版客户 P1 故障首次响应不超过 30 分钟，目标恢复时间为 4 小时；P2 首次响应不超过 2 小时，目标恢复时间为 1 个工作日。目标恢复时间不是赔偿承诺，赔偿以客户合同为准。计划维护窗口不计入可用性统计，但应提前 3 个工作日通知客户。", "structured_data": {"P1": {"响应分钟": 30, "目标恢复小时": 4}, "P2": {"响应小时": 2, "目标恢复工作日": 1}}}','{"section": "企业版服务", "vector_fields": ["content", "structured_data"]}','support','policy',1,'1.0',true,'客户支持/SLA','0fcef7439f0e6053d7d445c275b9d12f401b7be8e9c7821e2f67dd9d5938d448',ARRAY['module:support']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('3485abfa-db2c-5bb3-bfee-5b3bc487b786','6c46f4cf-ae69-545a-ab33-dcd8be179493','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('1c8d94b8-5d61-5ebf-b415-a48e5e313cbb','acme','REFUND-POLICY','订单退款规则','订单退款规则

未发货订单在付款后 24 小时内取消，可申请全额原路退款。已发货订单须先完成退货验收，验收通过后 3 个工作日内发起退款。支付渠道到账通常需要 1 至 5 个工作日。定制产品原则上不支持无理由退款，质量问题由售后评估。退款发起不等于客户已到账。

structured_data.例外: "定制产品质量问题需售后评估"
structured_data.未发货取消窗口小时: 24
structured_data.渠道到账工作日.最多: 5
structured_data.渠道到账工作日.最少: 1
structured_data.退货后发起工作日: 3','{"external_id": "REFUND-POLICY", "title": "订单退款规则", "business_module": "support", "doc_type": "policy", "source": "客户支持/退款规则", "tags": ["module:support"], "metadata": {"section": "未发货与已发货"}, "content": "未发货订单在付款后 24 小时内取消，可申请全额原路退款。已发货订单须先完成退货验收，验收通过后 3 个工作日内发起退款。支付渠道到账通常需要 1 至 5 个工作日。定制产品原则上不支持无理由退款，质量问题由售后评估。退款发起不等于客户已到账。", "structured_data": {"未发货取消窗口小时": 24, "退货后发起工作日": 3, "渠道到账工作日": {"最少": 1, "最多": 5}, "例外": "定制产品质量问题需售后评估"}}','{"section": "未发货与已发货", "vector_fields": ["content", "structured_data"]}','support','policy',1,'1.0',true,'客户支持/退款规则','b5714400d00ae2b772594a0b8fa27304aaca17adf6d02d44f96624f5e07a25f2',ARRAY['module:support']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('1c8d94b8-5d61-5ebf-b415-a48e5e313cbb','6c46f4cf-ae69-545a-ab33-dcd8be179493','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('68063fe4-8f95-552d-8f5c-89ac51cae081','acme','ORDER-A1001','订单 A1001 状态快照','订单 A1001 状态快照

订单 A1001 属于企业客户北辰设备，采购 12 套协作终端，总额 36000 元。已全额付款，预计 9 月 20 日发货，当前未发货且未申请退款。此资料为 2026 年 9 月 17 日快照，不能推断之后状态。

structured_data.总金额: 36000
structured_data.数量: 12
structured_data.状态: "待发货"
structured_data.订单号: "A1001"
structured_data.退款记录: null','{"external_id": "ORDER-A1001", "title": "订单 A1001 状态快照", "business_module": "sales", "doc_type": "record", "source": "ERP/订单/A1001", "tags": ["module:sales", "lifecycle:active"], "metadata": {"entity_ids": ["A1001"], "snapshot_at": "2026-09-17T10:00:00+08:00"}, "content": "订单 A1001 属于企业客户北辰设备，采购 12 套协作终端，总额 36000 元。已全额付款，预计 9 月 20 日发货，当前未发货且未申请退款。此资料为 2026 年 9 月 17 日快照，不能推断之后状态。", "structured_data": {"订单号": "A1001", "数量": 12, "总金额": 36000, "状态": "待发货", "退款记录": null}}','{"entity_ids": ["A1001"], "snapshot_at": "2026-09-17T10:00:00+08:00", "vector_fields": ["content", "structured_data"]}','sales','record',1,'1.0',true,'ERP/订单/A1001','385bab21fb2dc8b67b7623d0087a1010355a947dc6c3375865f7894950603942',ARRAY['module:sales','lifecycle:active']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('68063fe4-8f95-552d-8f5c-89ac51cae081','ec4cc6aa-9c63-544d-907d-d6393c4dee5d','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('68063fe4-8f95-552d-8f5c-89ac51cae081','aadcfbc3-056b-5a3d-987a-981da9fb53fa','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('3acd6b30-903d-5335-baf4-af1e2b0d8c4d','acme','ORDER-A1002','订单 A1002 及退款关联快照','订单 A1002 及退款关联快照

订单 A1002 金额 12800 元，因项目取消已取消交付，关联退款申请 R1001。退款已由财务审批并提交支付渠道，尚未收到到账确认。需要引用退款 R1001 的渠道状态区分提交成功和到账成功。

structured_data.关联退款号: "R1001"
structured_data.币种: "CNY"
structured_data.应退金额: 12800
structured_data.订单号: "A1002"
structured_data.订单状态: "已取消"','{"external_id": "ORDER-A1002", "title": "订单 A1002 及退款关联快照", "business_module": "sales", "doc_type": "record", "source": "ERP/订单/A1002", "tags": ["module:sales", "lifecycle:closed"], "metadata": {"entity_ids": ["A1002", "R1001"], "snapshot_at": "2026-09-17T10:00:00+08:00"}, "content": "订单 A1002 金额 12800 元，因项目取消已取消交付，关联退款申请 R1001。退款已由财务审批并提交支付渠道，尚未收到到账确认。需要引用退款 R1001 的渠道状态区分提交成功和到账成功。", "structured_data": {"订单号": "A1002", "关联退款号": "R1001", "订单状态": "已取消", "应退金额": 12800, "币种": "CNY"}}','{"entity_ids": ["A1002", "R1001"], "snapshot_at": "2026-09-17T10:00:00+08:00", "vector_fields": ["content", "structured_data"]}','sales','record',1,'1.0',true,'ERP/订单/A1002','a0cba1e8d2d89fbb80716e886fbea53a7341a2a6cf424f5adfa05fe5dfbf9c73',ARRAY['module:sales','lifecycle:closed']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('3acd6b30-903d-5335-baf4-af1e2b0d8c4d','6f92b41a-7e0e-56da-9ab5-fa9bc24fd38f','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('3acd6b30-903d-5335-baf4-af1e2b0d8c4d','aadcfbc3-056b-5a3d-987a-981da9fb53fa','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('699e657f-b0b5-54ee-ab0e-eaa95e249c44','acme','REFUND-R1001','退款 R1001 处理进度快照','退款 R1001 处理进度快照

退款 R1001 对应订单 A1002，金额 12800 元，于 2026 年 9 月 16 日 14:30 提交原支付渠道。当前状态为渠道处理中，不是退款失败，也不是已到账。通常 1 至 5 个工作日到账，超过 5 个工作日由售后创建渠道追踪工单。

structured_data.状态: "渠道处理中"
structured_data.订单号: "A1002"
structured_data.退款号: "R1001"
structured_data.金额: 12800
structured_data.预计到账工作日[0]: 1
structured_data.预计到账工作日[1]: 5','{"external_id": "REFUND-R1001", "title": "退款 R1001 处理进度快照", "business_module": "support", "doc_type": "record", "source": "售后系统/退款/R1001", "tags": ["module:support", "lifecycle:active"], "metadata": {"entity_ids": ["R1001", "A1002"], "snapshot_at": "2026-09-17T10:00:00+08:00"}, "content": "退款 R1001 对应订单 A1002，金额 12800 元，于 2026 年 9 月 16 日 14:30 提交原支付渠道。当前状态为渠道处理中，不是退款失败，也不是已到账。通常 1 至 5 个工作日到账，超过 5 个工作日由售后创建渠道追踪工单。", "structured_data": {"退款号": "R1001", "订单号": "A1002", "金额": 12800, "状态": "渠道处理中", "预计到账工作日": [1, 5]}}','{"entity_ids": ["R1001", "A1002"], "snapshot_at": "2026-09-17T10:00:00+08:00", "vector_fields": ["content", "structured_data"]}','support','record',1,'1.0',true,'售后系统/退款/R1001','743d9a56ca6fecd276c09530a740475b297d026ee26fc53e32ef6d52504964b8',ARRAY['module:support','lifecycle:active']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('699e657f-b0b5-54ee-ab0e-eaa95e249c44','ec4cc6aa-9c63-544d-907d-d6393c4dee5d','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('699e657f-b0b5-54ee-ab0e-eaa95e249c44','6c46f4cf-ae69-545a-ab33-dcd8be179493','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('b73de595-4b32-54fb-8050-3ce05a72eafc','acme','REFUND-R1002','退款 R1002 失败原因快照','退款 R1002 失败原因快照

退款 R1002 对应订单 A1003，金额 5200 元。支付渠道返回 BANK_ACCOUNT_CLOSED，表示原收款账户已注销。售后应联系客户通过实名认证提交新账户，再由财务复核并线下付款。不得直接把客户聊天中提供的账号作为付款依据。

structured_data.状态: "失败待人工复核"
structured_data.订单号: "A1003"
structured_data.退款号: "R1002"
structured_data.金额: 5200
structured_data.错误码: "BANK_ACCOUNT_CLOSED"','{"external_id": "REFUND-R1002", "title": "退款 R1002 失败原因快照", "business_module": "support", "doc_type": "record", "source": "售后系统/退款/R1002", "tags": ["module:support", "lifecycle:active"], "metadata": {"entity_ids": ["R1002", "A1003"], "snapshot_at": "2026-09-17T10:00:00+08:00"}, "content": "退款 R1002 对应订单 A1003，金额 5200 元。支付渠道返回 BANK_ACCOUNT_CLOSED，表示原收款账户已注销。售后应联系客户通过实名认证提交新账户，再由财务复核并线下付款。不得直接把客户聊天中提供的账号作为付款依据。", "structured_data": {"退款号": "R1002", "订单号": "A1003", "错误码": "BANK_ACCOUNT_CLOSED", "金额": 5200, "状态": "失败待人工复核"}}','{"entity_ids": ["R1002", "A1003"], "snapshot_at": "2026-09-17T10:00:00+08:00", "vector_fields": ["content", "structured_data"]}','support','record',1,'1.0',true,'售后系统/退款/R1002','a25c6a5f701e69785b4b4fedfeeab4adbc01e4f1602ecc27c5c8c403d46a141e',ARRAY['module:support','lifecycle:active']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('b73de595-4b32-54fb-8050-3ce05a72eafc','ec4cc6aa-9c63-544d-907d-d6393c4dee5d','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('b73de595-4b32-54fb-8050-3ce05a72eafc','6c46f4cf-ae69-545a-ab33-dcd8be179493','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('9fe90fea-4e27-5651-be64-e49820cf5528','acme','OPS-BACKUP','业务数据备份与恢复演练','业务数据备份与恢复演练

订单系统每日凌晨 02:00 执行全量备份，每 15 分钟归档一次日志。备份保留 30 天，每月执行一次隔离环境恢复演练。备份成功日志不能替代恢复验证。此条规定不授权知识库助手直接操作数据库或删除备份。

structured_data.保留天数: 30
structured_data.全量时间: "02:00"
structured_data.日志间隔分钟: 15
structured_data.演练频率: "每月"','{"external_id": "OPS-BACKUP", "title": "业务数据备份与恢复演练", "business_module": "it", "doc_type": "policy", "security_level": 2, "source": "运维部/备份规范", "tags": ["module:it", "audience:manager"], "metadata": {"section": "订单系统"}, "content": "订单系统每日凌晨 02:00 执行全量备份，每 15 分钟归档一次日志。备份保留 30 天，每月执行一次隔离环境恢复演练。备份成功日志不能替代恢复验证。此条规定不授权知识库助手直接操作数据库或删除备份。", "structured_data": {"全量时间": "02:00", "日志间隔分钟": 15, "保留天数": 30, "演练频率": "每月"}}','{"section": "订单系统", "vector_fields": ["content", "structured_data"]}','it','policy',2,'1.0',true,'运维部/备份规范','f55376af7a061ae56510daa1fd044c9182efab62cf8b27617c29614929b8e1f3',ARRAY['module:it','audience:manager']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('9fe90fea-4e27-5651-be64-e49820cf5528','7abda3f0-c27c-573c-898a-7cb1879743cb','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('9fe90fea-4e27-5651-be64-e49820cf5528','7e903e8c-5ee9-50bc-9859-86377117224f','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('35801c5c-7725-5b89-b134-d2a1efcb3735','acme','LEGAL-NDA','保密协议模板使用说明','保密协议模板使用说明

向外部供应商提供非公开技术资料前，应完成双方保密协议签署。模板条款发生任何修改均须法务审核。签署主体应与实际合作合同主体一致，不能使用部门名替代公司全称。具体保密期限以签署协议为准，本文不设统一期限。

structured_data.审核触发: "任何模板条款修改"
structured_data.必需动作: "提供资料前完成双方签署"','{"external_id": "LEGAL-NDA", "title": "保密协议模板使用说明", "business_module": "legal", "doc_type": "template", "source": "法务部/NDA模板说明", "tags": ["module:legal"], "metadata": {"section": "签署流程"}, "content": "向外部供应商提供非公开技术资料前，应完成双方保密协议签署。模板条款发生任何修改均须法务审核。签署主体应与实际合作合同主体一致，不能使用部门名替代公司全称。具体保密期限以签署协议为准，本文不设统一期限。", "structured_data": {"审核触发": "任何模板条款修改", "必需动作": "提供资料前完成双方签署"}}','{"section": "签署流程", "vector_fields": ["content", "structured_data"]}','legal','template',1,'1.0',true,'法务部/NDA模板说明','2ce5083cafc36b828a09259631dbb69232bc50872bf9ca8233c1a9bd90455f1c',ARRAY['module:legal']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('35801c5c-7725-5b89-b134-d2a1efcb3735','b567ad85-64bf-5675-8f1b-236fbf797e4c','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('05dc7d72-5192-5218-91da-b1553d8a3d20','acme','PRODUCT-API','企业 API 限流与重试规范','企业 API 限流与重试规范

企业标准套餐每个租户每分钟最多 600 次 API 请求。返回 HTTP 429 时应读取 Retry-After，并使用指数退避和随机抖动。写请求重试必须提供相同的 Idempotency-Key；查询请求可直接重试。批处理任务应避开整点集中提交。

structured_data.幂等请求头: "Idempotency-Key"
structured_data.每分钟请求上限: 600
structured_data.限流状态码: 429','{"external_id": "PRODUCT-API", "title": "企业 API 限流与重试规范", "business_module": "product", "doc_type": "reference", "source": "产品文档/API接入", "security_level": 0, "tags": ["module:product"], "metadata": {"section": "限流"}, "content": "企业标准套餐每个租户每分钟最多 600 次 API 请求。返回 HTTP 429 时应读取 Retry-After，并使用指数退避和随机抖动。写请求重试必须提供相同的 Idempotency-Key；查询请求可直接重试。批处理任务应避开整点集中提交。", "structured_data": {"每分钟请求上限": 600, "限流状态码": 429, "幂等请求头": "Idempotency-Key"}}','{"section": "限流", "vector_fields": ["content", "structured_data"]}','product','reference',0,'1.0',true,'产品文档/API接入','52c283b4dcf2453b1928c5a6ec3434a3febc59e3f1ab5a5e2925735c19eea30e',ARRAY['module:product']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('05dc7d72-5192-5218-91da-b1553d8a3d20','8eceb1d2-9abd-5936-b9de-735cc58badeb','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('c45c01ac-574e-53c0-9476-0a97a15f1279','acme','KB-MAINTAIN','知识库发布与文档版本维护规范','知识库发布与文档版本维护规范

同一业务文档每个租户只能存在一个最新版本。新版本通过审核并完成切分向量化后才能参与问答，旧版本保留用于追溯。结构化业务字段以 JSON 原文保存，选择参与向量化的字段须记录在 vector_fields 中。修改切分参数或向量模型后应创建新版本并重新生成全部子块。

structured_data.发布前检查[0]: "内容审核"
structured_data.发布前检查[1]: "切分完成"
structured_data.发布前检查[2]: "向量维度一致"
structured_data.发布前检查[3]: "来源可追溯"
structured_data.最新版本数量: 1','{"external_id": "KB-MAINTAIN", "title": "知识库发布与文档版本维护规范", "business_module": "it", "doc_type": "process", "source": "知识管理/发布规范", "tags": ["module:it"], "metadata": {"section": "版本发布"}, "content": "同一业务文档每个租户只能存在一个最新版本。新版本通过审核并完成切分向量化后才能参与问答，旧版本保留用于追溯。结构化业务字段以 JSON 原文保存，选择参与向量化的字段须记录在 vector_fields 中。修改切分参数或向量模型后应创建新版本并重新生成全部子块。", "structured_data": {"发布前检查": ["内容审核", "切分完成", "向量维度一致", "来源可追溯"], "最新版本数量": 1}}','{"section": "版本发布", "vector_fields": ["content", "structured_data"]}','it','process',1,'1.0',true,'知识管理/发布规范','7c2f673efeedff685a0d14de0fbcf34332a3a22f36524bd4aac8f3fd7307acc9',ARRAY['module:it']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('c45c01ac-574e-53c0-9476-0a97a15f1279','7e903e8c-5ee9-50bc-9859-86377117224f','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('d4169161-d283-5496-892f-4368abd11f17','acme','FIN-BUDGET-SECRET','星河科技专项预算审批记录','星河科技专项预算审批记录

内部虚构验证数据：星河科技 2027 年极光专项批准预算为 860 万元。仅授权级别 3 可读取。普通内部员工不应通过语义检索、关键词检索或引用摘要看到此金额。

structured_data.年度: 2027
structured_data.项目: "极光"
structured_data.预算万元: 860','{"external_id": "FIN-BUDGET-SECRET", "title": "星河科技专项预算审批记录", "business_module": "finance", "doc_type": "record", "security_level": 3, "source": "财务部/专项预算/机密", "tags": ["module:finance", "audience:manager"], "metadata": {"section": "预算审批"}, "content": "内部虚构验证数据：星河科技 2027 年极光专项批准预算为 860 万元。仅授权级别 3 可读取。普通内部员工不应通过语义检索、关键词检索或引用摘要看到此金额。", "structured_data": {"项目": "极光", "年度": 2027, "预算万元": 860}}','{"section": "预算审批", "vector_fields": ["content", "structured_data"]}','finance','record',3,'1.0',true,'财务部/专项预算/机密','11b28bb28d915bd77900376bcdf4d6f29ec0811aa53df5aeb3162190469aca79',ARRAY['module:finance','audience:manager']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('d4169161-d283-5496-892f-4368abd11f17','7abda3f0-c27c-573c-898a-7cb1879743cb','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('d4169161-d283-5496-892f-4368abd11f17','2f08f532-61e6-5ccd-b182-c606364fdd40','acme') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('711bfb90-aa17-5a85-95b0-bba1ceff5c44','beta','FIN-TRAVEL','远帆公司差旅住宿制度','远帆公司差旅住宿制度

远帆公司 beta 的境内出差住宿统一上限为每人每晚 900 元，无一线和非一线城市区分。此标准不适用于星河科技 acme。

structured_data.每晚住宿上限元: 900
structured_data.租户: "beta"','{"external_id": "FIN-TRAVEL", "title": "远帆公司差旅住宿制度", "tenant_id": "beta", "business_module": "finance", "doc_type": "policy", "version": "2026.1", "security_level": 1, "source": "远帆财务部/差旅政策", "tags": ["module:finance-travel", "region:cn"], "metadata": {"section": "住宿标准"}, "content": "远帆公司 beta 的境内出差住宿统一上限为每人每晚 900 元，无一线和非一线城市区分。此标准不适用于星河科技 acme。", "structured_data": {"每晚住宿上限元": 900, "租户": "beta"}}','{"section": "住宿标准", "vector_fields": ["content", "structured_data"]}','finance','policy',1,'2026.1',true,'远帆财务部/差旅政策','8f1061b15ef7db8976fef139675d810ebe328c390a997c3e582b66dbdb96a28c',ARRAY['module:finance-travel','region:cn']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('711bfb90-aa17-5a85-95b0-bba1ceff5c44','0755dd2c-ad11-50cc-8e45-db79de4a70a6','beta') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('711bfb90-aa17-5a85-95b0-bba1ceff5c44','94c6e75b-3275-5679-9f27-1f5b959c9c4d','beta') ON CONFLICT DO NOTHING;
INSERT INTO public.kb_documents (id,tenant_id,external_id,title,content,payload,metadata,business_module,doc_type,security_level,version,is_latest,source,content_hash,tags) VALUES ('b41fd96c-8e2f-5ef0-bdb8-d43854b06edc','beta','ORDER-A1002','远帆公司订单 A1002 状态','远帆公司订单 A1002 状态

远帆公司 beta 的订单 A1002 金额为 77000 元，状态已签收，没有退款。虽然编号与 acme 相同，资料仍属于不同租户，不能交叉引用。

structured_data.状态: "已签收"
structured_data.订单号: "A1002"
structured_data.退款: false
structured_data.金额: 77000','{"external_id": "ORDER-A1002", "title": "远帆公司订单 A1002 状态", "tenant_id": "beta", "business_module": "sales", "doc_type": "record", "security_level": 1, "source": "远帆ERP/订单/A1002", "tags": ["module:sales"], "metadata": {"entity_ids": ["A1002"], "snapshot_at": "2026-09-17T10:00:00+08:00"}, "content": "远帆公司 beta 的订单 A1002 金额为 77000 元，状态已签收，没有退款。虽然编号与 acme 相同，资料仍属于不同租户，不能交叉引用。", "structured_data": {"订单号": "A1002", "金额": 77000, "状态": "已签收", "退款": false}}','{"entity_ids": ["A1002"], "snapshot_at": "2026-09-17T10:00:00+08:00", "vector_fields": ["content", "structured_data"]}','sales','record',1,'1.0',true,'远帆ERP/订单/A1002','a6a1c66429bd522a826b1a46279f0ddddce78b1dbb7f559a84f604adb37e2901',ARRAY['module:sales']::text[]) ON CONFLICT (tenant_id,external_id,version) DO NOTHING;
INSERT INTO public.kb_document_tags (document_id,tag_id,tenant_id) VALUES ('b41fd96c-8e2f-5ef0-bdb8-d43854b06edc','52e5e297-3138-51f1-a0a3-4188a4888daa','beta') ON CONFLICT DO NOTHING;
COMMIT;
