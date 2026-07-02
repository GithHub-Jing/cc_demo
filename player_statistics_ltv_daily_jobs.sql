-- 玩家统计 / 留存 / LTV 每日作业 SQL
-- 目标：
-- 1. 从登录日志生成 fact_player_active_daily
-- 2. 每日 00:10 增量汇总基础统计
-- 3. 每日 00:10 增量回刷留存 / 付费留存 / LTV
--
-- 说明：
-- 1. 这里假设原始登录日志表为 ods_player_login_log
-- 2. 这里假设原始充值订单已经清洗进入 fact_player_recharge_order
-- 3. 下面以变量 @run_date 表示“今天”，统计对象主要是 T-1

SET NAMES utf8mb4;

-- 0. 推荐的登录日志原始表
-- 如果你们已有日志表，可忽略这段，仅对照字段。
CREATE TABLE IF NOT EXISTS ods_player_login_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    player_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    login_time DATETIME(3) NOT NULL,
    logout_time DATETIME(3) NULL,
    session_seconds INT NOT NULL DEFAULT 0,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    server_id BIGINT NULL,
    device_id VARCHAR(128) NULL,
    ip VARCHAR(64) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_login_time (login_time),
    KEY idx_player_login_time (player_id, login_time),
    KEY idx_dim_login_time (channel_code, area_code, system_code, login_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家登录原始日志表';


-- 1. 作业运行日期
-- 假设今天凌晨 00:10 执行，统计前一天。
SET @run_date = CURDATE();
SET @stat_date = DATE_SUB(@run_date, INTERVAL 1 DAY);


-- 2. 登录日志 -> 玩家日活跃事实
-- 没有 logout_time 也可以跑，只是 active_minutes 不够精确。
INSERT INTO fact_player_active_daily (
    stat_date,
    player_id,
    user_id,
    channel_code,
    area_code,
    system_code,
    server_id,
    login_count,
    active_minutes,
    first_login_time,
    last_login_time,
    created_at,
    updated_at
)
SELECT
    DATE(l.login_time) AS stat_date,
    l.player_id,
    MAX(l.user_id) AS user_id,
    SUBSTRING_INDEX(GROUP_CONCAT(l.channel_code ORDER BY l.login_time DESC), ',', 1) AS channel_code,
    SUBSTRING_INDEX(GROUP_CONCAT(l.area_code ORDER BY l.login_time DESC), ',', 1) AS area_code,
    SUBSTRING_INDEX(GROUP_CONCAT(l.system_code ORDER BY l.login_time DESC), ',', 1) AS system_code,
    CAST(SUBSTRING_INDEX(GROUP_CONCAT(COALESCE(l.server_id, 0) ORDER BY l.login_time DESC), ',', 1) AS UNSIGNED) AS server_id,
    COUNT(*) AS login_count,
    FLOOR(SUM(COALESCE(l.session_seconds, 0)) / 60) AS active_minutes,
    MIN(l.login_time) AS first_login_time,
    MAX(COALESCE(l.logout_time, l.login_time)) AS last_login_time,
    NOW(3) AS created_at,
    NOW(3) AS updated_at
FROM ods_player_login_log l
WHERE l.login_time >= @stat_date
  AND l.login_time < DATE_ADD(@stat_date, INTERVAL 1 DAY)
GROUP BY DATE(l.login_time), l.player_id
ON DUPLICATE KEY UPDATE
    user_id = VALUES(user_id),
    channel_code = VALUES(channel_code),
    area_code = VALUES(area_code),
    system_code = VALUES(system_code),
    server_id = VALUES(server_id),
    login_count = VALUES(login_count),
    active_minutes = VALUES(active_minutes),
    first_login_time = VALUES(first_login_time),
    last_login_time = VALUES(last_login_time),
    updated_at = VALUES(updated_at);


-- 3. 基础统计 ads_player_stat
-- 这里按“天”粒度汇总 T-1。
INSERT INTO ads_player_stat (
    stat_granularity,
    stat_time,
    stat_date,
    channel_code,
    area_code,
    system_code,
    new_player_num,
    active_player_num,
    old_active_player_num,
    pay_player_num,
    first_pay_player_num,
    recharge_order_num,
    recharge_amount_cent,
    total_active_minutes,
    max_active_minutes,
    created_at,
    updated_at
)
SELECT
    3 AS stat_granularity,
    CAST(@stat_date AS DATETIME) AS stat_time,
    @stat_date AS stat_date,
    d.channel_code,
    d.area_code,
    d.system_code,
    COALESCE(n.new_player_num, 0) AS new_player_num,
    COALESCE(a.active_player_num, 0) AS active_player_num,
    COALESCE(a.old_active_player_num, 0) AS old_active_player_num,
    COALESCE(p.pay_player_num, 0) AS pay_player_num,
    COALESCE(p.first_pay_player_num, 0) AS first_pay_player_num,
    COALESCE(p.recharge_order_num, 0) AS recharge_order_num,
    COALESCE(p.recharge_amount_cent, 0) AS recharge_amount_cent,
    COALESCE(a.total_active_minutes, 0) AS total_active_minutes,
    COALESCE(a.max_active_minutes, 0) AS max_active_minutes,
    NOW(3),
    NOW(3)
FROM (
    SELECT channel_code, area_code, system_code
    FROM fact_player_register
    WHERE cohort_date = @stat_date
    UNION
    SELECT channel_code, area_code, system_code
    FROM fact_player_active_daily
    WHERE stat_date = @stat_date
    UNION
    SELECT channel_code, area_code, system_code
    FROM fact_player_recharge_order
    WHERE pay_date = @stat_date
      AND order_status = 1
) d
LEFT JOIN (
    SELECT
        channel_code,
        area_code,
        system_code,
        COUNT(*) AS new_player_num
    FROM fact_player_register
    WHERE cohort_date = @stat_date
    GROUP BY channel_code, area_code, system_code
) n
    ON n.channel_code = d.channel_code
   AND n.area_code = d.area_code
   AND n.system_code = d.system_code
LEFT JOIN (
    SELECT
        a.channel_code,
        a.area_code,
        a.system_code,
        COUNT(*) AS active_player_num,
        SUM(CASE WHEN r.cohort_date < a.stat_date THEN 1 ELSE 0 END) AS old_active_player_num,
        SUM(a.active_minutes) AS total_active_minutes,
        MAX(a.active_minutes) AS max_active_minutes
    FROM fact_player_active_daily a
    JOIN fact_player_register r
      ON r.player_id = a.player_id
    WHERE a.stat_date = @stat_date
    GROUP BY a.channel_code, a.area_code, a.system_code
) a
    ON a.channel_code = d.channel_code
   AND a.area_code = d.area_code
   AND a.system_code = d.system_code
LEFT JOIN (
    SELECT
        channel_code,
        area_code,
        system_code,
        COUNT(DISTINCT player_id) AS pay_player_num,
        COUNT(DISTINCT CASE WHEN is_first_pay = 1 THEN player_id END) AS first_pay_player_num,
        COUNT(*) AS recharge_order_num,
        SUM(amount_cent) AS recharge_amount_cent
    FROM fact_player_recharge_order
    WHERE pay_date = @stat_date
      AND order_status = 1
    GROUP BY channel_code, area_code, system_code
) p
    ON p.channel_code = d.channel_code
   AND p.area_code = d.area_code
   AND p.system_code = d.system_code
ON DUPLICATE KEY UPDATE
    new_player_num = VALUES(new_player_num),
    active_player_num = VALUES(active_player_num),
    old_active_player_num = VALUES(old_active_player_num),
    pay_player_num = VALUES(pay_player_num),
    first_pay_player_num = VALUES(first_pay_player_num),
    recharge_order_num = VALUES(recharge_order_num),
    recharge_amount_cent = VALUES(recharge_amount_cent),
    total_active_minutes = VALUES(total_active_minutes),
    max_active_minutes = VALUES(max_active_minutes),
    updated_at = VALUES(updated_at);


-- 4. 玩家留存回刷
-- 每天只回刷常用留存窗口：D1/D3/D7/D14/D30
-- 例如今天是 T，那么要更新：
-- T-1 影响某 cohort 的 D1
-- T-3 影响某 cohort 的 D3
-- T-7 影响某 cohort 的 D7
-- T-14 影响某 cohort 的 D14
-- T-30 影响某 cohort 的 D30

-- D1
INSERT INTO ads_player_retention_cohort (
    cohort_type,
    cohort_date,
    retention_day,
    channel_code,
    area_code,
    system_code,
    cohort_player_num,
    retained_player_num,
    retention_rate,
    created_at,
    updated_at
)
SELECT
    'create_role',
    r.cohort_date,
    1,
    r.channel_code,
    r.area_code,
    r.system_code,
    COUNT(*) AS cohort_player_num,
    COUNT(a.player_id) AS retained_player_num,
    COUNT(a.player_id) / COUNT(*) AS retention_rate,
    NOW(3),
    NOW(3)
FROM fact_player_register r
LEFT JOIN fact_player_active_daily a
    ON a.player_id = r.player_id
   AND a.stat_date = DATE_ADD(r.cohort_date, INTERVAL 1 DAY)
WHERE r.cohort_date = DATE_SUB(@stat_date, INTERVAL 1 DAY)
GROUP BY r.cohort_date, r.channel_code, r.area_code, r.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_player_num = VALUES(retained_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

-- D3
INSERT INTO ads_player_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_player_num, retention_rate, created_at, updated_at
)
SELECT
    'create_role', r.cohort_date, 3, r.channel_code, r.area_code, r.system_code,
    COUNT(*),
    COUNT(a.player_id),
    COUNT(a.player_id) / COUNT(*),
    NOW(3), NOW(3)
FROM fact_player_register r
LEFT JOIN fact_player_active_daily a
    ON a.player_id = r.player_id
   AND a.stat_date = DATE_ADD(r.cohort_date, INTERVAL 3 DAY)
WHERE r.cohort_date = DATE_SUB(@stat_date, INTERVAL 3 DAY)
GROUP BY r.cohort_date, r.channel_code, r.area_code, r.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_player_num = VALUES(retained_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

-- D7
INSERT INTO ads_player_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_player_num, retention_rate, created_at, updated_at
)
SELECT
    'create_role', r.cohort_date, 7, r.channel_code, r.area_code, r.system_code,
    COUNT(*),
    COUNT(a.player_id),
    COUNT(a.player_id) / COUNT(*),
    NOW(3), NOW(3)
FROM fact_player_register r
LEFT JOIN fact_player_active_daily a
    ON a.player_id = r.player_id
   AND a.stat_date = DATE_ADD(r.cohort_date, INTERVAL 7 DAY)
WHERE r.cohort_date = DATE_SUB(@stat_date, INTERVAL 7 DAY)
GROUP BY r.cohort_date, r.channel_code, r.area_code, r.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_player_num = VALUES(retained_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

-- D14
INSERT INTO ads_player_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_player_num, retention_rate, created_at, updated_at
)
SELECT
    'create_role', r.cohort_date, 14, r.channel_code, r.area_code, r.system_code,
    COUNT(*),
    COUNT(a.player_id),
    COUNT(a.player_id) / COUNT(*),
    NOW(3), NOW(3)
FROM fact_player_register r
LEFT JOIN fact_player_active_daily a
    ON a.player_id = r.player_id
   AND a.stat_date = DATE_ADD(r.cohort_date, INTERVAL 14 DAY)
WHERE r.cohort_date = DATE_SUB(@stat_date, INTERVAL 14 DAY)
GROUP BY r.cohort_date, r.channel_code, r.area_code, r.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_player_num = VALUES(retained_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

-- D30
INSERT INTO ads_player_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_player_num, retention_rate, created_at, updated_at
)
SELECT
    'create_role', r.cohort_date, 30, r.channel_code, r.area_code, r.system_code,
    COUNT(*),
    COUNT(a.player_id),
    COUNT(a.player_id) / COUNT(*),
    NOW(3), NOW(3)
FROM fact_player_register r
LEFT JOIN fact_player_active_daily a
    ON a.player_id = r.player_id
   AND a.stat_date = DATE_ADD(r.cohort_date, INTERVAL 30 DAY)
WHERE r.cohort_date = DATE_SUB(@stat_date, INTERVAL 30 DAY)
GROUP BY r.cohort_date, r.channel_code, r.area_code, r.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_player_num = VALUES(retained_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);


-- 5. 玩家充值留存回刷
-- 逻辑：cohort = 某天成功付费玩家；retained = 第 N 天再次成功付费玩家
-- 示例只回刷 D1/D3/D7/D14/D30

-- D1
INSERT INTO ads_player_recharge_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_pay_player_num, retention_rate, created_at, updated_at
)
SELECT
    'pay_day',
    p0.pay_date,
    1,
    p0.channel_code,
    p0.area_code,
    p0.system_code,
    COUNT(DISTINCT p0.player_id),
    COUNT(DISTINCT p1.player_id),
    COUNT(DISTINCT p1.player_id) / COUNT(DISTINCT p0.player_id),
    NOW(3),
    NOW(3)
