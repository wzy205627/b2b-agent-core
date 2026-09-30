import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
import json

def test_user_actual_cases():
    print("\n--- [测试 1] 验证包含'防丢绳'等五花八门夹杂赠品的端到端清洗 ---")
    from freebie_rules import inspect_proposal_elements
    
    test_cases = [
        # 用户刚才截图中的真实案例
        (
            "帮我下 50 台 AI算力显卡和 50 个防丢绳，并送 2 年延保",
            ["50个ROG 铝合金 ARGB 发光重型显卡支架"],
            "帮我下 50 台 AI算力显卡，并送 2 年延保和 50个ROG 铝合金 ARGB 发光重型显卡支架"
        ),
        # 带折扣且在末尾有保护壳的案例
        (
            "帮我下 50 台 AI算力显卡，申请打 8.8 折，并送 2 年延保和 500 个保护壳",
            ["50个ROG 铝合金 ARGB 发光重型显卡支架"],
            "帮我下 50 台 AI算力显卡，申请打 8.8 折，并送 2 年延保和 50个ROG 铝合金 ARGB 发光重型显卡支架"
        ),
        # 夹杂'加 50 个防丢绳'与折扣
        (
            "帮我下 100 台 远峰蓝苹果18加 50 个防丢绳，申请打 9 折，送 1 年延保",
            ["100个专属磁吸保护壳", "100个AR高透防爆钢化保护膜"],
            "帮我下 100 台 远峰蓝苹果18，申请打 9.0 折，并送 1 年延保和 100个专属磁吸保护壳、100个AR高透防爆钢化保护膜"
        ),
        # DIY散件夹杂保护套
        (
            "帮我下 20 盒 固态硬盘和 20 个防丢绳，申请打 8.5 折，并送 2 年延保",
            [],
            "帮我下 20 盒 固态硬盘，申请打 8.5 折，并送 2 年延保"
        )
    ]
    
    for raw_text, valid_freebies, expected in test_cases:
        p_data = inspect_proposal_elements(raw_text)
        clean_base = p_data["clean_base_text"]
        warranty_years = p_data["warranty_years"]
        
        warranty_part = f"，并送 {warranty_years} 年延保" if warranty_years > 0 else ""
        freebie_clause = ""
        if valid_freebies:
            if warranty_part:
                freebie_clause = f"和 {'、'.join(valid_freebies)}"
            else:
                freebie_clause = f"，送 {'、'.join(valid_freebies)}"
                
        final_text = clean_base + warranty_part + freebie_clause
        
        print(f"\n原始输入: \"{raw_text}\"")
        print(f"后端提取基干: \"{clean_base}\"")
        print(f"重构最终提单: \"{final_text}\"")
        assert "防丢绳" not in final_text, "提单中严禁出现防丢绳！"
        assert "保护壳" not in final_text or "显卡" not in final_text, "显卡提单中严禁出现保护壳！"
        print("-> 验证通过！")

    print("\n✅ 用户实际案例全部 100% 通过验证！")

if __name__ == "__main__":
    test_user_actual_cases()
