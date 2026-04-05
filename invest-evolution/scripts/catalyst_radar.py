#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
催化剂雷达 - catalyst_radar.py
版本: 1.0.0
作者: Alan Li
日期: 2026-04-05

功能：自动发现新催化剂、监测旧催化剂冷却
数据源：
  - 同花顺新闻监控输出（market-news-monitor）
  - Tavily/Exa 搜索（按赛道关键词）
  - Investment Commander 催化剂知识库
输出：
  - 新催化剂 / 催化剂升级 / 催化剂冷却 三种信号
  - data/catalyst_updates/{date}.json
  - Telegram 推送
触发时间：每天 08:00（盘前）
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

WORKSPACE = Path.home() / ".openclaw" / "workspace"
SKILL_DIR = WORKSPACE / "skills" / "investment-commander"
DATA_DIR = Path(__file__).parent.parent / "data" / "catalyst_updates"
MEMORY_DIR = WORKSPACE / "memory"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def send_telegram_notification(message: str):
    """通过 OpenClaw Telegram session 推送"""
    import subprocess
    cmd = [
        'openclaw', 'message', 'send',
        '--channel', 'telegram',
        '--target', '8710019510',
        '--message', message
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15)
    except Exception as e:
        print(f"[通知] Telegram 推送失败: {e}")


# 默认催化剂知识库（找不到时使用）
DEFAULT_CATALYST_KB = {
    "active": [
        {
            "sector": "半导体/芯片",
            "catalysts": ["国产替代加速", "政策扶持", "AI算力需求爆发"],
            "last_updated": "2026-03-20",
            "strength": "high"
        },
        {
            "sector": "智能驾驶/汽车电子",
            "catalysts": ["L3量产加速", "华为合作订单", "政策补贴"],
            "last_updated": "2026-03-22",
            "strength": "medium"
        },
        {
            "sector": "SST固态变压器",
            "catalysts": ["SST技术突破", "国网招标启动"],
            "last_updated": "2026-03-28",
            "strength": "medium"
        },
        {
            "sector": "新材料",
            "catalysts": ["碳纤维量产", "军工订单落地"],
            "last_updated": "2026-03-25",
            "strength": "medium"
        }
    ],
    "cooling": [
        {
            "sector": "消费电子",
            "reason": "连续2周无新催化",
            "last_seen": "2026-03-10"
        }
    ]
}


def load_catalyst_kb() -> Dict:
    """加载催化剂知识库"""
    # 尝试从 investment-commander 目录加载
    patterns = [
        SKILL_DIR / "industry_analyst.py",
        SKILL_DIR / "catalyst_kb.json",
        SKILL_DIR / "data" / "catalysts.json",
        SKILL_DIR / "knowledge" / "catalysts.json",
    ]

    for p in patterns:
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8")
                # 尝试 JSON 解析
                if p.suffix == ".json":
                    return json.loads(content)
                # 从 Python 文件中提取知识库
                kb_match = re.search(r'CATALYST_KB\s*=\s*(\{.*?\})', content, re.DOTALL)
                if kb_match:
                    return json.loads(kb_match.group(1))
            except Exception:
                pass

    print("[催化剂雷达] 未找到知识库，使用默认知识库")
    return DEFAULT_CATALYST_KB


def load_recent_news(days: int = 3) -> List[str]:
    """加载近 N 天的新闻"""
    news_items = []
    cutoff = datetime.now() - timedelta(days=days)

    # 扫描 memory 目录中的日志
    if MEMORY_DIR.exists():
        for mf in MEMORY_DIR.glob("*.md"):
            try:
                # 从文件名判断日期
                fname = mf.name
                date_m = re.search(r'(\d{4}-\d{2}-\d{2})', fname)
                if date_m:
                    file_date = datetime.strptime(date_m.group(1), "%Y-%m-%d")
                    if file_date < cutoff:
                        continue

                content = mf.read_text(encoding="utf-8")
                # 提取新闻相关段落
                lines = content.split("\n")
                for line in lines:
                    # 过滤新闻类内容
                    if any(kw in line for kw in ["新闻", "催化", "政策", "突破", "订单", "量产", "大涨", "涨停"]):
                        if len(line) > 10:
                            news_items.append(line.strip())
            except Exception:
                pass

    # 扫描 market-news-monitor 输出目录
    news_dir = WORKSPACE / "output" / "news"
    if news_dir.exists():
        for nf in news_dir.glob("*.json"):
            try:
                data = json.loads(nf.read_text())
                if isinstance(data, list):
                    for item in data:
                        news_items.append(str(item))
            except Exception:
                pass

    return news_items


def extract_sectors_from_news(news_items: List[str]) -> Dict[str, List[str]]:
    """从新闻中提取赛道关键词"""
    sector_keywords = {
        "固态电池": ["固态电池", "全固态", "硫化物", "氧化物"],
        "半导体/芯片": ["半导体", "芯片", "AI芯片", "GPU", "HBM"],
        "智能驾驶": ["智能驾驶", "自动驾驶", "L3", "L4", "华为智驾"],
        "SST固态变压器": ["固态变压器", "SST", "电力变压器"],
        "新材料": ["碳纤维", "复合材料", "军工材料"],
        "军工": ["军工", "国防", "军品"],
        "光伏/新能源": ["光伏", "TOPCon", "HJT", "锂电"],
        "创新药": ["创新药", "ADC", "GLP-1"],
    }

    sector_mentions = {sector: [] for sector in sector_keywords}

    for news in news_items:
        for sector, keywords in sector_keywords.items():
            for kw in keywords:
                if kw in news:
                    sector_mentions[sector].append(news)
                    break

    return sector_mentions


