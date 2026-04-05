---
name: invest-evolution
description: Investment Commander 投研策略自进化系统 - 战绩追踪、催化剂雷达、归因诊断、回测验证，让投研系统越用越准。
version: 1.0.0
author: Alan Li
date: 2026-04-05
---

# invest-evolution 投研自进化系统

## 概述

让 Investment Commander 的投研系统具备自我进化的能力。通过追踪推荐战绩 → 发现催化剂变化 → 诊断失败原因 → 验证进化建议，形成完整的反馈闭环。

## 四大组件

| 组件 | 文件 | 触发时间 | 功能 |
|------|------|----------|------|
| 战绩追踪器 | `performance_tracker.py` | 每天 16:30 | 追踪推荐股票的实际表现，判定 win/fail/neutral |
| 催化剂雷达 | `catalyst_radar.py` | 每天 08:00 | 发现新催化剂、监测旧催化剂冷却 |
| 归因诊断器 | `failure_diagnosis.py` | 每天 17:00 | 对失败推荐做反事实归因分析 |
| 回测验证器 | `backtest_validator.py` | 每天 17:30 | 验证归因建议是否经得起回测 |

## Cron 时间线

```
08:00  → catalyst_radar.py（催化剂雷达，盘前扫描）
09:15  → 早盘选股（已有，不动）
15:30  → 盘后异动筛选（已有，不动）
16:30  → performance_tracker.py（战绩追踪，收盘后）
17:00  → failure_diagnosis.py（归因诊断）
17:30  → backtest_validator.py（回测验证）
```

## 数据流

```
每日推荐记录（memory/daily-log）
       ↓
catalyst_radar.py → 发现新/冷却催化剂 → 钉钉推送
       ↓
performance_tracker.py → 追踪战绩 → data/performance/{date}.jsonl
       ↓
failure_diagnosis.py → 归因诊断 → data/diagnosis/{date}_{stock}.json
       ↓
backtest_validator.py → 验证建议 → 钉钉推送（等待确认）
```

## 核心原则

1. **所有修改建议只推送不自动执行**，等用户确认
2. 与 `skills/meta-harness/` 完全独立
3. 数据存在 `data/` 子目录下，不污染其他目录
4. 只使用 tushare / requests / json / os / datetime / pathlib

## 目录结构

```
skills/invest-evolution/
├── SKILL.md
├── README.md
├── scripts/
│   ├── performance_tracker.py   # 战绩追踪器
│   ├── catalyst_radar.py      # 催化剂雷达
│   ├── failure_diagnosis.py    # 归因诊断器
│   └── backtest_validator.py   # 回测验证器
└── data/
    ├── performance/            # 战绩记录
    ├── diagnosis/              # 诊断报告
    └── catalyst_updates/       # 催化剂变动记录
```
