#!/usr/bin/env python3
"""indicator-report - 每天8:00发送指标探索日报"""
import json
from pathlib import Path
from datetime import datetime, timedelta

SKILL = Path('/Users/alanli/.openclaw/workspace/skills/a-stock-monitor')
best = json.loads((SKILL / 'config/best_indicators.json').read_text())

history = []
hist_file = SKILL / 'config/indicator_history.jsonl'
if hist_file.exists():
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    with open(hist_file) as f:
        for line in f:
            r = json.loads(line)
            if r.get('time', '') > cutoff:
                history.append(r)

improvements = sum(1 for h in history if h.get('improved'))
total_rounds = len(history)

print(f'📊 指标探索日报 {datetime.now().strftime("%m-%d")}')
print(f'最优 score: {best.get("composite_score", 0):.2f}')
print(f'分离度: {best.get("separation", 0):.2f}%')
print(f'Alpha: +{best.get("alpha", 0):.2f}pp')
print(f'高区胜率: {best.get("high_win", 0):.1%} vs 随机: 22.1%')
print(f'最优指标: {list(best.get("indicators", {}).keys())}')
print(f'昨日: {total_rounds}轮探索，{improvements}次改进')
print(f'指标库: 41个')
