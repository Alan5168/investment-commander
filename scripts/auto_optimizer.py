#!/usr/bin/env python3
"""
量化参数自动优化器 - Cron 调度版本

优化目标：夏普比率 > 0.8
核心定位：筛出20-30只技术面合格的候选池
"""

import sys
import json
import yaml
import random
from pathlib import Path
from datetime import datetime
import numpy as np

# 路径配置
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / 'config'
OUTPUT_DIR = BASE_DIR / 'output' / 'optimization'
BACKTEST_DIR = BASE_DIR / 'output' / 'backtest'
LOG_PATH = BASE_DIR / '.learnings' / 'optimizer_log.md'

# 默认配置
DEFAULT_CONFIG = {
    'market_filter': {
        'crash_threshold_1d': -0.03,
        'crash_threshold_5d': -0.05,
        'min_candidates': 10,
    },
    'candidate_pool': {
        'target_size': 25,
        'min_size': 15,
        'max_size': 30,
    },
    'technical_filters': {
        'volume_ratio_min': 1.2,
        'rsi_low': 35,
        'zj_saturation_max': 85,
    },
    'optimization': {
        'param_ranges': {
            'volume_ratio_min': [1.0, 2.5],
            'rsi_low': [25, 45],
            'zj_saturation_max': [70, 95],
            'accuracy_threshold': [2.0, 5.0],
        },
        'mutation_rate': 0.2,
        'mutation_strength_normal': 0.15,
        'mutation_strength_aggressive': 0.3,
        'early_stop_generations': 20,
    },
    'targets': {
        'hard_constraints': {
            'sharpe_ratio': 0.3,
            'max_drawdown': 0.20,
            'min_active_days': 60,
        }
    }
}


def load_config():
    """加载配置文件"""
    config = DEFAULT_CONFIG.copy()
    
    # 加载 screener_params.yaml
    screener_path = CONFIG_DIR / 'screener_params.yaml'
    if screener_path.exists():
        with open(screener_path, 'r', encoding='utf-8') as f:
            screener_config = yaml.safe_load(f)
            if screener_config:
                config['market_filter'] = screener_config.get('market_filter', config['market_filter'])
                config['candidate_pool'] = screener_config.get('candidate_pool', config['candidate_pool'])
                config['technical_filters'] = screener_config.get('technical_filters', config['technical_filters'])
    
    # 加载 optimizer_targets.yaml
    targets_path = CONFIG_DIR / 'optimizer_targets.yaml'
    if targets_path.exists():
        with open(targets_path, 'r', encoding='utf-8') as f:
            targets_config = yaml.safe_load(f)
            if targets_config:
                config['targets'] = targets_config.get('targets', config['targets'])
                config['optimization']['param_ranges'] = targets_config.get('optimization', {}).get('param_ranges', config['optimization']['param_ranges'])
    
    return config


