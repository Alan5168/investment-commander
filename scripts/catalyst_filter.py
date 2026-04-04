#!/usr/bin/env python3
"""
题材交集过滤器

把候选池和当前题材做交集
技术面通过 → 进入候选池（20-30只）
题材支撑 + 技术面 → 真正值得买入的标的
"""

import json
from pathlib import Path
from typing import List, Dict

# 行业-题材映射
INDUSTRY_CATALYST_MAP = {
    '半导体设备': ['芯片', '半导体', '国产替代', '设备'],
    '芯片': ['芯片', '半导体', 'AI芯片', '国产替代'],
    'EDA软件': ['芯片', '半导体', '国产替代', 'EDA'],
    '新材料': ['新材料', '新能源', '高端制造'],
    '医疗器械': ['医疗', '医药', '健康'],
    '汽车零部件': ['汽车', '新能源车', '智能驾驶'],
    '消费电子': ['消费电子', '苹果链', 'AI手机'],
    '电力设备': ['电力', '新能源', '储能'],
    '化工': ['化工', '新材料', '周期'],
    '软件': ['软件', 'AI', '信创'],
}

# 股票题材映射（可手动补充）
STOCK_CATALYST_MAP = {
    # === 示例持仓占位（用户请自行配置）===
    # 'XXXXXX': ['产业1', '产业2'],
    # === 技术面关注股 ===
    '002371': ['半导体设备', '刻蚀', '国产替代'],
    '688012': ['半导体设备', '刻蚀', '国产替代'],
    '688072': ['半导体设备', '薄膜', '国产替代'],
    '688120': ['半导体设备', 'CMP', '国产替代'],
    '688082': ['半导体设备', '清洗', '国产替代'],
    '300750': ['新能源', '锂电池', '储能'],
    '002594': ['新能源车', '电池', '电动车'],
    '688568': ['商业航天', '卫星遥感'],
    '600118': ['商业航天', '卫星应用'],
}


def get_stock_industry_context(code: str) -> str:
    """
    动态获取股票产业背景
    来源优先级：
    1. STOCK_CATALYST_MAP（手动维护，最准）
    2. INDUSTRY_CATALYST_MAP（行业级映射）
    3. "待补充"（兜底）
    """
    # 去除后缀
    clean = code.split('.')[0]

    # 来源1：STOCK_CATALYST_MAP
    if clean in STOCK_CATALYST_MAP:
        return '、'.join(STOCK_CATALYST_MAP[clean])

    # 来源2：INDUSTRY_CATALYST_MAP（按行业查）
    for industry, cats in INDUSTRY_CATALYST_MAP.items():
        if clean in cats:
            return industry

    return '待补充'



def get_stock_catalysts(code: str, name: str, sector: str) -> List[str]:
    """获取股票相关题材"""
    catalysts = []
    
    # 从映射表查找
    if code in STOCK_CATALYST_MAP:
        catalysts.extend(STOCK_CATALYST_MAP[code])
    
    # 从行业查找
    if sector in INDUSTRY_CATALYST_MAP:
        catalysts.extend(INDUSTRY_CATALYST_MAP[sector])
    
    # 去重
    return list(set(catalysts))


def match_catalyst(stock_catalysts: List[str], user_catalysts: List[str]) -> List[str]:
    """匹配题材"""
    matched = []
    for uc in user_catalysts:
        for sc in stock_catalysts:
            if uc.lower() in sc.lower() or sc.lower() in uc.lower():
                matched.append(uc)
                break
    return list(set(matched))


def filter_by_catalyst(candidates: List[Dict], catalysts: List[str]) -> Dict:
    """
    把候选池和当前题材做交集
    
    Args:
        candidates: 候选池股票列表，每个元素需包含 code, name, sector
        catalysts: 用户输入的题材关键词列表
    
    Returns:
        matched: 题材+技术双重确认 → 重点关注
        unmatched: 仅技术面 → 参考
    """
    matched = []
    unmatched = []
    
    for c in candidates:
        code = c.get('code', '')
        name = c.get('name', '')
        sector = c.get('sector', '')
        
        # 获取股票题材
        stock_catalysts = get_stock_catalysts(code, name, sector)
        
        # 匹配用户输入的题材
        matched_catalysts = match_catalyst(stock_catalysts, catalysts)
        
        if matched_catalysts:
            c['catalyst_match'] = True
            c['matched_catalysts'] = matched_catalysts
            matched.append(c)
        else:
            c['catalyst_match'] = False
            c['stock_catalysts'] = stock_catalysts
            unmatched.append(c)
    
    return {
        'matched': matched,
        'unmatched': unmatched,
    }


def format_output(candidates: List[Dict], catalysts: List[str]) -> str:
    """格式化输出"""
    result = filter_by_catalyst(candidates, catalysts)
    
    output = f"""📊 技术面候选池 × 题材交集

⚠️ 以下仅为技术面筛选结果
有题材支撑的标的才具备投资价值，请结合产业逻辑判断

🎯 当前关注题材：{', '.join(catalysts)}

---

### 🎯 题材+技术双重确认（{len(result['matched'])}只）
**重点关注，具备投资价值**

"""
    
    if result['matched']:
        for c in result['matched']:
            catalysts_str = ', '.join(c.get('matched_catalysts', []))
            output += f"- {c['code']} {c['name']} [{c.get('sector', '')}] - 题材: {catalysts_str}\n"
    else:
        output += "*无匹配*\n"
    
    output += f"""
---

### 📋 仅技术面合格（{len(result['unmatched'])}只）
**需要题材催化才有意义**

"""
    
    for c in result['unmatched'][:15]:  # 最多显示15只
        stock_catalysts = c.get('stock_catalysts', [])
        output += f"- {c['code']} {c['name']} [{c.get('sector', '')}] - 相关题材: {', '.join(stock_catalysts[:3])}\n"
    
    if len(result['unmatched']) > 15:
        output += f"\n... 还有 {len(result['unmatched']) - 15} 只\n"
    
    output += f"""
---

### 📊 统计
- 题材匹配率: {len(result['matched'])}/{len(candidates)} ({len(result['matched'])/len(candidates)*100:.1f}%)
- 建议: 优先关注「题材+技术双重确认」的标的
"""
    
    return output


def main():
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalysts', type=str, help='题材关键词，逗号分隔')
    parser.add_argument('--candidates', type=str, help='候选池JSON文件')
    args = parser.parse_args()
    
    if not args.catalysts:
        print("请输入题材关键词，例如：--catalysts '芯片,半导体,新能源'")
        return
    
    catalysts = [c.strip() for c in args.catalysts.split(',')]
    
    # 模拟候选池（实际应从选股模块获取）
    candidates = [
        {'code': '002371', 'name': '北方华创', 'sector': '半导体设备'},
        {'code': '688012', 'name': '中微公司', 'sector': '半导体设备'},
        {'code': '688568', 'name': '中科星图', 'sector': '商业航天'},
        {'code': '300750', 'name': '宁德时代', 'sector': '新能源'},
    ]
    
    if args.candidates:
        with open(args.candidates, 'r') as f:
            candidates = json.load(f)
    
    output = format_output(candidates, catalysts)
    print(output)


if __name__ == "__main__":
    main()