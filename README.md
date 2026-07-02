# Boss Analyzer 使用说明

Boss Analyzer 用于基于 Boss 直聘查询岗位、汇总技能要求，并长期追踪指定公司的指定岗位状态。

## 环境准备

安装依赖：

```bash
python3 -m pip install -r boss_analyzer/requirements.txt
```

首次使用前登录 Boss 直聘并保存 Cookie：

```bash
python3 -B -m boss_analyzer login
```

后续 `search` 和 `track --fast` 会优先使用 Cookie 走 API 快速模式，不打开浏览器。

如果提示 Cookie 过期，重新执行：

```bash
python3 -B -m boss_analyzer login
```

## 岗位搜索

搜索福州前 20 条 Python 工程师岗位，默认以终端表格输出：

```bash
python3 -B -m boss_analyzer search Python工程师 --city 福州 --limit 20 --fast
```

常用参数：

```text
--city          城市，例如 福州、深圳、上海；默认 全国
--limit         返回数量，默认 20
--fast          快速模式，只走 API；Cookie 失效时不回退浏览器
--format table 终端表格输出，默认值
--format html  生成 HTML 报告
```

生成 HTML：

```bash
python3 -B -m boss_analyzer search Python工程师 --city 福州 --limit 20 --fast --format html
```

## 技能汇总

在搜索结果后追加技能要求汇总：

```bash
python3 -B -m boss_analyzer search Python工程师 --city 福州 --limit 20 --fast --skill-summary
```

只显示前 10 个细分技能：

```bash
python3 -B -m boss_analyzer search Python工程师 --city 福州 --limit 20 --fast --skill-summary --skill-top 10
```

技能汇总会：

- 自动排除搜索词本身，例如搜索 `Python工程师` 时不统计 `Python`
- 输出技能类别，例如 `工程化/部署`、`数据库/缓存`、`爬虫/自动化`、`AI/机器学习`
- 输出细分技能 Top N
- 同一岗位内重复技能只计 1 次

## 公司岗位追踪

追踪某家公司在指定岗位搜索结果中的岗位变化：

```bash
python3 -B -m boss_analyzer track "福富公司" --position "Python工程师" --city 福州 --limit 20 --fast
```

定期执行，每 60 分钟一次，持续运行：

```bash
python3 -B -m boss_analyzer track "福富公司" --position "Python工程师" --city 福州 --limit 20 --fast --interval-minutes 60 --runs 0
```

只执行 6 次：

```bash
python3 -B -m boss_analyzer track "福富公司" --position "Python工程师" --city 福州 --limit 20 --fast --interval-minutes 60 --runs 6
```

追踪数据默认保存到：

```text
./data/boss_tracking.db
```

指定数据库路径：

```bash
python3 -B -m boss_analyzer track "福富公司" --position "Python工程师" --city 福州 --limit 20 --fast --db ./data/fuzhou_python.db
```

## 长期状态判断

`track` 会基于历史快照输出长期状态监控：

```text
🆕 新发现岗位：首次或近 1 天内发现
🔥 短期急招：14 天内出现，HR 很活跃或内容频繁更新
✅ 正常在招：HR 近 7 天活跃，近期仍有更新
♻️ 长期常招/人才池：连续 45 天以上在线，仍有活跃信号
🧊 长期低热/疑似占位：观察 30 天以上，21 天以上未更新，HR 活跃弱
❔ 状态不明：数据不足或 HR 活跃时间采集不到
```

状态表字段：

```text
观察天：第一次发现到当前运行的天数
未更新：岗位内容距上次变化的天数
快照：累计观察次数
证据：状态判断依据
```

## 推荐工作流

1. 登录刷新 Cookie：

```bash
python3 -B -m boss_analyzer login
```

2. 先看市场岗位和技能要求：

```bash
python3 -B -m boss_analyzer search Python工程师 --city 福州 --limit 20 --fast --skill-summary --skill-top 10
```

3. 选定目标公司后长期追踪：

```bash
python3 -B -m boss_analyzer track "目标公司名" --position "Python工程师" --city 福州 --limit 20 --fast --interval-minutes 60 --runs 0
```

## 注意事项

- Boss Cookie 可能很快过期，过期后重新执行 `login`
- `--fast` 模式不会回退浏览器，避免 Cookie 失效时慢速失败
- 不建议高频请求，定时追踪建议按 30 到 120 分钟间隔执行
- HTML 报告只在 `--format html` 或追踪报告场景生成
