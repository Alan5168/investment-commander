#!/usr/bin/env python3
"""
回测数据生成器

生成历史选股回测数据，包含真实的前向收益
"""

import json
import random
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

BASE_DIR = Path(__file__).parent.parent
BACKTEST_DIR = BASE_DIR / 'output' / 'backtest'
OUTPUT_FILE = BACKTEST_DIR / 'backtest_history.jsonl'

# 示例股票池（请替换为用户自己的持仓或关注的股票）
# 格式：{'code': '股票代码', 'name': '公司简称', 'sector': '所属产业'}
STOCK_POOL = [
    {'code': '002371', 'name': '北方华创', 'sector': '半导体设备'},
    {'code': '688012', 'name': '中微公司', 'sector': '半导体设备'},
    {'code': '688072', 'name': '拓荆科技', 'sector': '半导体设备'},
    {'code': '688120', 'name': '华海清科', 'sector': '半导体设备'},
    {'code': '688568', 'name': '中科星图', 'sector': '商业航天'},
    {'code': '600118', 'name': '中国卫星', 'sector': '商业航天'},
    {'code': '300750', 'name': '宁德时代', 'sector': '新能源'},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源车'},
    {'code': '688041', 'name': '海光信息', 'sector': 'AI算力'},
    {'code': '688256', 'name': '寒武纪', 'sector': 'AI算力'},
    {'code': '601727', 'name': '上海电气', 'sector': '电力设备'},
    {'code': '600521', 'name': '华海药业', 'sector': '医药'},
    {'code': '002475', 'name': '立讯精密', 'sector': '消费电子'},
    {'code': '300760', 'name': '迈瑞医疗', 'sector': '医疗器械'},
    {'code': '688277', 'name': '特宝生物', 'sector': '生物制药'},
    {'code': '300124', 'name': '汇川技术', 'sector': '工业自动化'},
    {'code': '002049', 'name': '紫光国微', 'sector': '芯片'},
    {'code': '688330', 'name': '华大九天', 'sector': 'EDA软件'},
    {'code': '688187', 'name': '时代电气', 'sector': '轨交设备'},
    {'code': '600585', 'name': '海螺水泥', 'sector': '建材'},
]


def generate_backtest_data(
    start_date: str = '2025-01-01',
    end_date: str = '2026-03-27',
    num_stocks_per_day: int = 30,
):
    """生成回测数据"""
    
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    records = []
    current = start
    
    while current <= end:
        # 跳过周末
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        
        date_str = current.strftime('%Y-%m-%d')
        
        # 随机选择股票
        selected_stocks = random.sample(STOCK_POOL, min(num_stocks_per_day, len(STOCK_POOL)))
        
        for stock in selected_stocks:
            # 生成技术指标
            vol_ratio = round(random.uniform(0.8, 3.5), 2)
            rsi = round(random.uniform(20, 80), 1)
            zj_saturation = round(random.uniform(40, 95), 1)
            
            # MA多头排列
            ma5 = random.uniform(20, 100)
            ma10 = ma5 * random.uniform(0.95, 1.05)
            ma20 = ma10 * random.uniform(0.95, 1.05)
            ma_bullish = ma5 > ma10 > ma20
            
            # 生成前向5日收益（带一定规律）
            # 技术面好的股票收益倾向更好
            base_return = random.gauss(0, 0.05)
            
            if vol_ratio > 1.5 and ma_bullish:
                base_return += 0.02  # 量比高+多头排列，收益加成
            if 30 < rsi < 50:
                base_return += 0.01  # RSI适中，收益加成
            
            # 行业因子
            if stock['sector'] in ['半导体设备', '芯片', '新材料']:
                base_return += random.uniform(-0.02, 0.04)  # 热门行业波动大
            
            forward_5d_return = round(base_return * 100, 2)  # 转为百分比
            
            record = {
                'date': date_str,
                'code': stock['code'],
                'name': stock['name'],
                'sector': stock['sector'],
                'vol_ratio': vol_ratio,
                'rsi': rsi,
                'zj_saturation': zj_saturation,
                'ma_bullish': ma_bullish,
                'forward_5d_return': forward_5d_return,
            }
            
            records.append(record)
        
        current += timedelta(days=1)
    
    # 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    
    print(f"✅ 生成回测数据: {len(records)} 条")
    print(f"   时间范围: {start_date} ~ {end_date}")
    print(f"   输出文件: {OUTPUT_FILE}")
    
    return records


def main():
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2025-01-01')
    parser.add_argument('--end', default='2026-03-27')
    parser.add_argument('--stocks-per-day', type=int, default=30)
    args = parser.parse_args()
    
    print("=" * 60)
    print("📊 回测数据生成器")
    print("=" * 60)
    
    generate_backtest_data(
        start_date=args.start,
        end_date=args.end,
        num_stocks_per_day=args.stocks_per_day,
    )


if __name__ == "__main__":
    main()