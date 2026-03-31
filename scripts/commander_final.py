#!/usr/bin/env python3
"""
Investment Commander v2 - 产业优先，技术面二次过滤

流程：催化剂 → 产业池(30-50只) → 技术面打分 → 候选池(10-15只) → 推荐3只
"""

import json
import subprocess
import re
import sys
from pathlib import Path
from datetime import datetime

# 添加 shared 目录到路径
SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from stock_client import get_daily
from alan_custom_screener import calc_technical_score


def get_industry_pool(catalyst: str) -> dict:
    """调用产业分析师，获取受益标的池"""
    from industry_analyst import parse_catalysts, analyze_catalyst
    catalysts = parse_catalysts(catalyst)
    return analyze_catalyst(catalysts)


def score_industry_pool(codes: list) -> list:
    """
    对产业池的股票做技术面打分
    只扫描30-50只，速度快，不需要批量限流
    """
    results = []
    for code in codes:
        try:
            df = get_daily(code, days=60)
            if df is None or len(df) < 20:
                continue

            score_result = calc_technical_score(df)
            results.append({
                'code': code,
                'score': score_result['score'],
                'signals': score_result['signals'],
                'ma20': score_result['ma20'],
                'vol_ratio': score_result['vol_ratio'],
                'rsi': score_result['rsi'],
                'close': float(df.iloc[-1]['收盘']),
                'change_pct': float(df.iloc[-1].get('涨跌幅', 0))
            })
        except Exception as e:
            continue

    # 按技术面评分排序
    return sorted(results, key=lambda x: x['score'], reverse=True)


def select_final_3_from_scored(scored: list, industry_result: dict) -> list:
    """
    从已打分的产业股里选3只
    优先级：直接受益 > 间接受益，同级内按技术面评分排序
    """
    direct = set(industry_result['pool']['direct'])

    recommendations = []

    # 先从直接受益里按技术面评分取（最多2只）
    for s in scored:
        if s['code'] in direct and len(recommendations) < 2:
            priority = 'A' if s['score'] >= 60 else 'C'
            recommendations.append({
                'code': s['code'],
                'priority': priority,
                'score': s['score'],
                'signals': s['signals'],
                'industry_tag': '直接受益',
                'quant_tag': f"技术评分{s['score']:.0f}分" if s['score'] >= 60 else "⚠️ 技术面偏弱"
            })

    # 再从间接受益补足到3只
    for s in scored:
        if s['code'] not in direct and len(recommendations) < 3:
            if s['code'] not in [r['code'] for r in recommendations]:
                priority = 'B' if s['score'] >= 60 else 'C'
                recommendations.append({
                    'code': s['code'],
                    'priority': priority,
                    'score': s['score'],
                    'signals': s['signals'],
                    'industry_tag': '间接受益',
                    'quant_tag': f"技术评分{s['score']:.0f}分" if s['score'] >= 60 else "⚠️ 技术面偏弱"
                })

    return recommendations[:3]


def get_stock_name(code: str) -> str:
    """获取股票名称（手动映射，待扩充）"""
    name_map = {
        '688256': '寒武纪', '688041': '海光信息', '688082': '盛美上海',
        '002371': '北方华创', '688012': '中微公司', '688120': '华海清科',
        '600588': '用友网络', '688165': '埃夫特', '601727': '上海电气',
        '688568': '中科星图', '600118': '中国卫星', '002475': '立讯精密',
        '300750': '宁德时代', '002594': '比亚迪', '688190': '云路先进材料',
        '603556': '海兴电力', '688677': '青岛海泰新光', '301268': '铭利达',
        '000818': '航锦科技', '688116': '天奈科技', '300763': '锦浪科技',
        '002415': '海康威视', '688072': '拓荆科技', '688037': '芯源微',
        '603690': '至纯科技', '600641': '万业企业', '688630': '云路股份',
    }
    return name_map.get(code, code)


