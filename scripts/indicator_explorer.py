#!/usr/bin/env python3
"""
indicator_explorer v2.4 - 遗传算法版本
优化目标：composite_score = separation*0.6 + alpha*0.4
约束：高区必须跑赢随机基准 22.1%
互斥约束：同组指标不能同时出现
"""

import json, random, numpy as np
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor')
BACKTEST_FILE = SKILL_DIR / 'output/backtest/backtest_20250101_20260327_v3.jsonl'
BEST_FILE = SKILL_DIR / 'config/best_indicators.json'
HISTORY_FILE = SKILL_DIR / 'config/indicator_history.jsonl'

RANDOM_BASELINE = 0.221

# 互斥组：同组内指标不能同时出现在一个组合里
MUTEX_GROUPS = [
    ['rsi_oversold', 'rsi_above_60', 'rsi_healthy', 'rsi_below_50', 'rsi_50_60_zone'],
    ['close_gt_ma10', 'close_lt_ma10'],
    ['close_gt_ma20', 'close_lt_ma20'],
    ['ma5_gt_ma10', 'ma20_gt_ma5'],  # 多头排列 vs 空头排列
    ['tier1_signal', 'tier0_weak'],
    ['vol_ratio_2x', 'vol_shrink'],
    ['big_up', 'big_down'],
    ['price_up', 'price_down'],
    ['close_gt_ma20', 'close_lt_ma20', 'close_above_ma20_pct'],
    ['price_up_vol_up', 'price_down_vol_shrink'],
    ['score_above_70', 'score_below_50'],
]

INDICATOR_LIBRARY = {
    # === 均线交叉 ===
    'ma5_gt_ma10':       {'desc': 'MA5>MA10（金叉）',                   'weight_range': [5, 30]},
    'ma10_gt_ma20':      {'desc': 'MA10>MA20',                          'weight_range': [5, 30]},
    'ma20_gt_ma5':       {'desc': 'MA20>MA5（空头排列减分）',             'weight_range': [-25, -5]},
    # === 价格与均线 ===
    'close_gt_ma5':      {'desc': '收盘>MA5',                            'weight_range': [3, 20]},
    'close_gt_ma10':     {'desc': '收盘>MA10',                          'weight_range': [3, 20]},
    'close_gt_ma20':     {'desc': '收盘>MA20',                          'weight_range': [3, 20]},
    'close_lt_ma10':     {'desc': '收盘<MA10（减分）',                  'weight_range': [-25, -5]},
    'close_lt_ma20':     {'desc': '收盘<MA20',                          'weight_range': [-20, -5]},
    'close_above_ma20_pct': {'desc': '收盘>MA20 3%以上（强势）',        'weight_range': [3, 20]},
    # === 量比 ===
    'vol_ratio_2x':      {'desc': '量比>2倍（温和放量）',                'weight_range': [5, 30]},
    'vol_ratio_1_5x':    {'desc': '量比1.5-2倍',                      'weight_range': [3, 18]},
    'vol_shrink':          {'desc': '量比<0.5（缩量）',                   'weight_range': [-18, -3]},
    # === RSI ===
    'rsi_healthy':       {'desc': 'RSI 45-60（健康区）',                'weight_range': [3, 18]},
    'rsi_oversold':       {'desc': 'RSI<40（超卖反弹）',                'weight_range': [5, 25]},
    'rsi_overbought':     {'desc': 'RSI>70（超买减分）',                'weight_range': [-20, -5]},
    'rsi_above_50':      {'desc': 'RSI>50（偏强）',                    'weight_range': [3, 15]},
    'rsi_below_50':       {'desc': 'RSI<50（偏弱）',                    'weight_range': [-15, -3]},
    'rsi_50_60_zone':    {'desc': 'RSI在50-60动量区间',                'weight_range': [3, 15]},
    'rsi_above_60':      {'desc': 'RSI>60（偏强）',                    'weight_range': [3, 15]},
    # === 涨跌 ===
    'big_up':              {'desc': '当日涨幅>3%',                        'weight_range': [3, 18]},
    'big_down':            {'desc': '当日跌幅>3%',                        'weight_range': [-18, -3]},
    'price_up':            {'desc': '当日上涨',                            'weight_range': [2, 12]},
    'price_down':          {'desc': '当日下跌',                            'weight_range': [-12, -2]},
    'negative_change':     {'desc': '当日下跌（负向）',                    'weight_range': [-15, -3]},
    # === Tier ===
    'tier1_signal':        {'desc': 'tier=1（强势信号）',                'weight_range': [10, 45]},
    'tier0_weak':         {'desc': 'tier=0（弱势）',                   'weight_range': [-25, -5]},
    # === 量价配合 ===
    'price_up_vol_up':     {'desc': '价涨量增（涨幅>0且量比>1.2）',      'weight_range': [5, 25]},
    'price_down_vol_shrink': {'desc': '价跌量缩（跌幅>0且量比<0.8）',    'weight_range': [3, 20]},
    # === 综合质量分 ===
    'score_above_70':     {'desc': '原始score>70（强势）',              'weight_range': [5, 25]},
    'score_above_60':     {'desc': '原始score>60（偏强）',              'weight_range': [3, 18]},
    # === v3 新增指标 ===
    'macd_golden_cross':  {'desc': 'MACD金叉',                    'weight_range': [10, 40]},
    'macd_above_zero':   {'desc': 'MACD零轴上方',                'weight_range': [5, 25]},
    'boll_lower_support': {'desc': '布林带下轨支撑（位置<0.2）',     'weight_range': [8, 30]},
    'boll_breakout':     {'desc': '布林带上轨突破（位置>0.8）',    'weight_range': [10, 35]},
    'momentum_5d_positive': {'desc': '5日动量为正',              'weight_range': [8, 25]},
    'momentum_20d_positive': {'desc': '20日动量为正',             'weight_range': [6, 20]},
    'is_20d_high':       {'desc': '创20日新高',                  'weight_range': [10, 35]},
    'ma20_slope_up':     {'desc': 'MA20斜率向上',                 'weight_range': [8, 30]},
    'close_vs_ma20_deep': {'desc': '收盘在MA20上方5%以上',       'weight_range': [8, 30]},
    'vol_3d_increasing': {'desc': '成交量连续3日递增',             'weight_range': [8, 30]},
    'score_below_50':     {'desc': '原始score<50（弱势）',              'weight_range': [-20, -5]},
}