FROM fact_player_recharge_order p0
LEFT JOIN fact_player_recharge_order p1
    ON p1.player_id = p0.player_id
   AND p1.pay_date = DATE_ADD(p0.pay_date, INTERVAL 1 DAY)
   AND p1.order_status = 1
WHERE p0.pay_date = DATE_SUB(@stat_date, INTERVAL 1 DAY)
  AND p0.order_status = 1
GROUP BY p0.pay_date, p0.channel_code, p0.area_code, p0.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_pay_player_num = VALUES(retained_pay_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

-- D3 / D7 / D14 / D30
-- 为避免重复大段动态 SQL，下面直接展开。
INSERT INTO ads_player_recharge_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_pay_player_num, retention_rate, created_at, updated_at
)
SELECT 'pay_day', p0.pay_date, 3, p0.channel_code, p0.area_code, p0.system_code,
       COUNT(DISTINCT p0.player_id), COUNT(DISTINCT p1.player_id),
       COUNT(DISTINCT p1.player_id) / COUNT(DISTINCT p0.player_id), NOW(3), NOW(3)
FROM fact_player_recharge_order p0
LEFT JOIN fact_player_recharge_order p1
    ON p1.player_id = p0.player_id
   AND p1.pay_date = DATE_ADD(p0.pay_date, INTERVAL 3 DAY)
   AND p1.order_status = 1
