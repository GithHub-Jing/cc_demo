# 功能规划：岗位搜索与匹配排序

## 背景

现有工具：输入公司名/URL → 抓取该公司Boss直聘信息 → 生成风险分析报告（真实性/招聘真实性/岗位贴合度）

用户新增两个需求：
1. **公司分析增强**：报告中展示所有岗位按用户匹配度的逐岗排名（当前只显示维度最优值）
2. **岗位搜索排序**：输入岗位名称，搜索全站匹配岗位，按综合分（贴合度+真实性）排序输出

---

## Feature 1：公司分析报告增强（逐岗排名）

### 变更范围

**`boss_analyzer/analyzers/fitness.py`**
- 新增 `evaluate_fitness_per_job(jobs, profile) -> list[tuple[Job, float]]`
- 返回每个岗位的独立贴合度分数列表，按分数降序排列
- 现有 `evaluate_fitness()` 不变（保持向后兼容）

**`boss_analyzer/models/report.py`**
- `AnalysisReport` 新增字段 `job_fitness_list: list[tuple[Job, float]]`
- 默认为空列表

**`boss_analyzer/main.py`**
- `analyze()` 函数中，有 profile 时同时计算 `job_fitness_list`

**`boss_analyzer/report/templates/report.html`**
- 在"岗位贴合度"维度后新增"岗位匹配排名"表格
- 展示：排名、岗位名、薪资、经验要求、技能、匹配分、链接

---

## Feature 2：岗位搜索与匹配排序（全新功能）

### 新增文件

| 文件 | 职责 |
|------|------|
| `boss_analyzer/models/ranking.py` | `JobMatch` 数据类（公司+岗位+各维度分+排名） |
| `boss_analyzer/analyzers/ranking.py` | `rank_matches()` 排序聚合函数 |
| `boss_analyzer/report/templates/ranking.html` | 排名报告 HTML 模板 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `boss_analyzer/scrapers/boss.py` | 新增 `search_jobs_by_position(position, city_code, limit)` 方法 |
| `boss_analyzer/main.py` | 新增 `search()` 函数 + `--search` / `--city` / `--limit` CLI 参数 |
| `boss_analyzer/report/html_report.py` | 新增 `generate_ranking_report()` 函数 |
| `boss_analyzer/config.py` | 新增 `CITY_CODES` 字典 + `SEARCH_LIMIT = 20` |

### 数据模型

```python
# boss_analyzer/models/ranking.py
@dataclass
class JobMatch:
    company: Company
    job: Job
    fitness_score: float = 0.0      # 岗位贴合度（必有）
    legitimacy_score: float = 0.0   # 企业真实性（可选，--full时计算）
    freshness_score: float = 0.0    # 招聘真实性（可选，--full时计算）
    rank: int = 0

    @property
    def overall_score(self) -> float:
        # fitness:0.6, legitimacy:0.25, freshness:0.15（有则计入）
    
    @property
    def match_level(self) -> str:
        # 强烈推荐(≥80) / 推荐(≥65) / 一般(≥50) / 不推荐
```

### 搜索流程

```
search(position, profile, city, limit, full_analysis)
  │
  ├─ BossScraper.search_jobs_by_position()
  │    └─ 访问 zhipin.com/web/geek/job?query={position}&city={city_code}
  │    └─ 提取每张卡片: job + 基础 company 信息（名称、规模、行业、公司URL）
  │
  ├─ [快速模式] 仅用 evaluate_fitness() 打分 → 排序
  │
  ├─ [完整模式 --full] 对 Top-N 公司额外抓取:
  │    ├─ TianyanchaScraper → legitimacy_score
  │    └─ freshness → freshness_score
  │
  └─ generate_ranking_report(matches) → HTML
```

### CLI 用法

```bash
# 现有用法（不变）
python -m boss_analyzer "字节跳动" --experience 3 --skills Python

# 新增：岗位搜索
python -m boss_analyzer --search "Python后端工程师" --experience 3 --skills Python Django
python -m boss_analyzer --search "数据分析师" --city 上海 --limit 30 --experience 2 --skills SQL Python
python -m boss_analyzer --search "前端工程师" --city 北京 --full --salary-min 20 --salary-max 40
```

### 排名报告内容

HTML 报告展示：
- 搜索条件摘要（岗位名、城市、用户画像）
- 排名榜单表格：排名 / 公司名 / 岗位名 / 薪资 / 经验要求 / 综合分 / 匹配级别 / 操作链接
- 分数分布可视化（进度条）
- 风险提示（低贴合度 / 可疑公司）

---

## 实施顺序

1. `config.py` — 添加 CITY_CODES + SEARCH_LIMIT
2. `models/ranking.py` — JobMatch 数据类
3. `scrapers/boss.py` — 添加 search_jobs_by_position()
4. `analyzers/fitness.py` — 添加 evaluate_fitness_per_job()
5. `models/report.py` — 添加 job_fitness_list 字段
6. `analyzers/ranking.py` — rank_matches() 函数
7. `main.py` — search() 函数 + CLI 参数
8. `report/html_report.py` — generate_ranking_report()
9. `report/templates/ranking.html` — 排名报告模板
10. `report/templates/report.html` — 添加逐岗排名表格

## 验收标准

- [ ] `python -m boss_analyzer "公司名" --experience 3 --skills Python` 报告中显示逐岗匹配排名
- [ ] `python -m boss_analyzer --search "岗位名" --experience 3 --skills Python` 生成排名 HTML 报告
- [ ] `--city 上海` 过滤城市正常工作
- [ ] `--full` 模式额外计算真实性分数
- [ ] 无 profile 时 search 模式仍可运行（仅展示岗位列表，不评分）
- [ ] 现有 analyze 功能完全不受影响