def is_valid_genome(genome: dict) -> bool:
    """检查指标组合是否有逻辑矛盾"""
    keys = set(genome.keys())
    for group in MUTEX_GROUPS:
        matched = [k for k in group if k in keys]
        if len(matched) > 1:
            return False
    return True


def make_genome() -> dict:
    """生成一个无矛盾的随机指标组合（最多试20次）"""
    for _ in range(20):
        n = random.randint(4, 7)
        keys = random.sample(list(INDICATOR_LIBRARY.keys()), n)
        g = {k: random.uniform(*INDICATOR_LIBRARY[k]['weight_range']) for k in keys}
        if is_valid_genome(g):
            return g
    # 保底
    return {'ma5_gt_ma10': 20.0, 'vol_ratio_1_5x': 12.0, 'rsi_healthy': 10.0}


def _mutate_step(genome: dict, strength: float = 0.2) -> dict:
    """单次变异操作"""
    new = dict(genome)

    if random.random() < 0.3:
        if random.random() < 0.5 and len(new) > 2:
            del new[random.choice(list(new.keys()))]
        else:
            candidates = [k for k in INDICATOR_LIBRARY if k not in new]
            if candidates:
                k = random.choice(candidates)
                new[k] = random.uniform(*INDICATOR_LIBRARY[k]['weight_range'])

    for k in list(new.keys()):
        if random.random() < 0.5:
            mn, mx = INDICATOR_LIBRARY[k]['weight_range']
            delta = (mx - mn) * strength
            new[k] = max(mn, min(mx, new[k] + random.uniform(-delta, delta)))

    return new


def mutate(genome: dict, strength: float = 0.2) -> dict:
    """对已有组合进行变异（保证不产生矛盾）"""
    for _ in range(20):
        new = _mutate_step(genome, strength)
        if is_valid_genome(new):
            return new
    return genome  # 变异失败返回原始


def load_records():
    records = []
    with open(BACKTEST_FILE) as f:
        for line in f:
            r = json.loads(line)
            if r.get('forward_5d_return') is not None:
                records.append(r)
    return records


