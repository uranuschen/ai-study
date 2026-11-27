-- 仅供用户审阅并手动执行；不会被程序自动执行。
-- 作用：对已创建的业务只读角色 biz_ro 授予 biz 三张表的最小 SELECT 权限，与知识库只读角色 codex_ro 严格隔离。
--
-- 【首次部署必读：先手动完成前置建角色步骤】
-- 为避免把示例占位符误当成真实数据库密码，本脚本不自动执行 CREATE ROLE。
-- 若环境中尚未创建 biz_ro，请先由管理员（如 postgres）在 ragdb 中单独执行下面这一条（替换为你自己的强密码）：
--
--     CREATE ROLE biz_ro LOGIN PASSWORD '<请替换为你自己的强密码>';
--
-- 创建好 biz_ro 后，再由表所有者或管理员执行本脚本完成最小权限授权。

-- 1. 前置检查：若 biz_ro 尚未创建，立即给出清晰中文提示并中止，避免首条 GRANT 直接报模糊错误。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'biz_ro') THEN
        RAISE EXCEPTION '角色 biz_ro 尚未创建；请先由管理员手动执行 CREATE ROLE biz_ro LOGIN PASSWORD ''<替换为你的强密码>''; 后再运行本授权脚本。';
    END IF;
END $$;

-- 2. 仅授予连接 ragdb、访问 biz schema 以及查询三张业务表的权限。
-- 不授予 INSERT / UPDATE / DELETE / TRUNCATE / CREATE，也不授予 public.kb_* 六张知识库表权限。
BEGIN;

GRANT CONNECT ON DATABASE ragdb TO biz_ro;
GRANT USAGE ON SCHEMA biz TO biz_ro;
GRANT SELECT ON biz.orders, biz.payments, biz.refunds TO biz_ro;

COMMIT;

-- 3. 手动核对查询（用户使用 biz_ro 登录后自行执行）：
-- SELECT current_user, current_database();
-- SELECT tenant_id, count(*) FROM biz.orders GROUP BY tenant_id ORDER BY tenant_id;
-- SELECT tenant_id, count(*) FROM biz.payments GROUP BY tenant_id ORDER BY tenant_id;
-- SELECT tenant_id, count(*) FROM biz.refunds GROUP BY tenant_id ORDER BY tenant_id;
-- SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'biz' ORDER BY tablename, indexname;
-- 预期拒绝（验证权限隔离）：
-- SELECT count(*) FROM public.kb_documents;
-- INSERT INTO biz.orders (tenant_id, order_id, status, amount, currency, updated_at)
-- VALUES ('acme', 'TEST1', '待支付', 1.00, 'CNY', now());
