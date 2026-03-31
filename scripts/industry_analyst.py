#!/usr/bin/env python3
"""
产业分析师 Agent

输入：用户描述的催化剂（会议/政策/事件）
输出：受益标的池，按受益强度分级
"""

import json
from typing import List, Dict

# 产业链知识库（手动维护，用户可补充）
CATALYST_KNOWLEDGE = {
    "英伟达": {
        "logic": "英伟达业绩/发布会 → 全球AI算力需求确认 → 国内算力产业链受益",
        "direct": ["688256", "688041", "688082"],  # 寒武纪、海光、盛美
        "indirect": ["002371", "688012", "688120"],  # 北方华创、中微、华海清科
        "sentiment": ["600588", "688165"]  # 概念股
    },
    "苹果": {
        "logic": "苹果发布会 → 新品备货 → 果链供应商受益",
        "direct": ["002475", "001219"],  # 立讯精密、富创精密
        "indirect": ["688012", "300433"],
        "sentiment": []
    },
    "商业航天": {
        "logic": "SpaceX/商业航天热度 → 国内商业航天政策加码 → 产业链受益",
        "direct": ["688568", "600118"],  # 中科星图、中国卫星
        "indirect": ["300101", "688325"],
        "sentiment": []
    },
    "算力": {
        "logic": "AI算力需求增长 → 数据中心建设 → 电力/设备/芯片受益",
        "direct": ["688041", "002415", "300763"],
        "indirect": ["601727", "688012"],
        "sentiment": []
    },
    "芯片": {
        "logic": "半导体国产替代持续推进",
        "direct": ["002371", "688012", "688120", "688072"],
        "indirect": ["688256", "688041"],
        "sentiment": []
    },
    "新能源": {
        "logic": "新能源政策支持 → 电动车/储能/光伏受益",
        "direct": ["300750", "002594", "601012"],
        "indirect": ["300274", "688036"],
        "sentiment": []
    },
    "电力设备": {
        "logic": "算力/新能源带动电力需求 → 电力设备受益",
        "direct": ["601727", "603806", "688556"],
        "indirect": ["300724"],
        "sentiment": []
    }
}


def parse_catalysts(user_input: str) -> List[str]:
    """从用户输入中识别催化剂关键词"""
    matched = []
    for keyword in CATALYST_KNOWLEDGE.keys():
        if keyword in user_input:
            matched.append(keyword)
    return matched


def analyze_catalyst(catalysts: List[str]) -> Dict:
    """
    分析催化剂，生成受益标的池
    """
    if not catalysts:
        return {
            "catalysts": [],
            "logic_chain": [],
            "pool": {"direct": [], "indirect": [], "sentiment": []},
            "message": "未识别到具体催化剂，请描述具体事件"
        }

    all_direct = []
    all_indirect = []
    all_sentiment = []
    logic_chains = []

    for cat in catalysts:
        if cat not in CATALYST_KNOWLEDGE:
            continue
        info = CATALYST_KNOWLEDGE[cat]
        logic_chains.append(f"【{cat}】{info['logic']}")
        all_direct.extend(info['direct'])
        all_indirect.extend(info['indirect'])
        all_sentiment.extend(info['sentiment'])

    # 去重（direct 先出来，indirect 排除已在 direct 的，sentiment 排除已在前两层的）
    direct = list(dict.fromkeys(all_direct))
    direct_set = set(direct)
    indirect = [s for s in dict.fromkeys(all_indirect) if s not in direct_set]
    indirect_set = set(indirect)
    sentiment = [s for s in dict.fromkeys(all_sentiment)
                 if s not in direct_set and s not in indirect_set]

    return {
        "catalysts": catalysts,
        "logic_chain": logic_chains,
        "pool": {
            "direct": direct,
            "indirect": indirect,
            "sentiment": sentiment
        },
        "total": len(direct) + len(indirect) + len(sentiment)
    }


def format_industry_report(result: Dict) -> str:
    """格式化产业分析报告"""
    if not result["catalysts"]:
        return f"⚠️ {result['message']}"

    lines = [
        f"🏭 产业分析报告",
        f"",
        f"催化剂：{'、'.join(result['catalysts'])}",
        f"",
    ]

    for logic in result["logic_chain"]:
        lines.append(f"📌 {logic}")

    lines.extend([
        f"",
        f"受益标的池（共{result['total']}只）：",
        f"",
        f"🎯 直接受益（{len(result['pool']['direct'])}只，优先关注）：",
    ])

    for code in result["pool"]["direct"]:
        lines.append(f"  {code}")

    if result["pool"]["indirect"]:
        lines.extend([
            f"",
            f"🔗 间接受益（{len(result['pool']['indirect'])}只）：",
        ])
        for code in result["pool"]["indirect"]:
            lines.append(f"  {code}")

    if result["pool"]["sentiment"]:
        lines.extend([
            f"",
            f"💭 概念受益（{len(result['pool']['sentiment'])}只，谨慎）：",
        ])
        for code in result["pool"]["sentiment"]:
            lines.append(f"  {code}")

    lines.extend([
        f"",
        f"⚠️ 以上为产业逻辑分析，需结合技术面确认后再决策"
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalyst', type=str, required=True,
                        help='催化剂描述，例如："英伟达GTC大会 算力"')
    parser.add_argument('--output', type=str, default=None)
    args = parser.parse_args()

    catalysts = parse_catalysts(args.catalyst)
    result = analyze_catalyst(catalysts)

    report = format_industry_report(result)
    print(report)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
