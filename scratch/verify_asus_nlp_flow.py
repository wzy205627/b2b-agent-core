# -*- coding: utf-8 -*-
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from sales_nlp_pipeline import nlp_pipeline
from agent_tools import query_product_database

def test_asus_flow():
    raw_input = "帮我下 50 台 华硕游戏笔记本，申请打 8.8 折，并送 2 年延保和 50 个拯救者 K7 客制化机械键盘"
    print("=" * 80)
    print("🚀 验证提单自然语言预处理与标准结构化表单组装")
    print("=" * 80)
    print(f"原始提单输入: '{raw_input}'\n")

    form = nlp_pipeline.extract_structured_form(raw_input)
    print("【标准结构化提单表单】:")
    print(json.dumps(form, ensure_ascii=False, indent=2))

    print("\n" + "=" * 80)
    print("🚀 验证纯净主商品关键词检索与 Cross-Encoder 重排")
    print("=" * 80)
    clean_query = form["clean_query"]
    qty = form["main_product"]["quantity"]
    unit = form["main_product"]["unit"]
    
    tool_out_str = query_product_database.invoke({
        "query": clean_query,
        "requested_quantity": qty,
        "requested_unit": unit
    })
    
    tool_res = json.loads(tool_out_str)
    print(f"检索 Query: '{clean_query}' | 申请量: {qty}{unit}")
    candidates = tool_res.get("candidates", [])
    for idx, c in enumerate(candidates):
        score = c.get("score") or c.get("rerank_score")
        print(f"  [{idx+1}] 商机编号: {c['opportunity_id']} | 商品: {c['product_name']} | 评分: {score}")

    top_cand = candidates[0]
    assert "华硕" in top_cand["product_name"], f"预期命中华硕，但命中了 {top_cand['product_name']}"
    print(f"\n🎉 完美命中正确商品: [{top_cand['opportunity_id']}] {top_cand['product_name']}")

if __name__ == "__main__":
    test_asus_flow()
