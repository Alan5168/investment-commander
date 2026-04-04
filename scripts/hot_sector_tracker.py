#!/usr/bin/env python3
"""
热点题材追踪器 (hot_sector_tracker.py)
功能：分析近30天A股热点题材 + 融合 last30days 全球新兴题材

数据来源：
1. akshare 涨停板（A股落地验证）
2. last30days Reddit（全球新兴题材）

用途：
- 供 morning_briefing 调用
- 供 commander_final.py --catalyst 调用
- 输出 config/hot_sectors_cache.json 供其他脚本读取
"""

import json
import subprocess
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

# 路径配置
SKILL_DIR = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor')
CONFIG_DIR = SKILL_DIR / 'config'
LAST30_DIR = Path.home() / 'Documents' / 'Last30Days'
CACHE_FILE = CONFIG_DIR / 'hot_sectors_cache.json'

# A股题材关键词映射（涨停板行业 → 标准题材名）
BOARD_KEYWORDS = {
    '半导体': '半导体/芯片',
    '集成电路': '半导体/芯片',
    'AI': 'AI算力',
    '算力': 'AI算力',
    '大模型': 'AI算力',
    '商业航天': '商业航天',
    '卫星': '商业航天',
    '低空经济': '低空经济/eVTOL',
    '无人机': '低空经济/eVTOL',
    'eVTOL': '低空经济/eVTOL',
    '新能源': '新能源/储能',
    '储能': '新能源/储能',
    '锂电池': '新能源/储能',
    '汽车零部件': '新能源汽车',
    '汽车整车': '新能源汽车',
    '智能驾驶': '新能源汽车',
    '机器人': '人形机器人',
    '人形机器人': '人形机器人',
    '核能': '核能/核聚变',
    '核电': '核能/核聚变',
    '量子': '量子计算',
    '脑机接口': '脑机接口',
    '生物医药': '生物制造',
    '医疗器械': '医疗器械',
}


def get_zt_hot_sectors(trading_days: int = 5) -> list:
    """从近N个交易日涨停板提取热门题材"""
    try:
        import akshare as ak
        trend = Counter()
        check = datetime.now()

        for _ in range(trading_days * 2):  # 多取几天确保覆盖
            date_str = check.strftime('%Y%m%d')
            try:
                df = ak.stock_zt_pool_em(date=date_str)
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        industry = str(row.get('所属行业', ''))
                        # 先用关键词匹配
                        matched = False
                        for kw, sector in BOARD_KEYWORDS.items():
                            if kw in industry:
                                trend[sector] += 1
                                matched = True
                        # 没有匹配到关键词，用原行业
                        if not matched and industry not in ('-', '', 'None'):
                            trend[industry] = trend.get(industry, 0) + 0.3
            except:
                pass
            check -= timedelta(days=1)

        return trend.most_common(8)
    except Exception as e:
        return []


def get_zt_summary(trading_days: int = 5) -> dict:
    """获取近N日涨停板统计摘要"""
    try:
        import akshare as ak
        total_count = 0
        check = datetime.now()

        for _ in range(trading_days * 2):
            date_str = check.strftime('%Y%m%d')
            try:
                df = ak.stock_zt_pool_em(date=date_str)
                if df is not None and len(df) > 0:
                    total_count += len(df)
            except:
                pass
            check -= timedelta(days=1)

        return {'total_zt': total_count, 'avg_daily': total_count / trading_days}
    except:
        return {'total_zt': 0, 'avg_daily': 0}