def format_final_report(recommendations: list, catalyst: str,
                       industry_result: dict, scored_count: int) -> str:
    """格式化最终推荐报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    priority_emoji = {'A': '🥇', 'B': '🥈', 'C': '🥉'}

    lines = [
        f"# 📌 Investment Commander 每日推荐",
        f"",
        f"**时间**：{now}",
        f"**催化剂**：{catalyst}",
        f"**产业池**：{len(industry_result['pool']['direct'])} 直接 + {len(industry_result['pool']['indirect'])} 间接",
        f"**技术面打分**：{scored_count} 只有效数据",
        f"",
        f"---",
        f"",
        f"## 今日推荐（{len(recommendations)}只）",
        f"",
    ]

    for i, r in enumerate(recommendations, 1):
        name = get_stock_name(r['code'])
        emoji = priority_emoji.get(r['priority'], '📌')
        signals_str = '; '.join(r['signals']) if r['signals'] else '无'
        lines.extend([
            f"### {emoji} {i}. {name}（{r['code']}）",
            f"",
            f"- **推荐依据**：{r['industry_tag']} + 技术评分 {r['score']:.0f}分",
            f"- **产业面**：{r['industry_tag']}",
            f"- **技术面**：{r['quant_tag']}",
            f"- **技术信号**：{signals_str}",
            f"",
        ])

    lines.extend([
        f"---",
        f"",
        f"## 产业逻辑",
        f"",
    ])
    for logic in industry_result['logic_chain']:
        lines.append(f"- {logic}")

    lines.extend([
        f"",
        f"---",
        f"",
        f"⚠️ **免责声明**",
        f"量化择时仅供参考（权重30%），最终决策以产业逻辑为主（权重70%）。",
        f"本推荐不构成投资建议，投资有风险，决策需谨慎。",
    ])

    return '\n'.join(lines)


def run(catalyst: str):
    """主入口"""
    print(f"🚀 Investment Commander v2 启动")
    print(f"催化剂：{catalyst}")
    print()

    # 1. 产业分析师
    print("1️⃣ 产业分析师：识别受益标的池...")
    industry_result = get_industry_pool(catalyst)

    if not industry_result['catalysts']:
        print(f"⚠️ 未识别到催化剂：{industry_result.get('message', '')}")
        return

    # 产业池：直接受益 + 间接受益
    industry_codes = (
        industry_result['pool']['direct'] +
        industry_result['pool']['indirect']
    )
    print(f"   产业池：{len(industry_codes)} 只（直接 {len(industry_result['pool']['direct'])} + 间接 {len(industry_result['pool']['indirect'])}）")

    if not industry_codes:
        print("⚠️ 产业池为空，请检查 CATALYST_KNOWLEDGE")
        return

    # 2. 技术面打分（只对产业池扫描）
    print(f"2️⃣ 量化分析师：对产业池做技术面打分...")
    scored = score_industry_pool(industry_codes)
    print(f"   技术面打分完成：{len(scored)} 只有效数据")

    if not scored:
        print("⚠️ 技术面打分全失败（可能是数据源问题）")
        return

    # 3. Commander 决策
    print(f"3️⃣ Commander：整合决策...")
    recommendations = select_final_3_from_scored(scored, industry_result)

    # 4. 生成报告
    report = format_final_report(
        recommendations, catalyst, industry_result, len(scored)
    )

    print(f"\n{'='*60}")
    print(report)

    # 保存报告
    output_dir = Path(__file__).parent / 'output' / 'recommendations'
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime('%Y-%m-%d')
    report_path = output_dir / f'{date_str}-推荐.md'
    report_path.write_text(report, encoding='utf-8')
    print(f"\n✅ 报告已保存：{report_path}")


def run_auto():
    """自动模式：早上8:50无需手动输入催化剂"""
    from us_market_signal import get_morning_context

    ctx = get_morning_context()

    # 如果YANG大涨，直接输出风险预警，不做推荐
    if ctx['risk_warning']:
        print("⚠️ 今日风险预警")
        print(ctx['yang_signal']['advice'])
        print("建议今日轻仓观望，不作推荐")
        return

    # 用美股热门题材作为今日催化剂
    auto_catalyst = ' '.join(ctx['auto_catalyst'])
    if not auto_catalyst:
        auto_catalyst = "芯片 算力"  # 默认催化剂

    print(f"今日自动催化剂（来自美股）：{auto_catalyst}")
    run(auto_catalyst)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalyst', type=str, default=None)
    parser.add_argument('--auto', action='store_true', help='自动模式（读取美股信号）')
    args = parser.parse_args()

    if args.auto:
        run_auto()
    else:
        if args.catalyst:
            run(args.catalyst)
        else:
            print("请输入 --catalyst 或 --auto")

