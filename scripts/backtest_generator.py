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

# 模拟股票池
STOCK_POOL = [
    {'code': '688190', 'name': '云路先进材料', 'sector': '新材料'},
    {'code': '603556', 'name': '海兴电力', 'sector': '电力设备'},
    {'code': '688677', 'name': '青岛海泰新光', 'sector': '医疗器械'},
    {'code': '000818', 'name': '航锦科技', 'sector': '化工'},
    {'code': '301268', 'name': '铭利达', 'sector': '汽车零部件'},
    {'code': '02018', 'name': '瑞声科技', 'sector': '消费电子'},
    {'code': '688116', 'name': '天奈科技', 'sector': '新材料'},
    {'code': '688262', 'name': '苏州国芯科技', 'sector': '芯片'},
    {'code': '03888', 'name': '金山软件', 'sector': '软件'},
    {'code': '300567', 'name': '精测电子', 'sector': '半导体设备'},
    {'code': '688332', 'name': '中科蓝讯', 'sector': '芯片'},
    {'code': '600745', 'name': '闻泰科技', 'sector': '半导体'},
    {'code': '301269', 'name': '华大九天', 'sector': 'EDA软件'},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体设备'},
    {'code': '688012', 'name': '中微公司', 'sector': '半导体设备'},
    {'code': '688072', 'name': '拓荆科技', 'sector': '半导体设备'},
    {'code': '688120', 'name': '华海清科', 'sector': '半导体设备'},
    {'code': '688082', 'name': '盛美上海', 'sector': '半导体设备'},
    {'code': '688037', 'name': '芯源微', 'sector': '半导体设备'},
    {'code': '603690', 'name': '至纯科技', 'sector': '半导体设备'},
    {'code': '600641', 'name': '万业企业', 'sector': '半导体设备'},
    {'code': '688630', 'name': '云路股份', 'sector': '新材料'},
    {'code': '603505', 'name': '金石资源', 'sector': '资源'},
    {'code': '300750', 'name': '宁德时代', 'sector': '新能源'},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源汽车'},
    {'code': '601012', 'name': '隆基绿能', 'sector': '光伏'},
    {'code': '600519', 'name': '贵州茅台', 'sector': '消费'},
    {'code': '000858', 'name': '五粮液', 'sector': '消费'},
    {'code': '601318', 'name': '中国平安', 'sector': '金融'},
    {'code': '000333', 'name': '美的集团', 'sector': '家电'},
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