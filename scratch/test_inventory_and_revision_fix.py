import re
import requests
import psycopg

BASE_URL = "http://127.0.0.1:8000"
DB_URI = "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable"

def test_instruction_extraction():
    print("\n--- [测试 1] 验证主管整改指示解析逻辑 ---")
    
    test_cases = [
        (
            "变相让利过多导致综合毛利率跌破红线！要求延保最多1年，壳砍半至250个，申请折扣不得低于9折！",
            {"disc": 0.90, "warranty": 1}
        ),
        (
            "🚨 严重击穿 BOM 底线成本！单台倒贴亏损，要求折扣不低于 8.5 折并取消额外赠品延保，重新提单！",
            {"disc": 0.85, "warranty": None}
        ),
        (
            "【主管整改指示】：原提单方案让利过大侵蚀公司利润，经测算请按以下具体指标整改后重新提单：\n1. 【订购数量】：因现存库存不足（现货仅存 10 台，缺口 40 台），建议将订购数量缩减至 10 台（缺口消除）；\n2. 【申请折扣】：调整至不低于 9.2 折；\n3. 【附赠延保】：缩减至最多 1 年；",
            {"disc": 0.92, "warranty": 1, "qty": 10}
        ),
        (
            "建议调整至9.5折，延保缩减至0年",
            {"disc": 0.95, "warranty": 0}
        )
    ]
    
    for text, expected in test_cases:
        # 1. 折扣正则
        disc = None
        for reg in [
            r"(?:不低于|不得低于|调整至|建议|最低|上调至|至少)\s*([0-9.]+)\s*折",
            r"(?:折扣|折扣率).*?([0-9.]+)\s*折",
            r"([0-9.]+)\s*折"
        ]:
            m = re.search(reg, text)
            if m:
                val = float(m.group(1)) / 10.0
                if 0.5 <= val <= 1.0:
                    disc = round(val, 3)
                    break
        
        # 2. 延保正则
        warranty = None
        for reg in [
            r"(?:延保|质保).*?(?:最多|缩减至|调整为|不超过|至多)?\s*([0-9]+)\s*年",
            r"(?:最多|缩减至|不超过|至多)\s*([0-9]+)\s*年"
        ]:
            m = re.search(reg, text)
            if m:
                val = int(m.group(1))
                if 0 <= val <= 5:
                    warranty = val
                    break
                    
        # 3. 数量正则
        qty = None
        for reg in [
            r"(?:缩减至|调整至|订购数量.*?)\s*([0-9]+)\s*(?:台|盒|个|件)",
            r"仅存\s*([0-9]+)\s*(?:台|盒|个|件)"
        ]:
            m = re.search(reg, text)
            if m:
                val = int(m.group(1))
                if val > 0:
                    qty = val
                    break
                    
        print(f"输入文本: \"{text[:45]}...\"")
        print(f"  解析结果 -> 折扣: {disc} (预期: {expected.get('disc')}), 延保: {warranty}年 (预期: {expected.get('warranty')}), 数量: {qty} (预期: {expected.get('qty')})")
        if expected.get("disc") is not None:
            assert abs(disc - expected["disc"]) < 0.001, f"折扣解析错误: 得到 {disc}, 预期 {expected['disc']}"
        if expected.get("warranty") is not None:
            assert warranty == expected["warranty"], f"延保解析错误: 得到 {warranty}, 预期 {expected['warranty']}"
        if expected.get("qty") is not None:
            assert qty == expected["qty"], f"数量解析错误: 得到 {qty}, 预期 {expected['qty']}"
            
    print("✅ 全部主管指示解析用例通过！")

def test_dynamic_inventory_sync():
    print("\n--- [测试 2] 验证待办列表动态库存真实联动 ---")
    
    # 1. 查询数据库当前 RTX 5090 库存
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT opp_id, product_name, stock FROM products WHERE opp_id = 'OPP-8849';")
            row = cur.fetchone()
            assert row, "未能找到 OPP-8849 商品记录！"
            original_stock = int(row[2])
            print(f"📦 数据库初始库存: [{row[0]}] {row[1]} 物理库存 = {original_stock}")

    try:
        # 2. 调用 API 获取待办列表
        res = requests.get(f"{BASE_URL}/api/pending-tasks").json()
        tasks = res.get("tasks", [])
        gpu_tasks = [t for t in tasks if t.get("interrupt_data", {}).get("opp_id") == "OPP-8849"]
        print(f"当前有 {len(gpu_tasks)} 个待审核的显卡提单")
        
        for t in gpu_tasks:
            data = t["interrupt_data"]
            print(f"  提单 #{t.get('order_id')}: 申请数量={data.get('quantity')}, 动态读取库存={data.get('current_stock')}, 状态={data.get('stock_status')}, 缺口={data.get('shortage_qty')}")
            assert data.get("current_stock") == original_stock, f"待办任务库存未与物理库存同步: {data.get('current_stock')} vs {original_stock}"

        # 3. 模拟前序订单放行扣减库存：将数据库库存设为 10 台
        print("\n模拟前序订单放行扣减库存 -> 将数据库物理库存修改为 10 台...")
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE products SET stock = 10 WHERE opp_id = 'OPP-8849';")

        # 4. 再次请求 API，验证后续提单是否即时感知数据库变化
        res2 = requests.get(f"{BASE_URL}/api/pending-tasks").json()
        tasks2 = res2.get("tasks", [])
        gpu_tasks2 = [t for t in tasks2 if t.get("interrupt_data", {}).get("opp_id") == "OPP-8849"]
        
        for t in gpu_tasks2:
            data = t["interrupt_data"]
            qty = data.get("quantity", 1)
            print(f"  [扣减后即时感知] 提单 #{t.get('order_id')}: 申请数量={qty}, 动态读取库存={data.get('current_stock')}, 状态={data.get('stock_status')}, 缺口={data.get('shortage_qty')}")
            assert data.get("current_stock") == 10, f"扣减后动态库存未更新为 10: 得到 {data.get('current_stock')}"
            if qty > 10:
                assert data.get("stock_status") == "SHORTAGE", "库存不足时状态应为 SHORTAGE"
                assert data.get("shortage_qty") == qty - 10, f"缺口计算错误: 得到 {data.get('shortage_qty')}"
                print(f"  ⚠️ 风控告警首项: {data.get('risk_reasons', [''])[0]}")
                assert "库存" in data.get("risk_reasons", [''])[0], "风控首项应包含库存告警"

        print("✅ 物理库存动态扣减与待办列表无缝联动验证完全通过！")

    finally:
        # 5. 恢复数据库库存
        print("\n恢复数据库物理库存至原始值...")
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE products SET stock = %s WHERE opp_id = 'OPP-8849';", (original_stock,))
        print("✅ 数据库库存已安全复原。")

if __name__ == "__main__":
    test_instruction_extraction()
    test_dynamic_inventory_sync()