class Optimizer:
    """参数优化器"""
    
    def __init__(self):
        self.config = load_config()
        self.state_file = OUTPUT_DIR / 'optimizer_state.json'
        self.backtest_file = BACKTEST_DIR / 'backtest_history.jsonl'
        
        # 参数范围
        self.param_ranges = self.config['optimization']['param_ranges']
        
        # 当前最优
        self.best_params = {
            'volume_ratio_min': self.config['technical_filters'].get('volume_ratio_min', 1.2),
            'rsi_low': self.config['technical_filters'].get('rsi_low', 35),
            'zj_saturation_max': self.config['technical_filters'].get('zj_saturation_max', 85),
            'accuracy_threshold': 3.0,
        }
        self.best_score = 0
        self.generation = 0
        self.no_improvement = 0
        
        # 加载历史状态
        self.load_state()
    
    def load_state(self):
        """加载优化状态"""
        if self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text())
                self.best_params = state.get('best_params', self.best_params)
                self.best_score = state.get('best_score', 0)
                self.generation = state.get('generation', 0)
                self.no_improvement = state.get('no_improvement', 0)
                print(f"📂 加载状态: 第{self.generation}代, 最优评分{self.best_score:.2f}")
            except Exception as e:
                print(f"⚠️ 加载状态失败: {e}")
    
    def save_state(self):
        """保存优化状态"""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            'best_params': self.best_params,
            'best_score': self.best_score,
            'generation': self.generation,
            'no_improvement': self.no_improvement,
            'timestamp': datetime.now().isoformat(),
            'metrics': getattr(self, 'last_metrics', {}),
        }
        self.state_file.write_text(json.dumps(state, indent=2))
    
    def mutate_params(self) -> dict:
        """参数变异"""
        new_params = self.best_params.copy()
        
        # 根据无改善代数调整变异强度
        if self.no_improvement > 10:
            strength = self.config['optimization'].get('mutation_strength_aggressive', 0.3)
        else:
            strength = self.config['optimization'].get('mutation_strength_normal', 0.15)
        
        mutation_rate = self.config['optimization'].get('mutation_rate', 0.2)
        
        for key, (min_val, max_val) in self.param_ranges.items():
            if random.random() < mutation_rate:
                delta = (max_val - min_val) * strength
                change = random.uniform(-delta, delta)
                new_val = self.best_params[key] + change
                new_params[key] = max(min_val, min(max_val, new_val))
        
        return new_params
    
    def calc_metrics(self, returns: list) -> dict:
        """
        计算策略指标（含夏普比率）
        """
        non_zero = [r for r in returns if r != 0]
        
        if not non_zero:
            return {}
        
        wins = [r for r in non_zero if r > 0]
        losses = [r for r in non_zero if r < 0]
        
        # 胜率（涨幅≥3%）
        win_rate = len([r for r in non_zero if r >= 0.03]) / len(non_zero)
        
        # 盈亏比
        plr = (np.mean(wins) / abs(np.mean(losses))) if wins and losses else 0
        
        # 最大回撤
        cum = 1.0
        peak = 1.0
        max_dd = 0.0
        for r in returns:
            cum *= (1 + r)
            peak = max(peak, cum)
            max_dd = max(max_dd, (peak - cum) / peak)
        
        # 夏普比率
        rf_per_period = 0.02 / 52  # 无风险利率2%年化，折算到每周
        excess_returns = [r - rf_per_period for r in non_zero]
        sharpe = (
            np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(52)
            if np.std(excess_returns) > 0 else 0
        )
        
        # 年化收益率
        cum_ret = np.prod([1 + r for r in non_zero])
        annual_return = cum_ret ** (52 / len(non_zero)) - 1 if non_zero else 0
        
        return {
            'win_rate': round(win_rate, 4),
            'max_drawdown': round(max_dd, 4),
            'profit_loss_ratio': round(plr, 2),
            'sharpe_ratio': round(sharpe, 2),
            'annual_return': round(annual_return, 4),
            'active_days': len(non_zero),
            'idle_days': len(returns) - len(non_zero),
        }
    
    def evaluate_params(self, params: dict) -> dict:
        """评估参数组合"""
        # 检查回测数据
        if not self.backtest_file.exists():
            print(f"❌ 回测数据不存在: {self.backtest_file}")
            return {'score': 0, 'metrics': {}}
        
        # 加载回测数据
        records = []
        with open(self.backtest_file, 'r') as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r.get('forward_5d_return') is not None:
                        records.append(r)
                except:
                    continue
        
        if not records:
            print(f"❌ 无有效回测数据")
            return {'score': 0, 'metrics': {}}
        
        # 应用技术面筛选
        filtered = []
        for r in records:
            # 量比筛选
            if r.get('vol_ratio', 1) < params['volume_ratio_min']:
                continue
            # RSI筛选
            if r.get('rsi', 50) < params['rsi_low'] - 10:
                continue
            filtered.append(r)
        
        if len(filtered) < 100:
            return {'score': 0, 'metrics': {'reason': 'filtered_too_few'}}
        
        # 按日期分组
        daily_data = {}
        for r in filtered:
            date = r.get('date')
            if date not in daily_data:
                daily_data[date] = []
            daily_data[date].append(r)
        
        # 方案B过滤 + 计算收益
        dates = sorted(daily_data.keys())
        returns = []
        
        market_filter = self.config['market_filter']
        
        for i, date in enumerate(dates):
            # 大盘过滤
            if i > 0:
                prev_returns = [r.get('forward_5d_return', 0) / 100 for r in daily_data[dates[i-1]]]
                avg_prev = np.mean(prev_returns) if prev_returns else 0
                
                if avg_prev < market_filter['crash_threshold_1d']:
                    returns.append(0.0)
                    continue
            
            # 候选数过滤
            if len(daily_data[date]) < market_filter['min_candidates']:
                returns.append(0.0)
                continue
            
            # 计算当日候选池平均收益
            day_returns = [r.get('forward_5d_return', 0) / 100 for r in daily_data[date]]
            returns.append(np.mean(day_returns))
        
        # 计算指标
        metrics = self.calc_metrics(returns)
        
        if not metrics:
            return {'score': 0, 'metrics': {}}
        
        # 硬限制检查
        hard = self.config['targets']['hard_constraints']
        
        if metrics['sharpe_ratio'] < hard['sharpe_ratio']:
            return {'score': 0, 'metrics': metrics, 'reason': 'sharpe_too_low'}
        if metrics['max_drawdown'] > hard['max_drawdown']:
            return {'score': 0, 'metrics': metrics, 'reason': 'drawdown_too_high'}
        if metrics['active_days'] < hard['min_active_days']:
            return {'score': 0, 'metrics': metrics, 'reason': 'too_few_active_days'}
        
        # 综合评分（以夏普比率为核心）
        score = (
            min(metrics['sharpe_ratio'] / 2, 1) * 40 +  # 夏普比率（核心）
            (1 - metrics['max_drawdown'] / 0.20) * 30 +  # 回撤控制
            min(metrics['profit_loss_ratio'] / 2, 1) * 15 +  # 盈亏比
            metrics['win_rate'] * 15  # 胜率
        )
        
        return {
            'score': round(score, 2),
            'metrics': metrics,
        }
    
    def run_generation(self, num_mutations: int = 5):
        """运行一代优化"""
        self.generation += 1
        
        print(f"\n{'='*50}")
        print(f"第 {self.generation} 代优化")
        print(f"{'='*50}")
        
        results = []
        
        for i in range(num_mutations):
            # 变异参数
            new_params = self.mutate_params()
            
            # 评估
            result = self.evaluate_params(new_params)
            
            print(f"  变异{i+1}: 评分={result['score']:.1f}, 夏普={result['metrics'].get('sharpe_ratio', 0):.2f}")
            
            # 更新最优
            if result['score'] > self.best_score:
                self.best_score = result['score']
                self.best_params = new_params
                self.last_metrics = result['metrics']
                self.no_improvement = 0
                print(f"    ✅ 新最优！评分={self.best_score:.1f}")
            else:
                self.no_improvement += 1
            
            results.append({
                'params': new_params,
                'result': result,
            })
        
        # 保存状态
        self.save_state()
        
        # 记录日志
        self.log_generation(results)
        
        return results
    
    def log_generation(self, results: list):
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
**连续无改善**: {self.no_improvement} 代