def parse_last30days_output(topic: str = "china ai semiconductor robot ev battery 2026") -> dict:
    """
    解析 last30days 输出的 markdown 文件，提取标题和分数
    """
    topic_slug = re.sub(r'\s+', '-', topic.strip())[:60]
    md_file = LAST30_DIR / f"{topic_slug}-raw.md"

    # 也尝试模糊匹配
    if not md_file.exists():
        candidates = list(LAST30_DIR.glob(f"{topic_slug[:20]}*.md"))
        if candidates:
            md_file = candidates[0]

    if not md_file.exists():
        return {'themes': [], 'top_threads': []}

    try:
        content = md_file.read_text()
        threads = []

        # 解析 R+数字 格式的线程
        thread_pattern = re.compile(
            r'\*\*R(\d+)\*\*.*?(?:https?://[^\s]+)?\s*\n.*?score:\s*(\d+)',
            re.DOTALL
        )

        # 找所有线程标题（更简单的方法）
        lines = content.split('\n')
        current_thread = {}
        threads = []

        for line in lines:
            m = re.match(r'\*\*R(\d+)\*\*.*?(?:https?://[^\s]+)?', line)
            if m:
                if current_thread:
                    threads.append(current_thread)
                current_thread = {'rank': int(m.group(1))}

            score_m = re.search(r'\[(\d+)pts', line)
            if score_m and current_thread:
                current_thread['score'] = int(score_m.group(1))

            # 提取关键词
            for kw in ['humanoid robot', 'brain computer', 'brain-machine', 'AI', 'semiconductor',
                       'China', 'battery', 'EV', 'quantum', 'nuclear fusion', 'low altitude', 'eVTOL',
                       'satellite', 'SST', 'solid-state']:
                if kw.lower() in line.lower():
                    current_thread['keywords'] = current_thread.get('keywords', [])
                    current_thread['keywords'].append(kw)

        if current_thread:
            threads.append(current_thread)

        # 排序取前5
        threads.sort(key=lambda x: x.get('score', 0), reverse=True)
        top = threads[:5]

        # 映射到标准题材
        theme_map = {
            'humanoid robot': '人形机器人',
            'brain computer': '脑机接口',
            'brain-machine': '脑机接口',
            'AI': 'AI算力',
            'semiconductor': '半导体/芯片',
            'China': '中国战略',
            'battery': '新能源/储能',
            'EV': '新能源汽车',
            'quantum': '量子计算',
            'nuclear fusion': '核能/核聚变',
            'low altitude': '低空经济/eVTOL',
            'eVTOL': '低空经济/eVTOL',
            'satellite': '商业航天',
            'SST': 'SST/电力电子',
            'solid-state': '固态电池',
        }

        themes = Counter()
        for t in top:
            for kw in t.get('keywords', []):
                mapped = theme_map.get(kw.lower())
                if mapped:
                    themes[mapped] += t.get('score', 0)

        return {
            'themes': [t for t, _ in themes.most_common(5)],
            'top_threads': top,
            'source': 'last30days',
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
    except Exception as e:
        return {'themes': [], 'top_threads': [], 'error': str(e)}


def generate_hot_sector_report(trading_days: int = 5) -> str:
    """生成热点题材报告"""
    lines = [
        f"🔥 热点题材追踪（近{trading_days}交易日）",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 1. A股涨停板热门题材
    zt_sectors = get_zt_hot_sectors(trading_days)
    zt_summary = get_zt_summary(trading_days)
    lines.append(f"📊 A股涨停板（近{trading_days}交易日共{int(zt_summary['total_zt'])}只涨停，日均{zt_summary['avg_daily']:.0f}只）")

    if zt_sectors:
        lines.append("  涨停板热门题材:")
        for sector, count in zt_sectors[:6]:
            bar = '█' * int(count)
            lines.append(f"  🔥 {sector}: {count:.0f}次 {bar}")
    else:
        lines.append("  暂无涨停板数据")
    lines.append("")

    # 2. last30days 全球新兴题材
    lines.append("🌐 last30days 全球新兴题材（Reddit 30天）")
    l30_result = parse_last30days_output()
    if l30_result.get('themes'):
        lines.append(f"  发现主题: {' / '.join(l30_result['themes'])}")
        lines.append(f"  数据来源: {l30_result.get('source', 'unknown')} / {l30_result.get('updated', '')}")
    else:
        if 'error' in l30_result:
            lines.append(f"  解析失败: {l30_result['error']}")
        else:
            lines.append("  暂无数据（可运行 last30days 更新）")
    lines.append("")

    # 3. 综合推荐催化剂
    all_themes = Counter()
    for sector, count in zt_sectors[:6]:
        all_themes[sector] = count * 2  # A股落地权重更高
    for theme in l30_result.get('themes', [])[:4]:
        all_themes[theme] += 1

    top_catalysts = [t for t, _ in all_themes.most_common(4)]

    lines.extend([
        "🎯 建议关注题材（涨停验证 + 全球趋势）:",
        f"  {' / '.join(top_catalysts) if top_catalysts else '数据不足'}",
        "",
        "─" * 40,
        f"  推荐命令:",
        f"  python3 scripts/commander_final.py --catalyst \"{' '.join(top_catalysts)}\"",
        f"",
        f"  缓存文件: {CACHE_FILE}",
    ])

    # 保存缓存
    cache_data = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'zt_sectors': dict(zt_sectors[:8]),
        'zt_summary': zt_summary,
        'l30_themes': l30_result.get('themes', []),
        'top_catalysts': top_catalysts,
    }
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))

    return '\n'.join(lines)


if __name__ == '__main__':
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(generate_hot_sector_report(trading_days=days))
