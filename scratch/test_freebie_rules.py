import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from freebie_rules import inspect_proposal_elements

inputs = [
    "帮我下 60 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9.0 折，送 1 年延保",
    "帮我下 60 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9.0 折，送显卡支架",
    "帮我下 60 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9.0 折",
    "帮我下 60 台 苹果18 Pro Max 512G 暗夜紫，申请打 9.0 折，送 1 年延保",
    "帮我下 100 片 三星 990 PRO 2TB 固态硬盘，申请打 9.5 折，送 100 个手机壳",
    "帮我下 100 片 三星 990 PRO 2TB 固态硬盘，申请打 9.5 折，送 1 年延保"
]

for inp in inputs:
    res = inspect_proposal_elements(inp)
    print(f"\n输入: {inp}")
    print(f"  品类: {res['category_name']} (赠品类型: {res['freebie_type']}) | 延保: {res['has_warranty']} ({res['warranty_years']}年)")
    print(f"  赠品提取: {res['extracted_freebies']} | 需弹窗: {res['needs_modal']} (原因: {res['reasons']})")
