#!/usr/bin/env python3
"""
量化参数自主优化器

优化目标：选股准确率（5日内涨幅≥3%的比例）
目标：准确率 55% 以上
"""

import sys
import json
import random
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

# 路径
SHARED_DIR = Path('/Users/alanli/.openclaw/workspace/shared')
OUTPUT_DIR = Path(__file__).parent.parent / 'output' / 'optimization'
LOG_PATH = Path(__file__).parent.parent / '.learnings' / 'optimizer_log.md'

sys.path.insert(0, str(SHARED_DIR))


class ParameterOptimizer:
    """参数优化器"""
    
    def __init__(self):
        # 参数范围
        self.param_ranges = {
            'volume_ratio_min': (1.0, 2.5),
            'rsi_low': (25, 45),
            'zj_saturation_max': (70, 95),
            'accuracy_threshold': (2.0, 5.0),
        }
        
        # 当前最优参数
        self.best_params = {
            'volume_ratio_min': 1.2,
            'rsi_low': 35,
            'zj_saturation_max': 85,
            'accuracy_threshold': 3.0,
        }
        
        self.best_score = 0
        self.generation = 0
        self.no_improvement_count = 0
        
        # 加载历史
        self.load_state()
    
    def load_state(self):
        """加载优化状态"""
        state_path = OUTPUT_DIR / 'optimizer_state.json'
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
                self.best_params = state.get('best_params', self.best_params)
                self.best_score = state.get('best_score', 0)
                self.generation = state.get('generation', 0)
                self.no_improvement_count = state.get('no_improvement_count', 0)
                print(f"加载状态: 第{self.generation}代, 最优评分{self.best_score:.2f}")
            except Exception as e:
                print(f"加载状态失败: {e}")
    
    def save_state(self):
        """保存优化状态"""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        state_path = OUTPUT_DIR / 'optimizer_state.json'
        state = {
            'best_params': self.best_params,
            'best_score': self.best_score,
            'generation': self.generation,
            'no_improvement_count': self.no_improvement_count,
            'timestamp': datetime.now().isoformat(),
        }
        state_path.write_text(json.dumps(state, indent=2))
    
    def mutate_params(self, params: dict, mutation_rate: float = 0.2) -> dict:
        """参数变异"""
        new_params = params.copy()
        
        for key, (min_val, max_val) in self.param_ranges.items():
            if random.random() < mutation_rate:
                # 变异幅度：根据无改善代数调整
                if self.no_improvement_count > 10:
                    mutation_strength = 0.3  # 扩大变异
                else:
                    mutation_strength = 0.15
                
                delta = (max_val - min_val) * mutation_strength
                change = random.uniform(-delta, delta)
                new_val = params[key] + change
                new_params[key] = max(min_val, min(max_val, new_val))
        
        return new_params
    
    def evaluate_params(self, params: dict, backtest_data: list) -> dict:
        """
        评估参数组合
        
        Returns:
            accuracy: 准确率
            candidate_count: 平均候选数
            avoid_crash_rate: 避开大跌股比例
            score: 综合评分
        """
        # 加载回测数据
        results_path = Path(backtest_data) if isinstance(backtest_data, str) else None
        
        if results_path and results_path.exists():
            results = []
            with open(results_path, 'r') as f:
                for line in f:
                    results.append(json.loads(line))
        elif isinstance(backtest_data, list):
            results = backtest_data
        else:
            return {'accuracy': 0, 'score': 0}
        
        if not results:
            return {'accuracy': 0, 'score': 0}
        
        # 用参数筛选
        filtered = []
        for r in results:
            # 量比筛选
            if r['vol_ratio'] < params['volume_ratio_min']:
                continue
            
            # RSI 筛选（低位回升）
            # 简化：RSI 在合理区间
            if r['rsi'] < params['rsi_low'] - 10:  # 太低可能有问题
                continue
            
            filtered.append(r)
        
        if not filtered:
            return {'accuracy': 0, 'score': 0, 'candidate_count': 0}
        
        # 计算指标
        # 准确率：涨幅≥accuracy_threshold的比例
        threshold = params['accuracy_threshold']
        accurate = sum(1 for r in filtered if r['change_pct'] >= threshold)
        accuracy = accurate / len(filtered) if filtered else 0
        
        # 候选数量合理性
        avg_candidates = len(filtered) / len(set(r['date'] for r in results))
        if 5 <= avg_candidates <= 20:
            candidate_score = 100
        elif avg_candidates < 5:
            candidate_score = avg_candidates * 20
        else:
            candidate_score = max(0, 100 - (avg_candidates - 20) * 5)
        
        # 避开大跌股比例
        crash_avoided = sum(1 for r in filtered if r['change_pct'] > -5)
        avoid_crash_rate = crash_avoided / len(filtered) if filtered else 0
        
        # 综合评分
        score = accuracy * 60 + (candidate_score / 100) * 20 + avoid_crash_rate * 20
        
        return {
            'accuracy': accuracy,
            'candidate_count': avg_candidates,
            'avoid_crash_rate': avoid_crash_rate,
            'score': score,
            'total_candidates': len(filtered),
        }
    
    def run_generation(self, backtest_data, num_mutations: int = 5):
        """运行一代优化"""
        self.generation += 1
        
        print(f"\n{'='*50}")
        print(f"第 {self.generation} 代优化")
        print(f"{'='*50}")
        
        results = []
        
        for i in range(num_mutations):
            # 变异参数
            new_params = self.mutate_params(self.best_params)
            
            # 评估
            eval_result = self.evaluate_params(new_params, backtest_data)
            
            results.append({
                'params': new_params,
                'evaluation': eval_result,
            })
            
            print(f"  变异{i+1}: 评分={eval_result['score']:.1f}, 准确率={eval_result['accuracy']:.1%}")
            
            # 更新最优
            if eval_result['score'] > self.best_score:
                self.best_score = eval_result['score']
                self.best_params = new_params
                self.no_improvement_count = 0
                print(f"    ✅ 新最优！评分={self.best_score:.1f}")
            else:
                self.no_improvement_count += 1
        
        # 保存状态
        self.save_state()
        
        # 记录日志
        self.log_generation(results)
        
        return results
    
    def log_generation(self, results):
        """记录优化日志"""
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        log_entry = f"""
## 第 {self.generation} 代 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**最优参数**:
- volume_ratio_min: {self.best_params['volume_ratio_min']:.2f}
- rsi_low: {self.best_params['rsi_low']:.1f}
- zj_saturation_max: {self.best_params['zj_saturation_max']:.1f}
- accuracy_threshold: {self.best_params['accuracy_threshold']:.1f}%

**最优评分**: {self.best_score:.2f}
**连续无改善**: {self.no_improvement_count} 代

**本代结果**:
"""
        
        for i, r in enumerate(results, 1):
            eval_r = r['evaluation']
            log_entry += f"- 变异{i}: 评分={eval_r['score']:.1f}, 准确率={eval_r['accuracy']:.1%}, 候选={eval_r['candidate_count']:.1f}只\n"
        
        # 追加到日志文件
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        print(f"\n📝 日志已更新: {LOG_PATH}")


def main():
    print("=" * 60)
    print("🔧 量化参数自主优化器")
    print("=" * 60)
    
    # 回测数据路径
    backtest_path = Path(__file__).parent.parent / 'output' / 'backtest' / 'backtest_20250101_20260327.jsonl'
    
    if not backtest_path.exists():
        print(f"❌ 回测数据不存在: {backtest_path}")
        return
    
    # 创建优化器
    optimizer = ParameterOptimizer()
    
    # 运行5代
    optimizer.run_generation(str(backtest_path), num_mutations=5)
    
    # 检查是否需要通知
    if optimizer.best_score > 65:
        print("\n⚠️ 准确率超过 65%，需要人工验证！")
    
    if optimizer.no_improvement_count > 20:
        print(f"\n⚠️ 连续 {optimizer.no_improvement_count} 代无改善，建议检查参数范围")
    
    print("\n" + "=" * 60)
    print(f"当前最优评分: {optimizer.best_score:.2f}")
    print(f"连续无改善: {optimizer.no_improvement_count} 代")
    print("=" * 60)


if __name__ == "__main__":
    main()