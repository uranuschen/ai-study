-- 仅供用户在手动执行 sql/05_business_schema.sql 之后审阅并手动执行；不会被程序自动执行。
-- 演示数据与 data/business_demo.json 保持一一对应，用于对照 json 与 postgres 两种数据源的查询行为。
-- 重复执行使用 ON CONFLICT DO NOTHING，不覆盖已手动修改的数据。
BEGIN;

-- 插入 6 条样例订单：包含 acme 与 other 同号订单 A1002，以及待支付、无支付记录、支付失败等场景。
INSERT INTO biz.orders (tenant_id, order_id, status, amount, currency, updated_at)
VALUES
    ('acme',  'A1001', '待支付', 199.00, 'CNY', '2026-09-28T09:00:00+08:00'),
    ('acme',  'A1002', '已支付', 299.00, 'CNY', '2026-09-28T09:05:00+08:00'),
    ('acme',  'A1003', '已完成', 499.00, 'CNY', '2026-09-28T09:10:00+08:00'),
    ('acme',  'A1004', '已支付',  88.00, 'CNY', '2026-09-28T09:20:00+08:00'),
    ('acme',  'A1005', '已支付',  59.00, 'CNY', '2026-09-28T09:25:00+08:00'),
    ('other', 'A1002', '已取消',  79.00, 'CNY', '2026-09-28T09:15:00+08:00')
ON CONFLICT (tenant_id, order_id) DO NOTHING;

-- 插入 5 条样例支付记录：A1002 在 acme 下有失败和成功两笔，other 下另有同号订单支付记录。
INSERT INTO biz.payments (tenant_id, payment_id, order_id, status, amount, currency, method, updated_at)
VALUES
    ('acme',  'P10020',   'A1002', '支付失败', 299.00, 'CNY', '银行卡',   '2026-09-28T09:03:00+08:00'),
    ('acme',  'P10021',   'A1002', '支付成功', 299.00, 'CNY', '支付宝',   '2026-09-28T09:05:00+08:00'),
    ('acme',  'P10031',   'A1003', '支付成功', 499.00, 'CNY', '微信支付', '2026-09-28T09:08:00+08:00'),
    ('acme',  'P10051',   'A1005', '支付失败',  59.00, 'CNY', '银行卡',   '2026-09-28T09:24:00+08:00'),
    ('other', 'POTHER21', 'A1002', '支付成功',  79.00, 'CNY', '微信支付', '2026-09-28T09:11:00+08:00')
ON CONFLICT (tenant_id, payment_id) DO NOTHING;

-- 插入 3 条样例退款记录：A1002 在 acme 下有两笔部分退款，other 下另有一笔退款。
INSERT INTO biz.refunds (tenant_id, refund_id, order_id, payment_id, status, amount, currency, reason, updated_at)
VALUES
    ('acme',  'R10021',   'A1002', 'P10021',   '退款成功', 99.00, 'CNY', '退回一件商品', '2026-09-28T10:00:00+08:00'),
    ('acme',  'R10022',   'A1002', 'P10021',   '退款中',   50.00, 'CNY', '申请部分退款', '2026-09-28T10:05:00+08:00'),
    ('other', 'ROTHER21', 'A1002', 'POTHER21', '退款成功', 79.00, 'CNY', '取消订单',     '2026-09-28T09:15:00+08:00')
ON CONFLICT (tenant_id, refund_id) DO NOTHING;

COMMIT;
