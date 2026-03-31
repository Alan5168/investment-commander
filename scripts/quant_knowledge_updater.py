#!/usr/bin/env python3
"""
quant_knowledge_updater.py
每周从 QuantsPlaybook / GitHub 搜索有效A股因子，
评估后自动扩充 INDICATOR_LIBRARY
"""

import json, re
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor')
BACKTEST_FILE = SKILL_DIR / 'output/backtest/backtest_20250101_20260327_v2.jsonl'
INDICATOR_LIB_FILE = SKILL_DIR / 'config/indicator_library.json'
LOG_FILE = SKILL_DIR / 'config/quant_updater_log.md'

# v2.jsonl 可用字段（仅这些可以安全使用）
AVAILABLE_FIELDS = {'close', 'ma5', 'ma10', 'ma20', 'vol_ratio', 'rsi', 'tier', 'change_pct', 'score'}


def search_github_indicators() -> list[dict]:
    """
    模拟从 GitHub QuantsPlaybook 搜索（实际用 Tavily/Exa API）
    这里返回候选指标定义（名称 + 计算规则字符串）
    """
    candidates = []

    # 搜索关键词组合
    queries = [
        "A股 量化因子 技术指标 RSJ RSI 动量 有效性",
        "stock technical indicator alpha factor A-share momentum",
        "a-share quantitative factor volume price relation",
    ]

    # 模拟从 GitHub quantsplaybook 找到的候选指标
    # 格式：{name, desc, formula, field_dependencies, direction}
    raw_candidates = [
        {
            'name': 'rsi_above_60',
            'desc': 'RSI>60 偏强',
            'formula': 'rsi > 60',
            'dependencies': ['rsi'],
            'direction': 'positive',
            'weight_range': [5, 20],
        },
        {
            'name': 'rsi_below_40',
            'desc': 'RSI<40 超卖',
            'formula': 'rsi < 40',
            'dependencies': ['rsi'],
            'direction': 'positive',
            'weight_range': [5, 25],
        },
        {
            'name': 'vol_ratio_above_3',
            'desc': '量比>3倍（主力活跃）',
            'formula': 'vol_ratio > 3.0',
            'dependencies': ['vol_ratio'],
            'direction': 'positive',
            'weight_range': [8, 30],
        },
        {
            'name': 'close_above_ma20_pct',
            'desc': '收盘价在MA20上方3%以上',
            'formula': 'close > ma20 * 1.03',
            'dependencies': ['close', 'ma20'],
            'direction': 'positive',
            'weight_range': [5, 25],
        },
        {
            'name': 'rsi_50_60_zone',
            'desc': 'RSI在50-60动量区间',
            'formula': '50 <= rsi <= 60',
            'dependencies': ['rsi'],
            'direction': 'positive',
            'weight_range': [3, 15],
        },
        {
            'name': 'change_pct_1to3',
            'desc': '涨幅1%-3%（温和上涨）',
            'formula': '0 < change_pct < 3',
            'dependencies': ['change_pct'],
            'direction': 'positive',
            'weight_range': [3, 15],
        },
        {
            'name': 'negative_change',
            'desc': '当日下跌',
            'formula': 'change_pct < 0',
            'dependencies': ['change_pct'],
            'direction': 'negative',
            'weight_range': [-15, -3],
        },
        {
            'name': 'score_high',
            'desc': '原始综合评分高（>65）',
            'formula': 'score > 65',
            'dependencies': ['score'],
            'direction': 'positive',
            'weight_range': [8, 30],
        },
        {
            'name': 'score_low',
            'desc': '原始综合评分低（<45）',
            'formula': 'score < 45',
            'dependencies': ['score'],
            'direction': 'negative',
            'weight_range': [-20, -5],
        },
    ]

    # 过滤：只保留依赖字段在 AVAILABLE_FIELDS 里的
    for c in raw_candidates:
        deps_ok = all(d in AVAILABLE_FIELDS for d in c['dependencies'])
        if deps_ok:
            candidates.append(c)
        else:
            print(f"  ⏭ 跳过 {c['name']}：缺少字段 {c['dependencies'] - AVAILABLE_FIELDS}")

    return candidates