WHERE p0.pay_date = DATE_SUB(@stat_date, INTERVAL 3 DAY)
  AND p0.order_status = 1
GROUP BY p0.pay_date, p0.channel_code, p0.area_code, p0.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_pay_player_num = VALUES(retained_pay_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

INSERT INTO ads_player_recharge_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_pay_player_num, retention_rate, created_at, updated_at
)
SELECT 'pay_day', p0.pay_date, 7, p0.channel_code, p0.area_code, p0.system_code,
       COUNT(DISTINCT p0.player_id), COUNT(DISTINCT p1.player_id),
       COUNT(DISTINCT p1.player_id) / COUNT(DISTINCT p0.player_id), NOW(3), NOW(3)
FROM fact_player_recharge_order p0
LEFT JOIN fact_player_recharge_order p1
    ON p1.player_id = p0.player_id
   AND p1.pay_date = DATE_ADD(p0.pay_date, INTERVAL 7 DAY)
   AND p1.order_status = 1
WHERE p0.pay_date = DATE_SUB(@stat_date, INTERVAL 7 DAY)
  AND p0.order_status = 1
GROUP BY p0.pay_date, p0.channel_code, p0.area_code, p0.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_pay_player_num = VALUES(retained_pay_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

INSERT INTO ads_player_recharge_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_pay_player_num, retention_rate, created_at, updated_at
)
SELECT 'pay_day', p0.pay_date, 14, p0.channel_code, p0.area_code, p0.system_code,
       COUNT(DISTINCT p0.player_id), COUNT(DISTINCT p1.player_id),
       COUNT(DISTINCT p1.player_id) / COUNT(DISTINCT p0.player_id), NOW(3), NOW(3)
