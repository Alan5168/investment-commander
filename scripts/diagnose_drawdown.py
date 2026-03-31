#!/usr/bin/env python3
"""
最大回撤诊断脚本

找出净值曲线崩溃的具体时间段和原因
"""

import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

def diagnose_drawdown():
    """找出回撤严重的时间段"""
    
    # 加载回测数据
    backtest_path = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor/output/backtest/backtest_20250101_20260327_v2.jsonl')
    
    records = []
    with open(backtest_path, 'r') as f:
        for line in f:
            r = json.loads(line)
            if r.get('forward_5d_return') is not None:
                records.append({
                    'date': r.get('date'),
                    'code': r.get('code'),
                    'forward_return': r.get('forward_5d_return') / 100,
                    'tier': r.get('tier'),
                    'tier_name': r.get('tier_name'),
                    'score': r.get('score'),
                })
    
    print("=" * 60)
    print("📊 最大回撤诊断")
    print("=" * 60)
    
    df = pd.DataFrame(records)
    df = df.sort_values('date')
    
    print(f"\n总记录: {len(df)} 条")
    print(f"日期范围: {df['date'].min()} ~ {df['date'].max()}")
    
    # 按日期分组，计算每日平均收益
    daily = df.groupby('date').agg({
        'forward_return': ['mean', 'std', 'count', lambda x: (x > 0).sum() / len(x)]
    }).reset_index()
    
    daily.columns = ['date', 'avg_return', 'std_return', 'count', 'win_rate']
    daily['cumulative'] = (1 + daily['avg_return']).cumprod()
    daily['peak'] = daily['cumulative'].cummax()
    daily['drawdown'] = (daily['peak'] - daily['cumulative']) / daily['peak']
    
    # 找出回撤最严重的时间点
    worst = daily.nlargest(10, 'drawdown')
    
    print("\n【回撤最严重的10个交易日】")
    print("-" * 80)
    for _, row in worst.iterrows():
        print(f"  {row['date']} | 回撤 {row['drawdown']:.1%} | 收益 {row['avg_return']:.1%} | 候选 {int(row['count'])} 只 | 胜率 {row['win_rate']:.0%}")
    
    # 找出连续亏损期
    daily['losing'] = daily['avg_return'] < 0
    
    consecutive_losses = []
    count = 0
    start = None
    total_loss = 0
    
    for _, row in daily.iterrows():
        if row['losing']:
            if count == 0:
                start = row['date']
                total_loss = row['avg_return']
            else:
                total_loss += row['avg_return']
            count += 1
        else:
            if count >= 3:
                consecutive_losses.append({
                    'start': start,
                    'end': row['date'],
                    'days': count,
                    'total_loss': total_loss
                })
            count = 0
            total_loss = 0
    
    print("\n【连续亏损超过3天的时期】")
    print("-" * 80)
    for p in consecutive_losses[:10]:
        print(f"  {p['start']} ~ {p['end']} | 连续 {p['days']} 天 | 累计亏损 {p['total_loss']:.1%}")
    
    # 按档位分析表现
    print("\n【各档位表现】")
    print("-" * 80)
    tier_stats = df.groupby('tier_name').agg({
        'forward_return': ['mean', 'count', lambda x: (x > 0).sum() / len(x)]
    })
    tier_stats.columns = ['平均收益', '次数', '胜率']
    
    for tier_name, row in tier_stats.iterrows():
        print(f"  {tier_name}: 平均收益 {row['平均收益']:.1%} | 次数 {int(row['次数'])} | 胜率 {row['胜率']:.0%}")
    
    # 按评分区间分析
    print("\n【评分区间表现】")
    print("-" * 80)
    df['score_bucket'] = pd.cut(df['score'], bins=[0, 50, 60, 70, 80, 100], labels=['<50', '50-60', '60-70', '70-80', '>80'])
    score_stats = df.groupby('score_bucket').agg({
        'forward_return': ['mean', 'count', lambda x: (x > 0).sum() / len(x)]
    })
    score_stats.columns = ['平均收益', '次数', '胜率']
    
    for bucket, row in score_stats.iterrows():
        print(f"  {bucket}分: 平均收益 {row['平均收益']:.1%} | 次数 {int(row['次数'])} | 胜率 {row['胜率']:.0%}")
    
    # 关键统计
    print("\n【关键统计】")
    print("-" * 80)
    print(f"  平均每日候选: {daily['count'].mean():.1f} 只")
    print(f"  单日最大亏损: {daily['avg_return'].min():.1%}")
    print(f"  单日最大盈利: {daily['avg_return'].max():.1%}")
    print(f"  收益标准差: {daily['avg_return'].std():.1%}")
    print(f"  最终净值: {daily['cumulative'].iloc[-1]:.2f}")
    
    return daily, worst, consecutive_losses


if __name__ == "__main__":
    diagnose_drawdown()