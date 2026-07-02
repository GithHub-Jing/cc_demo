# 游戏数据统计 MySQL 8 设计

## 1. 设计目标

- 支持用户留存分析、充值留存分析、LTV 分析
- 从 ES 宽字段模式迁移到 MySQL 8 的可扩展结构
- 保证日常查询高效，避免 `step_1...step_30`、`ltv_1...ltv_30` 这类难维护列
- 支持按 `system/channel/area` 多维筛选
- 支持按小时、天统计，并为后续周、月聚合预留空间

## 2. 结论先行

ES 里的设计本质上是“按时间桶 + 维度 + 一组聚合指标”的宽表。  
迁到 MySQL 8 时，不建议继续照搬成大量动态列，而应拆成两层：

1. 明细事实层：存注册、登录、角色创建、充值等最小必要事实
2. 统计汇总层：按 cohort（分群日期）+ retention_day / ltv_day 做聚合

核心原则：

- 留存/LTV 采用“长表”而不是“宽表”
- 高频后台看板使用汇总表，不直接扫大明细
- 维度字段统一标准化，避免业务表里重复塞 `year/month/week/day/hour/minute`
- 时间查询统一依赖真实时间字段和统计日期字段，不冗余存大量格式化日期

---

## 3. ES 字段到 MySQL 的映射建议

你给的 ES 结构里，主要有 4 类数据：

1. 用户注册/创角统计
2. 玩家活跃/充值统计
3. 留存统计
4. LTV 统计

其中：

- `step_1/step_4/step_6` 这类字段，本质是“cohort_date 对应第 N 天留存人数”
- `re_step_1/re_step_26` 本质是“充值用户 cohort 的第 N 天充值留存”
- `ltv_13/ltv_14/ltv_20` 本质是“cohort_date 截止第 N 天累计收入 / 人均 LTV”

所以 MySQL 中应该统一抽象成：

- `cohort_date`
- `metric_day`
- `metric_type`
- `metric_value`

或者更明确地拆成专用表。

---

## 4. 推荐分层模型

## 4.1 维度表

### 4.1.1 渠道维表 `dim_channel`