def score_record(r: dict, indicators: dict) -> float:
    score = 50

    ma5        = r.get('ma5',  0)
    ma10       = r.get('ma10', 0)
    ma20       = r.get('ma20', 0)
    close      = r.get('close', 0)
    vol_ratio  = r.get('vol_ratio', 1.0)
    rsi        = r.get('rsi', 50)
    tier       = r.get('tier', 0)
    change_pct = r.get('change_pct', 0)
    sc         = r.get('score', 50)

    for ind, weight in indicators.items():
        if ind == 'ma5_gt_ma10' and ma5 > ma10:
            score += weight
        elif ind == 'ma10_gt_ma20' and ma10 > ma20:
            score += weight
        elif ind == 'ma20_gt_ma5' and ma20 > ma5:
            score += weight
        elif ind == 'close_gt_ma5' and close > ma5:
            score += weight
        elif ind == 'close_gt_ma10' and close > ma10:
            score += weight
        elif ind == 'close_gt_ma20' and close > ma20:
            score += weight
        elif ind == 'close_above_ma20_pct' and close > ma20 * 1.03:
            score += weight
        elif ind == 'close_lt_ma10' and close < ma10:
            score += weight
        elif ind == 'close_lt_ma20' and close < ma20:
            score += weight
        elif ind == 'vol_ratio_2x' and vol_ratio > 2.0:
            score += weight
        elif ind == 'vol_ratio_1_5x' and 1.5 <= vol_ratio <= 2.0:
            score += weight
        elif ind == 'vol_shrink' and vol_ratio < 0.5:
            score += weight
        elif ind == 'rsi_healthy' and 45 <= rsi <= 60:
            score += weight
        elif ind == 'rsi_oversold' and rsi < 40:
            score += weight
        elif ind == 'rsi_overbought' and rsi > 70:
            score += weight
        elif ind == 'rsi_above_50' and rsi > 50:
            score += weight
        elif ind == 'rsi_below_50' and rsi < 50:
            score += weight
        elif ind == 'rsi_50_60_zone' and 50 <= rsi <= 60:
            score += weight
        elif ind == 'rsi_above_60' and rsi > 60:
            score += weight
        elif ind == 'big_up' and change_pct > 3:
            score += weight
        elif ind == 'big_down' and change_pct < -3:
            score += weight
        elif ind == 'price_up' and change_pct > 0:
            score += weight
        elif ind == 'price_down' and change_pct < 0:
            score += weight
        elif ind == 'negative_change' and change_pct < 0:
            score += weight
        elif ind == 'tier1_signal' and tier == 1:
            score += weight
        elif ind == 'tier0_weak' and tier == 0:
            score += weight
        elif ind == 'price_up_vol_up' and change_pct > 0 and vol_ratio > 1.2:
            score += weight
        elif ind == 'price_down_vol_shrink' and change_pct < 0 and vol_ratio < 0.8:
            score += weight
        elif ind == 'score_above_70' and sc > 70:
            score += weight
        elif ind == 'score_above_60' and sc > 60:
            score += weight
        elif ind == 'score_below_50' and sc < 50:
            score += weight

        # === v3 新增指标 ===
        elif ind == 'macd_golden_cross' and r.get('macd_golden_cross'):
            score += weight
        elif ind == 'macd_above_zero' and r.get('macd_above_zero'):
            score += weight
        elif ind == 'boll_lower_support' and r.get('boll_position', 0.5) < 0.2:
            score += weight
        elif ind == 'boll_breakout' and r.get('boll_position', 0.5) > 0.8:
            score += weight
        elif ind == 'momentum_5d_positive' and r.get('momentum_5d', 0) > 0:
            score += weight
        elif ind == 'momentum_20d_positive' and r.get('momentum_20d', 0) > 0:
            score += weight
        elif ind == 'is_20d_high' and r.get('is_20d_high'):
            score += weight
        elif ind == 'ma20_slope_up' and r.get('ma20_slope', 0) > 0.1:
            score += weight
        elif ind == 'close_vs_ma20_deep' and r.get('close_vs_ma20_pct', 0) > 5:
            score += weight
        elif ind == 'vol_3d_increasing' and r.get('vol_3d_increasing'):
            score += weight
    return max(0, min(100, score))


def evaluate(indicators: dict, records: list, q25: float, q75: float) -> dict:
    pred_high, true_high = [], []
    pred_low,  true_low  = [], []

    for r in records:
        fwd = r.get('forward_5d_return')
        if fwd is None:
            continue
        s = score_record(r, indicators)

        if s >= 55:
            pred_high.append(fwd)
            if fwd >= q75:
                true_high.append(fwd)
        elif s <= 45:
            pred_low.append(fwd)
            if fwd <= q25:
                true_low.append(fwd)

    if len(pred_high) < 20 or len(pred_low) < 20:
        return {
            'valid': False,
            'composite_score': -99,
            'reason': f'高区{len(pred_high)}/低区{len(pred_low)}（需各>=20）'
        }

    high_hit = len(true_high) / len(pred_high)
    low_hit  = len(true_low)  / len(pred_low)
    separation = (high_hit - low_hit) * 100
    alpha = (high_hit - RANDOM_BASELINE) * 100

    if high_hit < RANDOM_BASELINE:
        return {
            'valid': False,
            'composite_score': -99,
            'reason': f'高区{high_hit:.1%}未跑赢随机{RANDOM_BASELINE:.1%}'
        }

    composite_score = separation * 0.6 + alpha * 0.4

    return {
        'valid': True,
        'composite_score': round(composite_score, 2),
        'separation': round(separation, 2),
        'alpha': round(alpha, 2),
        'high_hit': round(high_hit, 3),
        'low_hit':  round(low_hit,  3),
        'pred_high_n': len(pred_high),
        'pred_low_n':  len(pred_low),
    }


