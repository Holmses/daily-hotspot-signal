# Daily Hotspot Signal

每天自动抓取公开热点源，筛出“有关注度但同角度竞争较低”的视频选题，并生成 Markdown 选题日报。

这个项目按 `a-share-v1-signal` 的方式组织：`src/` 包布局、`pyproject.toml` 暴露 CLI、`run-daily` 一次性执行、`run-scheduler` 常驻定时执行、Docker Compose 每天自动跑。

## 项目结构

```text
daily-hotspot-signal/
├── configs/
│   └── sources.toml.example
├── data/
│   ├── processed/
│   └── raw/
├── logs/
├── reports/
│   └── generated/
├── src/
│   └── hotspot_signal/
│       ├── data/
│       ├── domain/
│       ├── report/
│       ├── scheduler/
│       ├── sources/
│       └── strategy/
└── tests/
```

## 快速开始

```bash
cd daily-hotspot-signal
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

列出数据源：

```bash
.venv/bin/hotspot-signal list-sources --config configs/sources.toml.example
```

抓取并生成今天的选题日报：

```bash
.venv/bin/hotspot-signal run-daily --config configs/sources.toml.example
```

输出文件：

- `data/raw/hotspots-raw-YYYYMMDD-HHMMSS.json`
- `data/processed/topic-candidates-YYYYMMDD.json`
- `reports/generated/hotspot-report-YYYYMMDD.md`

## 定时执行

本地常驻：

```bash
.venv/bin/hotspot-signal run-scheduler \
  --config configs/sources.toml.example \
  --run-at 09:10 \
  --run-on-start
```

Docker Compose：

```bash
docker compose up -d --build hotspot-signal-daily
```

默认按 `configs/sources.toml.example` 里的 `[runtime].daily_run_time` 和 `Asia/Shanghai` 时区执行。

如果本机 Python 证书链正常，可以把 `[runtime].verify_ssl` 改成 `true`。当前示例配置设为 `false`，是为了避开本机抓公开网页时常见的 CA 证书错误。

## 数据源配置

支持三类公开源：

- `rss`：RSS / Atom 新闻源
- `json`：公开 JSON / JSONP 热榜接口
- `html`：普通 HTML 榜单页链接提取

每个源可以设置：

- `reliability`：来源可信度，越高越容易进入候选
- `category`：`official`、`news`、`technology`、`trend` 等
- `include_keywords` / `exclude_keywords`：过滤标题和摘要
- `items_path`、`title_fields`、`url_fields`：JSON 源字段映射

默认启用源包含中国政府网要闻 JSON 和百度热搜。`configs/sources.toml.example` 里也放了 RSSHub 知乎热榜、Hacker News 等可选源，公共实例或海外站点可能限流或超时，按需要启用即可。

## 评分逻辑

程序会把原始条目聚类去重，然后计算：

- 热度：榜单排名或源内热度字段
- 新鲜度：发布时间或抓取时间
- 稀缺度：采集源重复度、最近历史是否出现、是否带公告/新规/监管函等低竞争线索
- 冲击力：突发、监管、处罚、禁令、制裁等关键词
- 可信度：来源配置的可靠性
- 风险惩罚：网传、爆料、疑似、传闻等词会降权并提醒核验

注意：程序给的是低竞争初筛，不会替你确认平台上“完全没人做”。报告会为每个候选题给出搜索词，发布前需要查抖音、B站、小红书、YouTube 最近 24 小时同角度数量。

## 测试

```bash
.venv/bin/python -m pytest
```
