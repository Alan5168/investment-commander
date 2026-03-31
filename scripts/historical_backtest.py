#!/usr/bin/env python3
"""
历史数据回测脚本 v2.0

新增：
- 前向收益计算（选股后5日收益）
- 真实胜率、盈亏比、最大回撤
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from tqdm import tqdm

# 路径设置
SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
sys.path.insert(0, str(SHARED_DIR))

from stock_client import get_daily


def get_trading_days(start_date: str, end_date: str) -> list:
    """获取交易日列表"""
    start = datetime.strptime(start_date, '%Y%m%d')
    end = datetime.strptime(end_date, '%Y%m%d')
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return days


def get_csi1000_codes() -> list:
    """获取中证1000成分股代码"""
    try:
        import akshare as ak
        df = ak.index_stock_cons_weight_csindex(symbol='000852')
        codes = []
        for _, row in df.iterrows():
            code = str(row['成分券代码']).zfill(6)
            name = row['成分券名称']
            if 'ST' not in name and '退' not in name:
                codes.append(code)
        return codes[:100]
    except Exception as e:
        print(f"获取成分股失败: {e}")
        return []


def get_forward_return(df: pd.DataFrame, select_date: str, forward_days: int = 5) -> float:
    """
    计算前向收益
    
    Args:
        df: 日线数据
        select_date: 选股日期
        forward_days: 前向天数
    
    Returns:
        收益率
    """
    select_dt = pd.to_datetime(select_date)
    df_after = df[df['日期'] >= select_dt].copy()
    
    if len(df_after) < forward_days + 1:
        return None
    
    entry = df_after.iloc[0]['收盘']
    exit_ = df_after.iloc[forward_days]['收盘']
    
    return (exit_ - entry) / entry


def _calc_boll_position(df: pd.DataFrame) -> float:
    """Bollinger position: 0=lower, 0.5=mid, 1=upper"""
    if len(df) < 20:
        return 0.5
    mid = df['收盘'].rolling(20).mean().iloc[-1]
    std = df['收盘'].rolling(20).std().iloc[-1]
    upper = mid + 2 * std
    lower = mid - 2 * std
    close = df['收盘'].iloc[-1]
    if upper == lower:
        return 0.5
    return round((close - lower) / (upper - lower), 3)


def screen_stock_on_date(code: str, date: str, cache: dict) -> dict:
    """在特定日期筛选股票，并计算前向收益"""
    
    if code not in cache:
        df = get_daily(code, days=200)  # 多拉数据用于前向收益
        if df is None or len(df) < 60:
            return None
        cache[code] = df
    
    df = cache[code]
    
    # 过滤到指定日期之前的数据
    date_dt = pd.to_datetime(date)
    df_before = df[df['日期'] <= date_dt].copy()
    
    if len(df_before) < 30:
        return None
    
    # 计算指标
    latest = df_before.iloc[-1]
    close = latest['收盘']
    
    ma5 = df_before['收盘'].rolling(5).mean().iloc[-1]
    ma10 = df_before['收盘'].rolling(10).mean().iloc[-1]
    ma20 = df_before['收盘'].rolling(20).mean().iloc[-1]
    
    volume = latest['成交量']
    ma_vol5 = df_before['成交量'].rolling(5).mean().iloc[-1]
    vol_ratio = volume / ma_vol5 if ma_vol5 > 0 else 0
    
    # 当天涨跌幅
    change_pct = latest.get('涨跌幅', 0)
    if pd.isna(change_pct):
        prev_close = df_before.iloc[-2]['收盘'] if len(df_before) > 1 else close
        change_pct = ((close - prev_close) / prev_close * 100) if prev_close > 0 else 0
    
    # RSI
    delta = df_before['收盘'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_val = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    
    # 三档判断
    tier = 0
    tier_name = ""
    reason = ""
    
    if close > ma20 and ma5 > ma10 > ma20 and vol_ratio > 1.2:
        tier = 1
        tier_name = "强势"
        reason = f"MA多头+放量{vol_ratio:.1f}倍"
    elif close > ma20 and vol_ratio > 1.5:
        ma5_prev = df_before['收盘'].rolling(5).mean().iloc[-2] if len(df_before) > 1 else ma5
        ma10_prev = df_before['收盘'].rolling(10).mean().iloc[-2] if len(df_before) > 1 else ma10
        if ma5 > ma10 and ma5_prev <= ma10_prev:
            tier = 2
            tier_name = "弱势修复"
            reason = f"金叉+放量{vol_ratio:.1f}倍"
    elif close > ma20 and 35 <= rsi_val <= 65:
        rsi_prev3 = rsi.iloc[-4] if len(rsi) > 3 else rsi_val
        if rsi_prev3 < 35:
            tier = 3
            tier_name = "观察池"
            reason = f"RSI从{rsi_prev3:.0f}回升至{rsi_val:.0f}"
    
    if tier == 0:
        return None
    
    # 计算前向收益
    forward_return = get_forward_return(df, date, forward_days=5)
    
    # 计算评分
    score = {1: 70, 2: 55, 3: 40}.get(tier, 0)
    if change_pct > 0:
        score = min(100, score + abs(change_pct))
    
    # === New fields ===
    ma20_5d_ago = df_before['收盘'].rolling(20).mean().iloc[-6] if len(df_before) >= 26 else ma20
    ma20_slope = round((ma20 - ma20_5d_ago) / ma20 * 100, 3) if ma20 != 0 else 0
    close_vs_ma20_pct = round((close - ma20) / ma20 * 100, 2) if ma20 != 0 else 0
    ma60_series = df_before['收盘'].rolling(60).mean()
    ma60 = ma60_series.iloc[-1] if len(df_before) >= 60 else ma20
    close_vs_ma60_pct = round((close - ma60) / ma60 * 100, 2) if ma60 != 0 else 0
    vol_3d_increasing = bool(
        len(df_before) >= 3 and
        df_before['成交量'].iloc[-1] > df_before['成交量'].iloc[-2] > df_before['成交量'].iloc[-3]
    )
    ema12 = df_before['收盘'].ewm(span=12).mean()
    ema26 = df_before['收盘'].ewm(span=26).mean()
    macd_line = ema12 - ema26
    macd_above_zero = bool(macd_line.iloc[-1] > 0) if len(df_before) >= 26 else False
    macd_golden_cross = bool(
        len(df_before) >= 27 and macd_line.iloc[-1] > 0 and macd_line.iloc[-2] <= 0
    ) if len(df_before) >= 27 else False
    boll_position = _calc_boll_position(df_before)
    momentum_5d = round((close - df_before['收盘'].iloc[-6]) / df_before['收盘'].iloc[-6] * 100, 2)         if len(df_before) >= 6 else 0
    momentum_20d = round((close - df_before['收盘'].iloc[-21]) / df_before['收盘'].iloc[-21] * 100, 2)         if len(df_before) >= 21 else 0
    is_20d_high = bool(close >= df_before['最高'].tail(20).max()) if len(df_before) >= 20 else False

    return {
        'date': date,
        'code': code,
        'tier': tier,
        'tier_name': tier_name,
        'reason': reason,
        'close': round(close, 2),
        'change_pct': round(change_pct, 2),
        'forward_5d_return': round(forward_return * 100, 2) if forward_return is not None else None,
        'score': round(score, 1),
        'ma5': round(ma5, 2),
        'ma10': round(ma10, 2),
        'ma20': round(ma20, 2),
        'vol_ratio': round(vol_ratio, 2),
        'rsi': round(rsi_val, 1),
        'ma20_slope': ma20_slope,
        'close_vs_ma20_pct': close_vs_ma20_pct,
        'close_vs_ma60_pct': close_vs_ma60_pct,
        'vol_3d_increasing': vol_3d_increasing,
        'macd_above_zero': macd_above_zero,
        'macd_golden_cross': macd_golden_cross,
        'boll_position': boll_position,
        'momentum_5d': momentum_5d,
        'momentum_20d': momentum_20d,
        'is_20d_high': is_20d_high,
    }


def calculate_performance_metrics(results: list) -> dict:
    """计算绩效指标"""
    
    # 过滤有前向收益的记录
    valid_results = [r for r in results if r.get('forward_5d_return') is not None]
    
    if not valid_results:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_return': 0,
            'profit_loss_ratio': 0,
            'max_drawdown': 0,
        }
    
    returns = [r['forward_5d_return'] / 100 for r in valid_results]
    
    # 胜率
    wins = [r for r in returns if r > 0]
    win_rate = len(wins) / len(returns) if returns else 0
    
    # 平均收益
    avg_return = np.mean(returns) if returns else 0
    
    # 盈亏比
    avg_win = np.mean([r for r in returns if r > 0]) if wins else 0
    losses = [r for r in returns if r < 0]
    avg_loss = abs(np.mean(losses)) if losses else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    
    # 最大回撤
    cumulative = np.cumprod([1 + r for r in returns])
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_drawdown = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0
    
    return {
        'total_trades': len(valid_results),
        'win_rate': win_rate,
        'avg_return': avg_return,
        'profit_loss_ratio': profit_loss_ratio,
        'max_drawdown': max_drawdown,
        'win_count': len(wins),
        'loss_count': len(losses),
    }


def run_backtest(start_date: str, end_date: str, output: str = None):
    """运行历史回测"""
    
    print("=" * 60)
    print("📊 历史数据回测 v2.0（含前向收益）")
    print("=" * 60)
    
    trading_days = get_trading_days(start_date, end_date)
    print(f"\n交易日: {len(trading_days)} 天")
    
    universe = get_csi1000_codes()
    print(f"股票池: {len(universe)} 只")
    
    cache = {}
    results = []
    
    print(f"\n开始回测...\n")
    
    for date in tqdm(trading_days, desc="回测进度"):
        date_results = []
        
        for code in universe:
            result = screen_stock_on_date(code, date, cache)
            if result:
                date_results.append(result)
        
        date_results.sort(key=lambda x: x['score'], reverse=True)
        for r in date_results[:10]:
            results.append(r)
    
    # 保存结果
    if output is None:
        output_dir = Path(__file__).parent.parent / 'output' / 'backtest'
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f'backtest_{start_date}_{end_date}_v2.jsonl'
    
    with open(output, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    
    # 计算绩效指标
    metrics = calculate_performance_metrics(results)
    
    print(f"\n✅ 回测完成")
    print(f"   总记录: {len(results)} 条")
    print(f"   有效记录（有前向收益）: {metrics['total_trades']} 条")
    print(f"   输出: {output}")
    
    print(f"\n📊 绩效指标:")
    print(f"   胜率: {metrics['win_rate']:.1%} ({metrics['win_count']}胜/{metrics['loss_count']}负)")
    print(f"   平均收益: {metrics['avg_return']:.2%}")
    print(f"   盈亏比: {metrics['profit_loss_ratio']:.2f}")
    print(f"   最大回撤: {metrics['max_drawdown']:.1%}")
    
    # 档位分布
    tier_stats = {}
    for r in results:
        tier = r['tier']
        tier_stats[tier] = tier_stats.get(tier, 0) + 1
    
    print(f"\n档位分布:")
    for tier in sorted(tier_stats.keys()):
        name = {1: '强势', 2: '弱势修复', 3: '观察池'}.get(tier, '未知')
        print(f"   {name}: {tier_stats[tier]} 条")
    
    return results, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='历史数据回测')
    parser.add_argument('--start', required=True, help='开始日期 (YYYYMMDD)')
    parser.add_argument('--end', required=True, help='结束日期 (YYYYMMDD)')
    parser.add_argument('--output', help='输出文件路径')
    
    args = parser.parse_args()
    
    run_backtest(args.start, args.end, args.output)