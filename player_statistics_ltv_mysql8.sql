-- 玩家维度数据统计 / 留存 / LTV 表设计
-- 说明：
-- 1. 不设计 dim_area / dim_system / dim_channel
-- 2. 统计主体以 player_id 为核心
-- 3. 汇总表全部可按事实表重算
-- 4. 留存 / LTV 使用长表，不使用 step_1/ltv_1 之类宽字段

SET NAMES utf8mb4;

-- 1. 玩家创角事实
-- 作为玩家 cohort 的起点。留存和 LTV 一般都从这里出发。
CREATE TABLE fact_player_register (
    player_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    register_time DATETIME(3) NOT NULL COMMENT '账号注册时间，可等于或早于创角时间',
    create_role_time DATETIME(3) NOT NULL COMMENT '创角时间，推荐作为玩家 cohort 起点',
    cohort_date DATE NOT NULL COMMENT 'DATE(create_role_time)',
    channel_code VARCHAR(64) NOT NULL COMMENT '创角时渠道快照',
    area_code VARCHAR(64) NOT NULL COMMENT '创角时区服快照',
    system_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '创角时系统快照',
    server_id BIGINT NULL COMMENT '创角时服务器',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (player_id),
    KEY idx_cohort_dim (cohort_date, channel_code, area_code, system_code),
    KEY idx_user_id (user_id),
    KEY idx_create_role_time (create_role_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家创角事实表';


-- 2. 玩家日活跃事实
-- 只保留“某玩家某天是否活跃”和活跃强度，用于重算留存和活跃统计。
CREATE TABLE fact_player_active_daily (
    stat_date DATE NOT NULL,
    player_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    channel_code VARCHAR(64) NOT NULL COMMENT '当天活跃事件渠道快照',
    area_code VARCHAR(64) NOT NULL COMMENT '当天活跃事件区服快照',
    system_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '当天活跃事件系统快照',
    server_id BIGINT NULL,
    login_count INT NOT NULL DEFAULT 0,
    active_minutes INT NOT NULL DEFAULT 0,
    first_login_time DATETIME(3) NULL,
    last_login_time DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (stat_date, player_id),
    KEY idx_player_date (player_id, stat_date),
    KEY idx_dim_date (channel_code, area_code, system_code, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家日活跃事实表';


-- 3. 玩家充值订单事实
-- LTV、充值人数、充值留存都从这里重算。
CREATE TABLE fact_player_recharge_order (
    order_id BIGINT NOT NULL,
    player_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    pay_time DATETIME(3) NOT NULL,
    pay_date DATE NOT NULL COMMENT 'DATE(pay_time)',
    channel_code VARCHAR(64) NOT NULL COMMENT '充值发生时渠道快照',
    area_code VARCHAR(64) NOT NULL COMMENT '充值发生时区服快照',
    system_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '充值发生时系统快照',
    server_id BIGINT NULL,
    amount_cent BIGINT NOT NULL COMMENT '金额，单位分',
    currency_code VARCHAR(16) NOT NULL DEFAULT 'CNY',
    order_status TINYINT NOT NULL COMMENT '1=成功，其它=失败/关闭/退款前状态',
    is_first_pay TINYINT NOT NULL DEFAULT 0 COMMENT '是否该玩家首充订单，可离线维护',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (order_id),
    KEY idx_player_pay_date (player_id, pay_date),
    KEY idx_pay_date_dim (pay_date, channel_code, area_code, system_code),
    KEY idx_first_pay (is_first_pay, pay_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家充值订单事实表';


-- 4. 玩家基础统计汇总
-- 供运营后台快速查看新增、活跃、付费、收入等基础指标。
CREATE TABLE ads_player_stat (
    id BIGINT NOT NULL AUTO_INCREMENT,
    stat_granularity TINYINT NOT NULL COMMENT '1=分钟 2=小时 3=天 4=周 5=月',
    stat_time DATETIME(0) NOT NULL COMMENT '统计时间桶起点',
    stat_date DATE NOT NULL COMMENT '统计日期',
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    new_player_num INT NOT NULL DEFAULT 0 COMMENT '新增创角数',
    active_player_num INT NOT NULL DEFAULT 0 COMMENT '活跃玩家数',
    old_active_player_num INT NOT NULL DEFAULT 0 COMMENT '老活跃玩家数',
    pay_player_num INT NOT NULL DEFAULT 0 COMMENT '当日付费玩家数',
    first_pay_player_num INT NOT NULL DEFAULT 0 COMMENT '首充玩家数',
    recharge_order_num INT NOT NULL DEFAULT 0 COMMENT '成功充值订单数',
    recharge_amount_cent BIGINT NOT NULL DEFAULT 0 COMMENT '成功充值总金额',
    total_active_minutes BIGINT NOT NULL DEFAULT 0 COMMENT '总活跃分钟',
    max_active_minutes INT NOT NULL DEFAULT 0 COMMENT '最大单玩家活跃分钟',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_granularity_time_dim (stat_granularity, stat_time, channel_code, area_code, system_code),
    KEY idx_stat_date_dim (stat_date, channel_code, area_code, system_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家基础统计汇总表';


-- 5. 玩家留存汇总
-- cohort 主体固定为“创角玩家”。
CREATE TABLE ads_player_retention_cohort (
    id BIGINT NOT NULL AUTO_INCREMENT,
    cohort_type VARCHAR(32) NOT NULL DEFAULT 'create_role' COMMENT '当前固定 create_role，未来可扩展 register/first_pay',
    cohort_date DATE NOT NULL COMMENT 'cohort 日期',
    retention_day SMALLINT NOT NULL COMMENT '第 N 天留存，如 1/3/7/15/30',
    channel_code VARCHAR(64) NOT NULL COMMENT '按创角时归因',
    area_code VARCHAR(64) NOT NULL COMMENT '按创角时归因',
    system_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '按创角时归因',
    cohort_player_num INT NOT NULL DEFAULT 0 COMMENT 'cohort 玩家基数',
    retained_player_num INT NOT NULL DEFAULT 0 COMMENT '第 N 天仍活跃的玩家数',
    retention_rate DECIMAL(10,6) NOT NULL DEFAULT 0 COMMENT 'retained_player_num / cohort_player_num',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_cohort_day_dim (cohort_type, cohort_date, retention_day, channel_code, area_code, system_code),
    KEY idx_cohort_dim (cohort_date, channel_code, area_code, system_code),
    KEY idx_retention_day (retention_day, cohort_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家留存 cohort 汇总表';


-- 6. 玩家充值留存汇总
-- cohort 主体为“某天成功付费玩家”，看后续第 N 天是否再次付费。
CREATE TABLE ads_player_recharge_retention_cohort (
    id BIGINT NOT NULL AUTO_INCREMENT,
    cohort_type VARCHAR(32) NOT NULL DEFAULT 'pay_day' COMMENT '当前固定 pay_day，未来可扩展 first_pay',
    cohort_date DATE NOT NULL COMMENT '付费 cohort 日期',
    retention_day SMALLINT NOT NULL COMMENT '第 N 天充值留存',
    channel_code VARCHAR(64) NOT NULL COMMENT '按 cohort 当天付费归因',
    area_code VARCHAR(64) NOT NULL COMMENT '按 cohort 当天付费归因',
    system_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '按 cohort 当天付费归因',
    cohort_player_num INT NOT NULL DEFAULT 0 COMMENT 'cohort 付费玩家数',
    retained_pay_player_num INT NOT NULL DEFAULT 0 COMMENT '第 N 天再次付费玩家数',
    retention_rate DECIMAL(10,6) NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_cohort_day_dim (cohort_type, cohort_date, retention_day, channel_code, area_code, system_code),
    KEY idx_cohort_dim (cohort_date, channel_code, area_code, system_code),
    KEY idx_retention_day (retention_day, cohort_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家充值留存 cohort 汇总表';


-- 7. 玩家 LTV 汇总
-- cohort 主体固定为创角玩家；收入按该 cohort 后续充值累计。
CREATE TABLE ads_player_ltv_cohort (
    id BIGINT NOT NULL AUTO_INCREMENT,
    cohort_type VARCHAR(32) NOT NULL DEFAULT 'create_role' COMMENT '当前固定 create_role',
    cohort_date DATE NOT NULL,
    ltv_day SMALLINT NOT NULL COMMENT '第 N 天 LTV',
    channel_code VARCHAR(64) NOT NULL COMMENT '按创角时归因',
    area_code VARCHAR(64) NOT NULL COMMENT '按创角时归因',
    system_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '按创角时归因',
    cohort_player_num INT NOT NULL DEFAULT 0 COMMENT 'cohort 玩家数',
    pay_player_num INT NOT NULL DEFAULT 0 COMMENT '第 N 天有付费的去重玩家数',
    revenue_cent BIGINT NOT NULL DEFAULT 0 COMMENT '第 N 天当天收入',
    cumulative_revenue_cent BIGINT NOT NULL DEFAULT 0 COMMENT '从 D0 到 Dn 累计收入',
    ltv_amount DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '累计收入 / cohort_player_num / 100',
    arpu_amount DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '当天收入 / cohort_player_num / 100',
    arppu_amount DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '当天收入 / pay_player_num / 100',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_cohort_day_dim (cohort_type, cohort_date, ltv_day, channel_code, area_code, system_code),
    KEY idx_cohort_dim (cohort_date, channel_code, area_code, system_code),
    KEY idx_ltv_day (ltv_day, cohort_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家 LTV cohort 汇总表';


-- 8. 推荐口径说明
-- ads_player_retention_cohort:
--   cohort 玩家 = 某天创角的 player_id 集合
--   retained 玩家 = 第 N 天在 fact_player_active_daily 中出现过的 player_id
--
-- ads_player_recharge_retention_cohort:
--   cohort 玩家 = 某天成功付费 player_id 去重集合
--   retained_pay 玩家 = 第 N 天再次成功付费 player_id 去重集合
--
-- ads_player_ltv_cohort:
--   cohort 玩家 = 某天创角的 player_id 集合
--   收入 = 这些 player_id 后续在 fact_player_recharge_order 中的成功充值金额
--
-- 9. 推荐补算方式
-- 1. 按 cohort_date 删除汇总表对应数据
-- 2. 从事实表重新聚合
-- 3. INSERT ... ON DUPLICATE KEY UPDATE 回写
--
-- 10. 推荐保留周期
-- fact_player_register: 长期保留
-- fact_player_active_daily: 建议长期保留，至少保留大于最大留存周期
-- fact_player_recharge_order: 长期保留
