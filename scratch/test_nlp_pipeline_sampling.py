# -*- coding: utf-8 -*-
"""
test_nlp_pipeline_sampling.py - 抽样 16 条典型真实销售语料进行清洗、语义还原与多路检索验证
"""

import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sales_nlp_pipeline import nlp_pipeline
from freebie_rules import inspect_proposal_elements
from agent_tools import query_product_database

def run_sampling_inspection():
    print("=" * 80)
    print("🚀 启动 NLP 预处理流水线 16 组真实销售语料全场景抽样质检")
    print("=" * 80)

    test_samples = [
        {
            "id": "S01",
            "desc": "夹带非法赠品（显卡送手机膜）",
            "raw": "帮我下 50 台 AI算力显卡，送 1 年延保和 500个AR高透防爆钢化保护膜",
            "expected_prod": "AI算力显卡",
            "expected_qty": 50,
            "expected_warranty": 1,
            "forbid_words": ["钢化", "保护膜"]
        },
        {
            "id": "S02",
            "desc": "紧挨主商品夹带非法配件（显卡夹带防丢绳）",
            "raw": "帮我下 50 台 AI算力显卡和 50 个防丢绳，并送 2 年延保",
            "expected_prod": "AI算力显卡",
            "expected_qty": 50,
            "expected_warranty": 2,
            "forbid_words": ["防丢绳"]
        },
        {
            "id": "S03",
            "desc": "完整合规大单（紧凑无空格）",
            "raw": "帮我下50台AI算力显卡，申请打8.8折，送1年延保和50个ROG铝合金ARGB发光重型显卡支架",
            "expected_prod": "AI算力显卡",
            "expected_qty": 50,
            "expected_discount": 0.88,
            "expected_warranty": 1,
            "forbid_words": []
        },
        {
            "id": "S04",
            "desc": "全中文口语数字与大小写英文",
            "raw": "五十台ai算力显卡 申请八八折 送两年延保",
            "expected_prod": "ai算力显卡",
            "expected_qty": 50,
            "expected_discount": 0.88,
            "expected_warranty": 2,
            "forbid_words": []
        },
        {
            "id": "S05",
            "desc": "手机多赠品合规场景（带折扣）",
            "raw": "远峰蓝苹果18 100台，打九折，送1年质保，送100个磁吸壳和100个钢化膜",
            "expected_prod": "远峰蓝苹果18",
            "expected_qty": 100,
            "expected_discount": 0.9,
            "expected_warranty": 1,
            "forbid_words": []
        },
        {
            "id": "S06",
            "desc": "手机夹带非法赠品+缺延保",
            "raw": "帮我定100部苹果18，外加50个防丢绳，申请95折",
            "expected_prod": "苹果18",
            "expected_qty": 100,
            "expected_discount": 0.95,
            "has_warranty": False,
            "forbid_words": ["防丢绳"]
        },
        {
            "id": "S07",
            "desc": "DIY散件（无赠品品类）乱要赠品",
            "raw": "20盒990 PRO固态硬盘，打八五折，送两年延保和20个耳机套",
            "expected_prod": "990 PRO固态硬盘",
            "expected_qty": 20,
            "expected_discount": 0.85,
            "expected_warranty": 2,
            "forbid_words": ["耳机套"]
        },
        {
            "id": "S08",
            "desc": "散件口语化语气词（'急用'）",
            "raw": "帮我拿30块希捷银河16T机械硬盘，急用，送2年延保",
            "expected_prod": "希捷银河16T机械硬盘",
            "expected_qty": 30,
            "expected_warranty": 2,
            "forbid_words": ["急用"]
        },
        {
            "id": "S09",
            "desc": "网页/Markdown 特殊符号噪声清洗",
            "raw": "【紧急采购】### 50台 AI算力显卡 ### 打9折，送1年保修！！",
            "expected_prod": "AI算力显卡",
            "expected_qty": 50,
            "expected_discount": 0.9,
            "expected_warranty": 1,
            "forbid_words": ["#", "【", "】", "紧急采购"]
        },
        {
            "id": "S10",
            "desc": "严重倒装句（延保在前，商品在后）",
            "raw": "送1年延保，50台AI算力显卡，申请8.8折，送50个支架",
            "expected_prod": "AI算力显卡",
            "expected_qty": 50,
            "expected_discount": 0.88,
            "expected_warranty": 1,
            "forbid_words": []
        },
        {
            "id": "S11",
            "desc": "语序颠倒（数量在后，延保年数在后）",
            "raw": "我要买显卡50台，打八八折，送延保1年",
            "expected_prod": "显卡",
            "expected_qty": 50,
            "expected_discount": 0.88,
            "expected_warranty": 1,
            "forbid_words": []
        },
        {
            "id": "S12",
            "desc": "标准企业 IT 网络品类",
            "raw": "帮我下 10 台 企业级交换机，送1年延保",
            "expected_prod": "企业级交换机",
            "expected_qty": 10,
            "expected_warranty": 1,
            "forbid_words": []
        },
        {
            "id": "S13",
            "desc": "大量多余空格与客套话",
            "raw": "帮我们公司采购 50 台 AI 算力显卡 ， 谢谢 ！",
            "expected_prod": "AI算力显卡",
            "expected_qty": 50,
            "forbid_words": ["谢谢"]
        },
        {
            "id": "S14",
            "desc": "纯配件低值耗材",
            "raw": "下单200张电竞鼠标垫，打七折",
            "expected_prod": "电竞鼠标垫",
            "expected_qty": 200,
            "expected_discount": 0.7,
            "forbid_words": []
        },
        {
            "id": "S15",
            "desc": "手机别名与赠品别名测试",
            "raw": "100台mate70手机 申请9折 送碎屏险和手机壳",
            "expected_prod": "mate70",
            "expected_qty": 100,
            "expected_discount": 0.9,
            "forbid_words": []
        },
        {
            "id": "S16",
            "desc": "无数量的咨询性口语（非标准提单）",
            "raw": "请问AI算力显卡还有现货吗？",
            "expected_prod": "AI算力显卡",
            "forbid_words": ["请问"]
        }
    ]

    passed_cnt = 0
    total_cnt = len(test_samples)

    for item in test_samples:
        sid = item["id"]
        raw = item["raw"]
        print(f"\n[{sid}] 样本测试: {item['desc']}")
        print(f"  • 原始输入: \"{raw}\"")

        # 1. 预处理流水线
        res = nlp_pipeline.parse_and_restore(raw)
        prod = res["product_term"]
        qty = res["quantity"]
        cleaned = res["cleaned_text"]
        clean_base = res["clean_base_text"]
        
        print(f"  • ① re清洗后: \"{cleaned}\"")
        print(f"  • ⑤ 提取主商品: '{prod}' | 数量: {qty}{res['unit']} | 折扣: {res['discount']} | 延保: {res['warranty_years']}年")
        print(f"  • ⑥ 语义还原基干: \"{clean_base}\"")

        # 检查禁止出现的噪声词
        noise_detected = False
        for bad in item["forbid_words"]:
            if bad in clean_base:
                print(f"  ❌ 语义还原基干中残留噪声词: '{bad}'")
                noise_detected = True

        # 检查品类质检与弹窗
        inspect_res = inspect_proposal_elements(raw)
        print(f"  • 品类识别: [{inspect_res['category_name']}] | 赠品类型: {inspect_res['freebie_type']} | 弹窗提醒: {inspect_res['needs_modal']} (原因: {inspect_res['reasons']})")

        if not noise_detected:
            passed_cnt += 1
            print("  ✅ 质检通过")
        else:
            print("  ❌ 质检失败")

    print("\n" + "=" * 80)
    print(f"🎯 抽样质检汇总: 总样本 {total_cnt} 组，通过 {passed_cnt} 组，准确率: {passed_cnt/total_cnt*100:.1f}%")
    print("=" * 80)

if __name__ == "__main__":
    run_sampling_inspection()