def score_indicator(candidate: dict) -> dict:
    """
    用真实数据评估一个候选指标的有效性
    不需要新的 API 调用，直接用已有 v2.jsonl
    """
    records = []
    with open(BACKTEST_FILE) as f:
        for line in f:
            r = json.loads(line)
            if r.get('forward_5d_return') is not None:
                records.append(r)

    formula = candidate['formula']
    direction = candidate['direction']

    # 用 eval 安全地评估公式（只访问预定义的字段）
    def safe_eval(r):
        local_vars = {
            'close': r.get('close', 0),
            'ma5': r.get('ma5', 0),
            'ma10': r.get('ma10', 0),
            'ma20': r.get('ma20', 0),
            'vol_ratio': r.get('vol_ratio', 1.0),
            'rsi': r.get('rsi', 50),
            'tier': r.get('tier', 0),
            'change_pct': r.get('change_pct', 0),
            'score': r.get('score', 50),
        }
        try:
            return eval(formula, {"__builtins__": {}}, local_vars)
        except:
            return False

    hits = [r for r in records if safe_eval(r)]
    miss = [r for r in records if not safe_eval(r)]

    if len(hits) < 20:
        return {'valid': False, 'reason': f'命中仅{len(hits)}条（需>=20）'}

    hit_rate = sum(1 for r in hits if r['forward_5d_return'] >= 3) / len(hits)
    miss_rate = sum(1 for r in miss if r['forward_5d_return'] >= 3) / len(miss) if miss else 0

    return {
        'valid': True,
        'name': candidate['name'],
        'desc': candidate['desc'],
        'hit_rate': round(hit_rate, 3),
        'miss_rate': round(miss_rate, 3),
        'lift': round(hit_rate - miss_rate, 3),
        'n_hits': len(hits),
        'weight_range': candidate['weight_range'],
        'direction': direction,
    }


def update_indicator_library(new_indicators: list[dict]):
    """将验证通过的指标写入 indicator_library.json"""
    lib_file = Path(INDICATOR_LIB_FILE)
    existing = {}
    if lib_file.exists():
        existing = json.loads(lib_file.read_text())

    for ind in new_indicators:
        existing[ind['name']] = {
            'desc': ind['desc'],
            'weight_range': ind['weight_range'],
            'direction': ind['direction'],
            'hit_rate': ind['hit_rate'],
            'lift': ind['lift'],
            'added_at': datetime.now().isoformat(),
        }

    lib_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"\n✅ 已写入 {len(new_indicators)} 个新指标到 {INDICATOR_LIB_FILE}")


def run():
    print("=" * 50)
    print(f"📖 Quants 知识更新 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # Step 1: 搜索候选指标
    print("\n1. 搜索 GitHub/QuantsPlaybook 候选指标...")
    candidates = search_github_indicators()
    print(f"   找到 {len(candidates)} 个候选（已过滤可用字段）")

    # Step 2: 评估每个候选
    print("\n2. 评估候选指标有效性...")
    approved = []
    for c in candidates:
        result = score_indicator(c)
        if result['valid']:
            print(f"   ✅ {c['name']}: 命中率={result['hit_rate']:.1%} "
                  f"提升={result['lift']:+.1%} n={result['n_hits']}")
            approved.append({**c, **result})
        else:
            print(f"   ⏭  {c['name']}: {result['reason']}")

    if not approved:
        print("\n无通过评估的新指标")
        return

    # Step 3: 只保留 lift > 0 的（真正有效的）
    effective = [a for a in approved if a['lift'] > 0]
    print(f"\n3. 有效指标（lift>0）: {len(effective)}/{len(approved)}")

    if effective:
        update_indicator_library(effective)

        # 写日志
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            for e in effective:
                f.write(f"- {e['name']}: lift={e['lift']:+.1%}, hit_rate={e['hit_rate']:.1%}\n")


if __name__ == "__main__":
    run()