**本代结果**:
"""
        
        for i, r in enumerate(results, 1):
            m = r['result'].get('metrics', {})
            log_entry += f"- 变异{i}: 评分={r['result']['score']:.1f}, 夏普={m.get('sharpe_ratio', 0):.2f}, 回撤={m.get('max_drawdown', 0):.1%}\n"
        
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        print(f"📝 日志已更新: {LOG_PATH}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--generations', type=int, default=5)
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔧 量化参数自动优化器")
    print("=" * 60)
    
    optimizer = Optimizer()
    
    # 早停检查
    early_stop = optimizer.config['optimization'].get('early_stop_generations', 20)
    if optimizer.no_improvement >= early_stop:
        print(f"\n⚠️ 连续 {optimizer.no_improvement} 代无改善，建议检查参数范围或回测数据")
    
    # 运行优化
    for _ in range(args.generations):
        optimizer.run_generation(5)
    
    print("\n" + "=" * 60)
    print(f"当前最优评分: {optimizer.best_score:.2f}")
    print(f"连续无改善: {optimizer.no_improvement} 代")
    
    if hasattr(optimizer, 'last_metrics'):
        m = optimizer.last_metrics
        print(f"\n📊 最优策略指标:")
        print(f"  夏普比率: {m.get('sharpe_ratio', 0):.2f}")
        print(f"  年化收益: {m.get('annual_return', 0):.1%}")
        print(f"  最大回撤: {m.get('max_drawdown', 0):.1%}")
        print(f"  胜率: {m.get('win_rate', 0):.1%}")
        print(f"  盈亏比: {m.get('profit_loss_ratio', 0):.2f}")
        print(f"  活跃天数: {m.get('active_days', 0)}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()