FROM fact_player_recharge_order p0
LEFT JOIN fact_player_recharge_order p1
    ON p1.player_id = p0.player_id
   AND p1.pay_date = DATE_ADD(p0.pay_date, INTERVAL 14 DAY)
   AND p1.order_status = 1
WHERE p0.pay_date = DATE_SUB(@stat_date, INTERVAL 14 DAY)
  AND p0.order_status = 1
GROUP BY p0.pay_date, p0.channel_code, p0.area_code, p0.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_pay_player_num = VALUES(retained_pay_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);

INSERT INTO ads_player_recharge_retention_cohort (
    cohort_type, cohort_date, retention_day, channel_code, area_code, system_code,
    cohort_player_num, retained_pay_player_num, retention_rate, created_at, updated_at
)
SELECT 'pay_day', p0.pay_date, 30, p0.channel_code, p0.area_code, p0.system_code,
       COUNT(DISTINCT p0.player_id), COUNT(DISTINCT p1.player_id),
       COUNT(DISTINCT p1.player_id) / COUNT(DISTINCT p0.player_id), NOW(3), NOW(3)
FROM fact_player_recharge_order p0
LEFT JOIN fact_player_recharge_order p1
    ON p1.player_id = p0.player_id
   AND p1.pay_date = DATE_ADD(p0.pay_date, INTERVAL 30 DAY)
   AND p1.order_status = 1
WHERE p0.pay_date = DATE_SUB(@stat_date, INTERVAL 30 DAY)
  AND p0.order_status = 1
GROUP BY p0.pay_date, p0.channel_code, p0.area_code, p0.system_code
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    retained_pay_player_num = VALUES(retained_pay_player_num),
    retention_rate = VALUES(retention_rate),
    updated_at = VALUES(updated_at);