def run():
    import time
    t0 = time.time()

    records = load_records()
    print(f"加载 {len(records)} 条记录（纯本地）")

    fwds = sorted([r['forward_5d_return'] for r in records])
    q25  = np.percentile(fwds, 25)
    q75  = np.percentile(fwds, 75)
    print(f"Forward Q25={q25:.2f} Q75={q75:.2f}")
    print(f"随机基准: {RANDOM_BASELINE:.1%}（高区必须跑赢）")
    print(f"指标库: {len(INDICATOR_LIBRARY)} 个 | 互斥组: {len(MUTEX_GROUPS)} 组")

    best = {'composite_score': 0, 'indicators': {}}
    if BEST_FILE.exists():
        best = json.loads(BEST_FILE.read_text())

    print(f"\n当前最优 composite_score: {best.get('composite_score', 0):.2f}")
    print(f"当前最优指标: {list(best.get('indicators', {}).keys())}")

    # 生成候选
    candidates = []
    if best.get('indicators') and is_valid_genome(best['indicators']):
        for _ in range(10):
            candidates.append(('mutate', mutate(best['indicators'])))
    for _ in range(5):
        candidates.append(('random', make_genome()))

    print(f"\n评估 {len(candidates)} 个候选（互斥约束已启用）...\n")

    results = []
    for label, genome in candidates:
        result = evaluate(genome, records, q25, q75)
        if result['valid']:
            results.append((result['composite_score'], label, genome, result))

    if not results:
        print("本轮无有效组合")
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, 'a') as f:
            f.write(json.dumps({
                'time': datetime.now().isoformat(),
                'best_composite': 0, 'alpha': 0,
                'global_best': best.get('composite_score', 0),
                'improved': False, 'top_indicators': [], 'n_valid': 0
            }, ensure_ascii=False) + '\n')
    else:
        results.sort(key=lambda x: -x[0])
        best_score, label, best_genome, best_result = results[0]

        improved = best_score > best.get('composite_score', 0)

        if improved:
            print(f"🏆 指标进化 #{best.get('generation', 0) + 1}")
            print(f"  composite_score: {best_score:.2f} (旧: {best.get('composite_score', 0):.2f})")
            print(f"  分离度: {best_result['separation']:.2f}%  Alpha: {best_result['alpha']:+.2f}pp")
            print(f"  高区命中: {best_result['high_hit']:.1%}  低区命中: {best_result['low_hit']:.1%}")
            print(f"  指标: {list(best_genome.keys())}")

            best = {
                'composite_score': best_result['composite_score'],
                'separation': best_result['separation'],
                'alpha': best_result['alpha'],
                'indicators': best_genome,
                'high_hit': best_result['high_hit'],
                'low_hit':  best_result['low_hit'],
                'pred_high_n': best_result['pred_high_n'],
                'pred_low_n':  best_result['pred_low_n'],
                'random_baseline': RANDOM_BASELINE,
                'updated_at': datetime.now().isoformat(),
                'generation': best.get('generation', 0) + 1,
            }
            BEST_FILE.write_text(json.dumps(best, indent=2, ensure_ascii=False))
            print(f"  ✅ 已保存")
        else:
            print(f"  本轮最优 {best_score:.2f}，未超越当前最优 {best.get('composite_score', 0):.2f}")

        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, 'a') as f:
            f.write(json.dumps({
                'time': datetime.now().isoformat(),
                'best_composite': best_result['composite_score'],
                'alpha': best_result['alpha'],
                'global_best': best.get('composite_score', 0),
                'improved': improved,
                'top_indicators': list(best_genome.keys()),
                'n_valid': len(results)
            }, ensure_ascii=False) + '\n')

    elapsed = time.time() - t0
    print(f"[{datetime.now().strftime('%H:%M')}] 完成，耗时 {elapsed:.1f}秒")


if __name__ == "__main__":
    run()
