-- 仅供用户在 ragdb 数据库中审阅并手动执行；本文件不会被程序自动执行。
-- 本脚本仅新建独立的 biz schema 及三张业务演示表，不修改 public.kb_* 六张知识库表。
-- 目标：PostgreSQL 16；金额使用精确数值 numeric(12, 2)，时间使用带时区的 timestamptz。
BEGIN;

-- 新建独立业务命名空间，与 public 下的知识库表隔离。
CREATE SCHEMA IF NOT EXISTS biz;

-- 订单表：同一租户内订单号唯一，保存订单状态、金额与最后更新时间。
CREATE TABLE biz.orders (
    tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''), -- 租户标识，例如 acme、other；查询必须按租户过滤。
    order_id text NOT NULL CHECK (btrim(order_id) <> ''), -- 订单编号，例如 A1002；同租户内唯一。
    status text NOT NULL CHECK (btrim(status) <> ''), -- 订单状态原文，例如 待支付、已支付、已完成、已取消。
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0), -- 订单金额，精确到分，避免浮点误差。
    currency text NOT NULL CHECK (btrim(currency) <> ''), -- 币种代码，例如 CNY。
    updated_at timestamptz NOT NULL, -- 订单状态的最后更新时间，含时区。
    PRIMARY KEY (tenant_id, order_id)
);

-- 支付记录表：同一订单可有多条支付尝试记录，通过复合外键约束同租户关联。
CREATE TABLE biz.payments (
    tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''), -- 租户标识，必须与关联订单一致。
    payment_id text NOT NULL CHECK (btrim(payment_id) <> ''), -- 支付记录编号，例如 P10021；同租户内唯一。
    order_id text NOT NULL CHECK (btrim(order_id) <> ''), -- 关联订单编号，必须属于同一租户。
    status text NOT NULL CHECK (btrim(status) <> ''), -- 支付状态原文，例如 支付成功、支付失败。
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0), -- 本笔支付金额，精确到分。
    currency text NOT NULL CHECK (btrim(currency) <> ''), -- 币种代码，例如 CNY。
    method text NOT NULL CHECK (btrim(method) <> ''), -- 支付方式，例如 支付宝、微信支付、银行卡。
    updated_at timestamptz NOT NULL, -- 本笔支付记录的更新时间，含时区。
    PRIMARY KEY (tenant_id, payment_id),
    UNIQUE (tenant_id, order_id, payment_id),
    FOREIGN KEY (tenant_id, order_id) REFERENCES biz.orders (tenant_id, order_id)
);

-- 按租户、订单号与确定排序建索引，支持按订单查询全部支付记录。
CREATE INDEX biz_payments_tenant_order
    ON biz.payments (tenant_id, order_id, updated_at, payment_id);

-- 退款记录表：同一订单可有多条退款记录；payment_id 可为空，非空时必须关联同租户同订单的支付记录。
CREATE TABLE biz.refunds (
    tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''), -- 租户标识，必须与关联订单一致。
    refund_id text NOT NULL CHECK (btrim(refund_id) <> ''), -- 退款记录编号，例如 R10021；同租户内唯一。
    order_id text NOT NULL CHECK (btrim(order_id) <> ''), -- 关联订单编号，必须属于同一租户。
    payment_id text CHECK (payment_id IS NULL OR btrim(payment_id) <> ''), -- 可选关联支付编号；允许为空，非空时须属于同一租户同一订单。
    status text NOT NULL CHECK (btrim(status) <> ''), -- 退款状态原文，例如 退款成功、退款中。
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0), -- 本笔退款金额，精确到分。
    currency text NOT NULL CHECK (btrim(currency) <> ''), -- 币种代码，例如 CNY。
    reason text NOT NULL CHECK (btrim(reason) <> ''), -- 退款原因说明。
    updated_at timestamptz NOT NULL, -- 本笔退款记录的更新时间，含时区。
    PRIMARY KEY (tenant_id, refund_id),
    FOREIGN KEY (tenant_id, order_id) REFERENCES biz.orders (tenant_id, order_id),
    FOREIGN KEY (tenant_id, order_id, payment_id) REFERENCES biz.payments (tenant_id, order_id, payment_id)
);

-- 按租户、订单号与确定排序建索引，支持按订单查询全部退款记录。
CREATE INDEX biz_refunds_tenant_order
    ON biz.refunds (tenant_id, order_id, updated_at, refund_id);

-- 以下备注会保存到数据库元数据中，便于在数据库工具中查看。
COMMENT ON SCHEMA biz IS '第 76 课业务演示表命名空间，与 public 下的知识库表隔离。';

COMMENT ON TABLE biz.orders IS '业务演示订单表：保存按租户隔离的订单状态、金额与更新时间。';
COMMENT ON COLUMN biz.orders.tenant_id IS '租户标识，例如 acme、other；查询必须按租户过滤。';
COMMENT ON COLUMN biz.orders.order_id IS '订单编号，例如 A1002；同租户内唯一。';
COMMENT ON COLUMN biz.orders.status IS '订单状态原文，例如 待支付、已支付、已完成、已取消。';
COMMENT ON COLUMN biz.orders.amount IS '订单金额，使用 numeric(12, 2) 精确保存。';
COMMENT ON COLUMN biz.orders.currency IS '币种代码，例如 CNY。';
COMMENT ON COLUMN biz.orders.updated_at IS '订单记录最后更新时间，含时区。';

COMMENT ON TABLE biz.payments IS '业务演示支付表：一个订单可有多条支付记录，受同租户订单外键约束。';
COMMENT ON COLUMN biz.payments.tenant_id IS '租户标识，必须与关联订单一致。';
COMMENT ON COLUMN biz.payments.payment_id IS '支付记录编号，例如 P10021；同租户内唯一。';
COMMENT ON COLUMN biz.payments.order_id IS '关联订单编号，必须属于同一租户。';
COMMENT ON COLUMN biz.payments.status IS '支付状态原文，例如 支付成功、支付失败。';
COMMENT ON COLUMN biz.payments.amount IS '本笔支付金额，使用 numeric(12, 2) 精确保存。';
COMMENT ON COLUMN biz.payments.currency IS '币种代码，例如 CNY。';
COMMENT ON COLUMN biz.payments.method IS '支付方式，例如 支付宝、微信支付、银行卡。';
COMMENT ON COLUMN biz.payments.updated_at IS '本笔支付记录的更新时间，含时区。';

COMMENT ON TABLE biz.refunds IS '业务演示退款表：一个订单可有多条退款记录，payment_id 允许为空。';
COMMENT ON COLUMN biz.refunds.tenant_id IS '租户标识，必须与关联订单一致。';
COMMENT ON COLUMN biz.refunds.refund_id IS '退款记录编号，例如 R10021；同租户内唯一。';
COMMENT ON COLUMN biz.refunds.order_id IS '关联订单编号，必须属于同一租户。';
COMMENT ON COLUMN biz.refunds.payment_id IS '可选关联支付编号；允许为空，非空时关联同租户同订单的支付记录。';
COMMENT ON COLUMN biz.refunds.status IS '退款状态原文，例如 退款成功、退款中。';
COMMENT ON COLUMN biz.refunds.amount IS '本笔退款金额，使用 numeric(12, 2) 精确保存。';
COMMENT ON COLUMN biz.refunds.currency IS '币种代码，例如 CNY。';
COMMENT ON COLUMN biz.refunds.reason IS '退款原因说明。';
COMMENT ON COLUMN biz.refunds.updated_at IS '本笔退款记录的更新时间，含时区。';

COMMIT;