-- 6. 玩家 LTV 回刷
-- 每天 @stat_date 会影响所有 cohort_date <= @stat_date 的一个新 ltv_day
-- 下面示例仅回刷最近 30 天 cohort 的“当天新增 ltv_day”
INSERT INTO ads_player_ltv_cohort (
    cohort_type,
    cohort_date,
    ltv_day,
    channel_code,
    area_code,
    system_code,
    cohort_player_num,
    pay_player_num,
    revenue_cent,
    cumulative_revenue_cent,
    ltv_amount,
    arpu_amount,
    arppu_amount,
    created_at,
    updated_at
)
SELECT
    'create_role' AS cohort_type,
    x.cohort_date,
    x.ltv_day,
    x.channel_code,
    x.area_code,
    x.system_code,
    x.cohort_player_num,
    x.pay_player_num,
    x.revenue_cent,
    x.cumulative_revenue_cent,
    ROUND(x.cumulative_revenue_cent / 100 / x.cohort_player_num, 6) AS ltv_amount,
    ROUND(x.revenue_cent / 100 / x.cohort_player_num, 6) AS arpu_amount,
    ROUND(
        CASE WHEN x.pay_player_num = 0 THEN 0 ELSE x.revenue_cent / 100 / x.pay_player_num END,
        6
    ) AS arppu_amount,
    NOW(3),
    NOW(3)
FROM (
    SELECT
        b.cohort_date,
        b.channel_code,
        b.area_code,
        b.system_code,
        DATEDIFF(@stat_date, b.cohort_date) AS ltv_day,
        b.cohort_player_num,
        COALESCE(d.pay_player_num, 0) AS pay_player_num,
        COALESCE(d.revenue_cent, 0) AS revenue_cent,
        COALESCE(h.cumulative_revenue_cent, 0) + COALESCE(d.revenue_cent, 0) AS cumulative_revenue_cent
    FROM (
        SELECT
            cohort_date,
            channel_code,
            area_code,
            system_code,
            COUNT(*) AS cohort_player_num
        FROM fact_player_register
        WHERE cohort_date BETWEEN DATE_SUB(@stat_date, INTERVAL 30 DAY) AND @stat_date
        GROUP BY cohort_date, channel_code, area_code, system_code
    ) b
    LEFT JOIN (
        SELECT
            r.cohort_date,
            r.channel_code,
            r.area_code,
            r.system_code,
            COUNT(DISTINCT o.player_id) AS pay_player_num,
            SUM(o.amount_cent) AS revenue_cent
        FROM fact_player_register r
        JOIN fact_player_recharge_order o
          ON o.player_id = r.player_id
         AND o.pay_date = @stat_date
         AND o.order_status = 1
        WHERE r.cohort_date BETWEEN DATE_SUB(@stat_date, INTERVAL 30 DAY) AND @stat_date
        GROUP BY r.cohort_date, r.channel_code, r.area_code, r.system_code
    ) d
      ON d.cohort_date = b.cohort_date
     AND d.channel_code = b.channel_code
     AND d.area_code = b.area_code
     AND d.system_code = b.system_code
    LEFT JOIN ads_player_ltv_cohort h
      ON h.cohort_type = 'create_role'
     AND h.cohort_date = b.cohort_date
     AND h.channel_code = b.channel_code
     AND h.area_code = b.area_code
     AND h.system_code = b.system_code
     AND h.ltv_day = DATEDIFF(@stat_date, b.cohort_date) - 1
    WHERE DATEDIFF(@stat_date, b.cohort_date) BETWEEN 0 AND 30
) x
ON DUPLICATE KEY UPDATE
    cohort_player_num = VALUES(cohort_player_num),
    pay_player_num = VALUES(pay_player_num),
    revenue_cent = VALUES(revenue_cent),
    cumulative_revenue_cent = VALUES(cumulative_revenue_cent),
    ltv_amount = VALUES(ltv_amount),
    arpu_amount = VALUES(arpu_amount),
    arppu_amount = VALUES(arppu_amount),
    updated_at = VALUES(updated_at);


-- 7. 手工验证查询

-- 看某天是否已生成日活跃事实
-- SELECT * FROM fact_player_active_daily WHERE stat_date = @stat_date ORDER BY player_id;

-- 看某天基础统计
-- SELECT * FROM ads_player_stat WHERE stat_date = @stat_date ORDER BY channel_code, area_code;

-- 看最近 30 天留存
-- SELECT * FROM ads_player_retention_cohort
-- WHERE cohort_date BETWEEN DATE_SUB(@stat_date, INTERVAL 30 DAY) AND @stat_date
-- ORDER BY cohort_date, retention_day;

-- 看最近 30 天 LTV
-- SELECT * FROM ads_player_ltv_cohort
-- WHERE cohort_date BETWEEN DATE_SUB(@stat_date, INTERVAL 30 DAY) AND @stat_date
-- ORDER BY cohort_date, ltv_day;