```sql
CREATE TABLE dim_channel (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    channel_code VARCHAR(64) NOT NULL,
    channel_name VARCHAR(128) NOT NULL,
    status TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_channel_code (channel_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.1.2 区服维表 `dim_area`

```sql
CREATE TABLE dim_area (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    area_code VARCHAR(64) NOT NULL,
    area_name VARCHAR(128) NOT NULL,
    status TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_area_code (area_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.1.3 系统维表 `dim_system`

```sql
CREATE TABLE dim_system (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    system_code VARCHAR(64) NOT NULL,
    system_name VARCHAR(128) NOT NULL,
    status TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_system_code (system_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

说明：

- ES 里的 `channel/area/system` 不建议继续直接用字符串散落在统计表
- 若历史包袱较重，也可以先保留 `VARCHAR`，后续再映射到维表 ID

---

## 4.2 明细事实层

这一层只保留可重算统计所需的最小事实。

### 4.2.1 用户表 `fact_user_register`

```sql
CREATE TABLE fact_user_register (
    user_id BIGINT NOT NULL,
    register_time DATETIME(3) NOT NULL,
    register_date DATE NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    device_id VARCHAR(128) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (user_id),
    KEY idx_register_date_dim (register_date, channel_code, area_code, system_code),
    KEY idx_channel_area_date (channel_code, area_code, register_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 计算新增用户
- 作为用户留存和 LTV 的 cohort 基础

### 4.2.2 创角表 `fact_player_create`

```sql
CREATE TABLE fact_player_create (
    player_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    create_time DATETIME(3) NOT NULL,
    create_date DATE NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (player_id),
    KEY idx_user_id (user_id),
    KEY idx_create_date_dim (create_date, channel_code, area_code, system_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 计算 `created_player_num`
- 计算 `no_create_player_num`

### 4.2.3 用户活跃日表 `fact_user_active_daily`

```sql
CREATE TABLE fact_user_active_daily (
    stat_date DATE NOT NULL,
    user_id BIGINT NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    active_minutes INT NOT NULL DEFAULT 0,
    login_count INT NOT NULL DEFAULT 0,
    first_login_time DATETIME(3) NULL,
    last_login_time DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (stat_date, user_id),
    KEY idx_user_date (user_id, stat_date),
    KEY idx_dim_date (channel_code, area_code, system_code, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

用途：

- 留存判断建议基于“当日活跃”
- 活跃统计、平均在线时长都从这里来

### 4.2.4 充值订单表 `fact_recharge_order`

```sql
CREATE TABLE fact_recharge_order (
    order_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    player_id BIGINT NULL,
    pay_time DATETIME(3) NOT NULL,
    pay_date DATE NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    amount_cent BIGINT NOT NULL,
    currency_code VARCHAR(16) NOT NULL DEFAULT 'CNY',
    order_status TINYINT NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (order_id),
    KEY idx_pay_date_dim (pay_date, channel_code, area_code, system_code),
    KEY idx_user_pay_date (user_id, pay_date),
    KEY idx_user_pay_time (user_id, pay_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

约束建议：

- 仅统计 `order_status = 1` 的成功订单
- 金额统一存分：`amount_cent`

---

## 4.3 汇总统计层

这一层用于看板、报表和高频查询。

### 4.3.1 通用时间粒度枚举

建议统一定义：

- `1 = minute`
- `2 = hour`
- `3 = day`
- `4 = week`
- `5 = month`

但留存和 LTV 主要以 `day` 为核心，小时统计仅用于新增/活跃/充值基础看板。

### 4.3.2 用户基础统计表 `ads_user_stat`

用于替代 ES 的 `user_statistics` / `device_statistics` 一类宽表。

```sql
CREATE TABLE ads_user_stat (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    stat_granularity TINYINT NOT NULL,
    stat_time DATETIME(0) NOT NULL,
    stat_date DATE NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    new_user_num INT NOT NULL DEFAULT 0,
    created_player_num INT NOT NULL DEFAULT 0,
    no_create_player_num INT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_granularity_time_dim (stat_granularity, stat_time, channel_code, area_code, system_code),
    KEY idx_stat_date_dim (stat_date, channel_code, area_code, system_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.3.3 玩家基础统计表 `ads_player_stat`

```sql
CREATE TABLE ads_player_stat (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    stat_granularity TINYINT NOT NULL,
    stat_time DATETIME(0) NOT NULL,
    stat_date DATE NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    all_player_num INT NOT NULL DEFAULT 0,
    new_player_num INT NOT NULL DEFAULT 0,
    all_active_player_num INT NOT NULL DEFAULT 0,
    old_active_player_num INT NOT NULL DEFAULT 0,
    max_active_player_time INT NOT NULL DEFAULT 0,
    all_active_player_time BIGINT NOT NULL DEFAULT 0,
    first_recharge_num INT NOT NULL DEFAULT 0,
    all_recharge_num INT NOT NULL DEFAULT 0,
    new_recharge_num INT NOT NULL DEFAULT 0,
    all_recharge_money_cent BIGINT NOT NULL DEFAULT 0,
    old_recharge_money_cent BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_granularity_time_dim (stat_granularity, stat_time, channel_code, area_code, system_code),
    KEY idx_stat_date_dim (stat_date, channel_code, area_code, system_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 5. 留存设计

## 5.1 用户留存 cohort 表 `ads_user_retention_cohort`

```sql
CREATE TABLE ads_user_retention_cohort (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    cohort_date DATE NOT NULL,
    retention_day SMALLINT NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    cohort_user_num INT NOT NULL DEFAULT 0,
    retained_user_num INT NOT NULL DEFAULT 0,
    retention_rate DECIMAL(10,6) NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_cohort_dim_day (cohort_date, retention_day, channel_code, area_code, system_code),
    KEY idx_dim_cohort (channel_code, area_code, system_code, cohort_date),
    KEY idx_retention_day (retention_day, cohort_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

解释：

- `cohort_date`：注册日期
- `retention_day = 1`：次留
- `retention_day = 7`：7 留
- `retention_day = 30`：30 留

这样可以完全替代 ES 中的 `step_1/step_7/step_30`

### 5.2 充值留存 cohort 表 `ads_recharge_retention_cohort`

```sql
CREATE TABLE ads_recharge_retention_cohort (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    cohort_date DATE NOT NULL,
    retention_day SMALLINT NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    recharge_user_num INT NOT NULL DEFAULT 0,
    retained_recharge_user_num INT NOT NULL DEFAULT 0,
    retention_rate DECIMAL(10,6) NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_cohort_dim_day (cohort_date, retention_day, channel_code, area_code, system_code),
    KEY idx_dim_cohort (channel_code, area_code, system_code, cohort_date),
    KEY idx_retention_day (retention_day, cohort_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

这里的 cohort 建议定义为：

- 某天首充用户
- 或某天有充值行为的去重用户

两种都可做，但口径必须固定。  
如果你们历史 ES 是“当天充值用户，后续继续充值的留存”，那就按第二种。

---

## 6. LTV 设计

## 6.1 LTV cohort 表 `ads_ltv_cohort`

```sql
CREATE TABLE ads_ltv_cohort (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    cohort_date DATE NOT NULL,
    ltv_day SMALLINT NOT NULL,
    channel_code VARCHAR(64) NOT NULL,
    area_code VARCHAR(64) NOT NULL,
    system_code VARCHAR(64) NOT NULL DEFAULT '',
    cohort_user_num INT NOT NULL DEFAULT 0,
    pay_user_num INT NOT NULL DEFAULT 0,
    revenue_cent BIGINT NOT NULL DEFAULT 0,
    cumulative_revenue_cent BIGINT NOT NULL DEFAULT 0,
    ltv_amount DECIMAL(18,6) NOT NULL DEFAULT 0,
    arpu_amount DECIMAL(18,6) NOT NULL DEFAULT 0,
    arppu_amount DECIMAL(18,6) NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_cohort_dim_day (cohort_date, ltv_day, channel_code, area_code, system_code),
    KEY idx_dim_cohort (channel_code, area_code, system_code, cohort_date),
    KEY idx_ltv_day (ltv_day, cohort_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

字段口径：

- `revenue_cent`：cohort 在第 N 天当天贡献收入
- `cumulative_revenue_cent`：cohort 从第 0 天到第 N 天累计收入
- `ltv_amount = cumulative_revenue_cent / cohort_user_num / 100`
- `arpu_amount = revenue_cent / cohort_user_num / 100`
- `arppu_amount = revenue_cent / pay_user_num / 100`

这样直接替代 ES 里的 `ltv_1 ... ltv_30`

---

## 7. 为什么不要继续做宽表

如果继续做：

- `step_1, step_2, ... step_180`
- `ltv_1, ltv_2, ... ltv_180`

问题会很明显：

1. 增加分析周期必须改表
2. SQL 很难动态查询和透视
3. 指标含义容易混淆，代码维护差
4. 索引帮不上忙，字段越堆越丑

长表方案的优势：

1. 任何 N 日留存/LTV 都只是一行数据
2. 可直接做区间聚合、趋势图、导出
3. 后续要扩成 60 日、90 日、180 日不需要改结构

---

## 8. 典型计算逻辑

## 8.1 次留/7 留/30 留计算

注册 cohort：

```sql
INSERT INTO ads_user_retention_cohort (
    cohort_date,
    retention_day,
    channel_code,
    area_code,
    system_code,
    cohort_user_num,
    retained_user_num,
    retention_rate
)
SELECT
    u.register_date AS cohort_date,
    DATEDIFF(a.stat_date, u.register_date) AS retention_day,
    u.channel_code,
    u.area_code,
    u.system_code,
    COUNT(DISTINCT u.user_id) AS cohort_user_num,
    COUNT(DISTINCT a.user_id) AS retained_user_num,
    COUNT(DISTINCT a.user_id) / COUNT(DISTINCT u.user_id) AS retention_rate
FROM fact_user_register u
LEFT JOIN fact_user_active_daily a
    ON a.user_id = u.user_id
   AND a.stat_date > u.register_date
   AND DATEDIFF(a.stat_date, u.register_date) IN (1, 7, 30)
WHERE u.register_date = DATE '2025-06-17'
GROUP BY
    u.register_date,
    DATEDIFF(a.stat_date, u.register_date),
    u.channel_code,
    u.area_code,
    u.system_code;
```

实际生产里建议分两步：

1. 先算 cohort 基数
2. 再按 `retention_day` 回填留存人数

这样更稳定，也更容易做补算。

## 8.2 LTV 计算

```sql
INSERT INTO ads_ltv_cohort (
    cohort_date,
    ltv_day,
    channel_code,
    area_code,
    system_code,
    cohort_user_num,
    pay_user_num,
    revenue_cent,
    cumulative_revenue_cent,
    ltv_amount,
    arpu_amount,
    arppu_amount
)
SELECT
    u.register_date AS cohort_date,
    DATEDIFF(r.pay_date, u.register_date) AS ltv_day,
    u.channel_code,
    u.area_code,
    u.system_code,
    COUNT(DISTINCT u.user_id) AS cohort_user_num,
    COUNT(DISTINCT CASE WHEN r.order_status = 1 THEN r.user_id END) AS pay_user_num,
    COALESCE(SUM(CASE WHEN r.order_status = 1 THEN r.amount_cent ELSE 0 END), 0) AS revenue_cent,
    0 AS cumulative_revenue_cent,
    0 AS ltv_amount,
    0 AS arpu_amount,
    0 AS arppu_amount
FROM fact_user_register u
LEFT JOIN fact_recharge_order r
    ON r.user_id = u.user_id
   AND r.pay_date >= u.register_date
   AND DATEDIFF(r.pay_date, u.register_date) BETWEEN 0 AND 30
WHERE u.register_date = DATE '2024-12-25'
GROUP BY
    u.register_date,
    DATEDIFF(r.pay_date, u.register_date),
    u.channel_code,
    u.area_code,
    u.system_code;
```

`cumulative_revenue_cent` 建议通过窗口函数或离线任务二次更新：

```sql
SELECT
    cohort_date,
    ltv_day,
    channel_code,
    area_code,
    system_code,
    SUM(revenue_cent) OVER (
        PARTITION BY cohort_date, channel_code, area_code, system_code
        ORDER BY ltv_day
    ) AS cumulative_revenue_cent
FROM ads_ltv_cohort;
```

---

## 9. 典型查询

## 9.1 查某渠道某区服最近 30 天次留/7 留/30 留

```sql
SELECT
    cohort_date,
    retention_day,
    cohort_user_num,
    retained_user_num,
    retention_rate
FROM ads_user_retention_cohort
WHERE channel_code = 'game'
  AND area_code = '19'
  AND system_code = ''
  AND retention_day IN (1, 7, 30)
  AND cohort_date BETWEEN DATE '2025-05-29' AND DATE '2025-06-27'
ORDER BY cohort_date DESC, retention_day ASC;
```

## 9.2 查某 cohort 的 LTV1/LTV3/LTV7/LTV15/LTV30

```sql
SELECT
    cohort_date,
    ltv_day,
    cumulative_revenue_cent,
    ltv_amount
FROM ads_ltv_cohort
WHERE channel_code = 'game'
  AND area_code = '1'
  AND system_code = ''
  AND cohort_date = DATE '2024-12-25'
  AND ltv_day IN (1, 3, 7, 15, 30)
ORDER BY ltv_day;
```

## 9.3 如果前端必须要宽结果

MySQL 层临时透视即可，不要把宽结构存回表里：

```sql
SELECT
    cohort_date,
    MAX(CASE WHEN ltv_day = 1 THEN ltv_amount END) AS ltv_1,
    MAX(CASE WHEN ltv_day = 3 THEN ltv_amount END) AS ltv_3,
    MAX(CASE WHEN ltv_day = 7 THEN ltv_amount END) AS ltv_7,
    MAX(CASE WHEN ltv_day = 15 THEN ltv_amount END) AS ltv_15,
    MAX(CASE WHEN ltv_day = 30 THEN ltv_amount END) AS ltv_30
FROM ads_ltv_cohort
WHERE channel_code = 'game'
  AND area_code = '1'
  AND system_code = ''
GROUP BY cohort_date;
```

---

## 10. 索引与性能建议

## 10.1 明细表

- `fact_user_register`：`(register_date, channel_code, area_code, system_code)`
- `fact_user_active_daily`：主键 `(stat_date, user_id)`，辅索引 `(user_id, stat_date)`
- `fact_recharge_order`：`(user_id, pay_date)`、`(pay_date, channel_code, area_code, system_code)`

原因：

- 留存计算核心是 `user_id + date`
- LTV 计算核心是 `user_id + pay_date`

## 10.2 汇总表

- 留存表唯一键：`(cohort_date, retention_day, channel_code, area_code, system_code)`
- LTV 表唯一键：`(cohort_date, ltv_day, channel_code, area_code, system_code)`

原因：

- 支持幂等补算
- 支持 `INSERT ... ON DUPLICATE KEY UPDATE`

## 10.3 分区建议

数据量上来后，优先给明细表做按月分区：

- `fact_user_active_daily` 按 `stat_date` 月分区
- `fact_recharge_order` 按 `pay_date` 月分区

不建议一开始就给所有汇总表做复杂分区。  
汇总表本身数据量相对可控，先依赖索引即可。

---

## 11. 调度与补算建议

推荐离线任务按以下顺序跑：

1. 导入注册事实
2. 导入创角事实
3. 导入活跃日事实
4. 导入充值事实
5. 汇总基础看板表
6. 汇总用户留存表
7. 汇总充值留存表
8. 汇总 LTV 表

补算策略：

- 按 `cohort_date` 补算
- 按 `channel_code/area_code/system_code` 局部补算
- 汇总表用唯一键覆盖更新

---

## 12. 与你当前 ES 结构的对应关系

### `dev_kitchen_user_statistics`

对应：

- `ads_user_stat`

字段映射：

- `new_user_num` -> `new_user_num`
- `created_player_num` -> `created_player_num`
- `no_create_player_num` -> `no_create_player_num`
- `time/day/hour/month/week/year` -> `stat_time/stat_date`，其余时间维不落库冗余存

### `dev_kitchen_player_statistics`

对应：

- `ads_player_stat`

### `dev_kitchen_retention_statistics`

对应：

- `ads_user_retention_cohort`

映射：

- `step_1` -> `retention_day = 1`
- `step_4` -> `retention_day = 4`
- `step_6` -> `retention_day = 6`

### `dev_kitchen_recharge_retention_statistics`

对应：

- `ads_recharge_retention_cohort`

映射：

- `re_step_1` -> `retention_day = 1`
- `re_step_27` -> `retention_day = 27`

### `dev_kitchen_ltv_statistics`

对应：

- `ads_ltv_cohort`

映射：

- `ltv_13` -> `ltv_day = 13`
- `ltv_20` -> `ltv_day = 20`

---

## 13. 最终推荐

如果你现在只关心“可用性好、扩展强、查询高效”，建议直接按下面的最小可用集合落地：

必做表：

1. `fact_user_register`
2. `fact_player_create`
3. `fact_user_active_daily`
4. `fact_recharge_order`
5. `ads_user_stat`
6. `ads_player_stat`
7. `ads_user_retention_cohort`
8. `ads_recharge_retention_cohort`
9. `ads_ltv_cohort`

这套结构的优点：

- 可以完整覆盖你给的 ES 场景
- 不依赖动态列
- 后续做 60 日、90 日、180 日留存/LTV 不需要改表
- 前端要宽格式时，查询层透视即可

如果你愿意，我下一步可以直接继续给你补两部分：

1. 一份可直接执行的完整 MySQL 8 DDL SQL 文件
2. 一份“每日离线统计任务”的 SQL/伪代码方案，包含留存和 LTV 的实际跑批逻辑

---

## 14. 示例数据说明

我另外补了一份示例数据文件：

- [game_statistics_sample_data.sql](/Users/worker/PyCharmMiscProject/game_statistics_sample_data.sql:1)

你可以用它直接感受这套模型。

### 示例 1：2025-06-17 / `game` / `25`

注册用户 5 个：

- `10001`
- `10002`
- `10003`
- `10004`
- `10005`

其中：

- D1 活跃用户 3 个：`10001/10003/10004`
- D3 活跃用户 2 个：`10001/10003`
- D7 活跃用户 2 个：`10001/10004`

所以留存汇总表里会看到：

- `retention_day = 1`，`retained_user_num = 3`，留存率 `0.6`
- `retention_day = 3`，`retained_user_num = 2`，留存率 `0.4`
- `retention_day = 7`，`retained_user_num = 2`，留存率 `0.4`

### 示例 2：2024-12-25 / `game` / `1`

注册用户 4 个：

- `10009`
- `10010`
- `10011`
- `10012`

充值轨迹：

- D0 收入 `1360` 分
- D1 收入 `1360` 分
- D3 收入 `3240` 分
- D7 收入 `5600` 分
- D14 收入 `7460` 分

累计收入：

- D0 = `1360`
- D1 = `2720`
- D3 = `5960`
- D7 = `11560`
- D14 = `19020`

因为 cohort 用户数是 4，所以：

- `LTV0 = 1360 / 100 / 4 = 3.40`
- `LTV1 = 2720 / 100 / 4 = 6.80`
- `LTV3 = 5960 / 100 / 4 = 14.90`
- `LTV7 = 11560 / 100 / 4 = 28.90`
- `LTV14 = 19020 / 100 / 4 = 47.55`