def detect_new_catalysts(
    sector_mentions: Dict[str, List[str]],
    kb: Dict
) -> List[Dict]:
    """发现新催化剂"""
    new_catalysts = []

    known_sectors = set(s.get("sector", "") for s in kb.get("active", []))
    known_sectors.update(s.get("sector", "") for s in kb.get("cooling", []))

    for sector, mentions in sector_mentions.items():
        if sector not in known_sectors and mentions:
            new_catalysts.append({
                "sector": sector,
                "mentions": mentions[:3],  # 最多3条
                "strength": "unknown",
                "first_seen": datetime.now().strftime("%Y-%m-%d")
            })

    return new_catalysts


def detect_catalyst_upgrades(
    sector_mentions: Dict[str, List[str]],
    kb: Dict
) -> List[Dict]:
    """检测催化剂升级"""
    upgrades = []

    active_sectors = {s["sector"]: s for s in kb.get("active", [])}

    for sector, mentions in sector_mentions.items():
        if sector in active_sectors and len(mentions) >= 3:
            current = active_sectors[sector]
            # 新增了更多催化事件
            existing_count = len(current.get("catalysts", []))
            if len(mentions) > existing_count:
                upgrades.append({
                    "sector": sector,
                    "previous_strength": current.get("strength", "unknown"),
                    "new_strength": "high" if len(mentions) >= 5 else "medium",
                    "new_mentions": len(mentions),
                    "catalysts": mentions[:3]
                })

    return upgrades


def detect_cooling_catalysts(
    kb: Dict,
    news_days: int = 5
) -> List[Dict]:
    """检测催化剂冷却（连续N天无新催化）"""
    cooling = []
    today = datetime.now()

    for sector_item in kb.get("active", []):
        sector = sector_item["sector"]
        last_updated = sector_item.get("last_updated", "")
        if not last_updated:
            continue

        try:
            last_date = datetime.strptime(last_updated, "%Y-%m-%d")
            days_since = (today - last_date).days
            if days_since >= news_days:
                cooling.append({
                    "sector": sector,
                    "days_without_catalyst": days_since,
                    "previous_strength": sector_item.get("strength", "unknown"),
                    "last_updated": last_updated,
                    "threshold_days": news_days
                })
        except Exception:
            pass

    return cooling


def build_update_report(
    new_catalysts: List[Dict],
    upgrades: List[Dict],
    cooling: List[Dict],
    kb: Dict
) -> Dict:
    """构建更新报告"""
    report = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "new_catalysts": new_catalysts,
        "catalyst_upgrades": upgrades,
        "cooling_warnings": cooling,
        "total_active_sectors": len(kb.get("active", [])),
        "total_cooling_sectors": len(kb.get("cooling", [])) + len(cooling),
    }
    return report


def format_telegram_message(report: Dict) -> str:
    """格式化Telegram 推送消息"""
    lines = ["【催化剂雷达】"]

    if report["new_catalysts"]:
        lines.append("\n🆕 新发现：")
        for nc in report["new_catalysts"][:3]:
            lines.append(f"  • {nc['sector']}：{nc['mentions'][0][:50] if nc['mentions'] else '新催化事件'}")
    else:
        lines.append("\n🆕 新发现：无")

    if report["catalyst_upgrades"]:
        lines.append("\n⬆️ 催化剂升级：")
        for up in report["catalyst_upgrades"][:3]:
            lines.append(f"  • {up['sector']}：强度从 {up['previous_strength']} 升至 {up['new_strength']}")
    else:
        lines.append("\n⬆️ 催化剂升级：无")

    if report["cooling_warnings"]:
        lines.append("\n❄️ 冷却预警：")
        for cw in report["cooling_warnings"][:3]:
            lines.append(f"  • {cw['sector']}：连续 {cw['days_without_catalyst']} 天无新催化事件")
    else:
        lines.append("\n❄️ 冷却预警：无")

    lines.append(f"\n📊 当前活跃赛道：{report['total_active_sectors']} 个")
    return "\n".join(lines)


def run_catalyst_radar(news_days: int = 5):
    """主函数"""
    print(f"[催化剂雷达] 开始扫描（冷却阈值：{news_days}天）...")

    # 1. 加载知识库
    kb = load_catalyst_kb()
    print(f"  知识库：{len(kb.get('active', []))} 个活跃赛道")

    # 2. 加载近期新闻
    news_items = load_recent_news(days=news_days)
    print(f"  采集到 {len(news_items)} 条相关新闻")

    # 3. 提取赛道提及
    sector_mentions = extract_sectors_from_news(news_items)
    active_mentions = {s: m for s, m in sector_mentions.items() if m}
    print(f"  有提及的赛道：{len(active_mentions)} 个")

    # 4. 检测三类信号
    new_catalysts = detect_new_catalysts(sector_mentions, kb)
    upgrades = detect_catalyst_upgrades(sector_mentions, kb)
    cooling = detect_cooling_catalysts(kb, news_days)

    print(f"  新催化剂：{len(new_catalysts)} 个")
    print(f"  催化剂升级：{len(upgrades)} 个")
    print(f"  冷却预警：{len(cooling)} 个")

    # 5. 构建报告
    report = build_update_report(new_catalysts, upgrades, cooling, kb)

    # 6. 保存
    today_str = datetime.now().strftime("%Y%m%d")
    output_file = DATA_DIR / f"{today_str}.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 7. 格式化Telegram 消息
    dingtalk_msg = format_telegram_message(report)
    print(f"\n{dingtalk_msg}")
    send_telegram_notification(dingtalk_msg)

    print(f"\n[催化剂雷达] 完成，报告已保存至 {output_file}")
    return report


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    run_catalyst_radar(news_days=days)
