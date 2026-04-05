# Investment Commander（投资团队编排器）

> 🤖 产业逻辑（70%）+ 量化择时（30%）= 每日 3 只精选推荐
>
> 📍 **定位**：全球新兴题材发现 × A股/港股落地验证，适用于关注中美科技趋势的个人投资者。

### 快速启动（推荐方式）
```bash
# ClawTeam 多Agent协作（新版）
clawteam launch investment-commander --goal "AI算力 芯片 商业航天" --team-name my-invest

# 直接运行脚本（经典方式）
python3 scripts/morning_briefing.py        # 完整早报（含热点题材）
python3 scripts/commander_final.py        # 产业优先选股
python3 scripts/hot_sector_tracker.py     # 热点题材分析
```
> 不做决策，只做调度 —— 让专业的人做专业的事

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 一句话说明

Investment Commander 是**全球题材发现 × A股落地验证**的投资决策系统，通过多 Agent 协作——产业分析师 × 量化择时官 × 风控验证员——每日输出 3 只精选股票，并给出精确的买卖点位与操作清单。

**使用方式**：在钉钉或 Telegram 对我说"今日选股"，90 秒内收到报告。

---

## 核心特色

### 🎯 双轨推荐：产业 × 量化

| 轨道 | 分析师 | 负责 |
|------|--------|------|
| 产业逻辑（70%） | 产业分析师 | 赛道景气度、竞争格局、催化剂事件 |
| 量化择时（30%） | 量化分析师 | 均线、MACD、RSI、布林带、动量指标综合打分 |
| 仲裁 | 风控验证员 | 过滤高杠杆、流动性风险，输出最终推荐 |

两个通道独立打分，最终加权融合——既有基本面的深度，又有技术面的择时。

### 📊 遗传算法指标探索

指标组合不是拍脑袋定的，是用**遗传算法在 1831 条历史回测记录上进化**出来的。

- **指标库**：41 个指标（均线交叉、RSI、MACD、布林带、动量、MA 斜率等）
- **互斥约束**：防止逻辑矛盾的指标组合（如同时出现"金叉"和"死叉"）
- **composite_score**：分离度 × 0.6 + alpha × 0.4，高区分度才是好策略

### 🔬 回测驱动进化

每次市场环境变化，指标组合可能失效。系统会持续用**最新回测数据**重新评估组合表现，动态淘汰低效指标。

### 🛡️ 三层风控

1. **宏观风险过滤**：大盘指数（沪深 300）下行趋势时自动降仓
2. **基本面风控**：排除亏损股、微盘股（流通市值 < 50 亿）
3. **量化风控**：单一行业仓位上限、止损纪律

---

## 快速开始

### 前置依赖

```bash
pip install akshare pandas numpy
# OpenClaw 已包含在系统中
```

### 使用方式

**方式一：钉钉 / Telegram 触发**
```
/选股 今日
/持仓分析 301268
/问股 688190
```

**方式二：命令行直接运行**
```bash
cd skills/investment-commander
python3 scripts/commander_final.py --stock 301268
```

---

## 目录结构

```
investment-commander/
├── SKILL.md                    # 技能定义（OpenClaw 加载用）
├── RULES.md                   # Agent 角色规则
├── README.md                   # 本文件
├── scripts/
│   ├── commander_final.py      # 编排主入口
│   ├── indicator_explorer.py   # 遗传算法指标探索
│   ├── industry_analyst.py     # 产业分析师
│   ├── quant_timing_reference.py # 量化择时官
│   ├── alan_custom_screener.py # Alan 定制选股器
│   ├── historical_backtest.py  # 历史回测生成
│   └── market_filter.py        # 大盘宏观过滤
├── invest-evolution/           # 投研自进化系统
│   ├── SKILL.md
│   ├── README.md
│   ├── scripts/
│   │   ├── catalyst_radar.py       # 催化剂雷达
│   │   ├── performance_tracker.py  # 战绩追踪器
│   │   ├── failure_diagnosis.py    # 归因诊断器
│   │   └── backtest_validator.py   # 回测验证器
│   └── data/
│       ├── performance/
│       ├── diagnosis/
│       └── catalyst_updates/
├── config/
│   ├── best_indicators.json    # 当前最优指标组合
│   ├── indicator_history.jsonl  # 探索历史记录
│   ├── indicator_library.json   # 指标库定义
│   └── screener_params.yaml    # 选股参数配置
└── templates/
    └── report_template.md       # 报告模板
```

---

## 版本历史

### v2.1.0 (2026-04-05) — invest-evolution 投研自进化系统
- **新增 `invest-evolution/` 子模块**：战绩追踪 → 催化剂雷达 → 归因诊断 → 回测验证
  - `catalyst_radar.py`：每日 08:00 扫描新催化剂/冷却预警
  - `performance_tracker.py`：每日 16:30 追踪推荐股票真实收益（Tushare）
  - `failure_diagnosis.py`：每日 17:00 失败推荐归因（催化剂/择时/风控）
  - `backtest_validator.py`：每日 17:30 验证归因建议是否成立
- 所有进化建议只推送不自动执行，需人工确认
- Telegram 推送通道（替代钉钉）

### v2.0.0 (2026-04-04) — ClawTeam 集成
- **ClawTeam 模板**：`clawteam/templates/investment-commander.toml`
  - 5个 Agent 协作：Commander + 产业分析师 + 量化分析师 + 风控验证员 + 新闻情绪分析师
  - 启动命令：`clawteam launch investment-commander --goal "AI算力 芯片"`
- **热点题材追踪器**：`hot_sector_tracker.py`（akshare涨停板 + last30days全球新兴题材）
- **早报增强**：新增「热点题材」模块，A股涨停验证 + last30days全球趋势交叉
- **美股数据**：改用 Yahoo Finance（绕过 akshare 稳定性问题）

### v1.3.1 (2026-04-04)
- 新增热点题材追踪器：hot_sector_tracker.py（akshare涨停板 + last30days全球新兴题材）
- 早报新增「热点题材」模块：A股涨停验证 + last30days Reddit全球趋势交叉
- hot_sectors_cache.json 缓存，供 commander_final.py 读取推荐催化剂
- 美股数据改用 Yahoo Finance（绕过 akshare 稳定性问题）

### v1.3 (2026-04-04)
- 持仓股产业背景自动注入：portfolio.json → STOCK_CATALYST_MAP → 早报/推荐自动带产业说明
- 持仓排除逻辑：推荐时自动过滤用户已持仓股票（需配置 portfolio.json）
- 量化指标升级：best_indicators v2（composite_score 17.09 → 19.31，高区胜率 28.1% vs 随机 22.1%）

### v1.2 (2026-03-31)
- 遗传算法指标探索（indicator_explorer v2.0）
- v3 回测数据：MACD / 布林带 / 动量 / MA 斜率等 12 个新字段
- 指标库 31 → **41 个**

### v1.0 (2026-03-29)
- 初始版本

---

## 致谢

- 数据源：[AKShare](https://github.com/akfamily/akshare) · [Tushare](https://tushare.pro/)
- 量化框架灵感：[TradingAgents](https://github.com/goldgeyser/TradingAgents)
- A股监控基础：[JamesMei/a-stock-monitor](https://github.com/JamesMei/a-stock-monitor)
