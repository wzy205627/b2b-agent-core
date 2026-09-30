import re
from unittest.mock import MagicMock

def sync_dynamic_inventory(task_data: dict, conn) -> dict:
    """
    根据数据库 products 表实时库存，动态刷新待办任务快照中的可用库存、缺口及风控状态。
    """
    if not task_data:
        return task_data
    
    updated = dict(task_data)
    opp_id = updated.get("opp_id") or updated.get("opportunity_id")
    if not opp_id:
        return updated
        
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock, unit, product_name FROM products WHERE opp_id = %s;", (opp_id,))
            row = cur.fetchone()
            if row:
                real_stock = int(row[0])
                unit = updated.get("unit") or row[1] or "台"
                order_qty = int(updated.get("quantity") or 1)
                
                updated["current_stock"] = real_stock
                if order_qty > real_stock:
                    updated["stock_status"] = "SHORTAGE"
                    shortage = order_qty - real_stock
                    updated["shortage_qty"] = shortage
                    
                    reasons = list(updated.get("risk_reasons") or [])
                    reasons = [r for r in reasons if "库存" not in r]
                    reasons.insert(0, f"现货库存告急 (申请{order_qty}{unit}，现存仅{real_stock}{unit}，缺口{shortage}{unit})")
                    updated["risk_reasons"] = reasons
                else:
                    updated["stock_status"] = "SUFFICIENT"
                    updated["shortage_qty"] = 0
                    reasons = list(updated.get("risk_reasons") or [])
                    updated["risk_reasons"] = [r for r in reasons if "库存" not in r]
    except Exception as e:
        print(f"[sync_dynamic_inventory] 动态查验库存异常: {e}")
        
    return updated

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
                    
        print(f"输入: \"{text[:40]}...\" -> 解析出 折扣:{disc}, 延保:{warranty}年, 数量:{qty}")
        if expected.get("disc") is not None:
            assert abs(disc - expected["disc"]) < 0.001
        if expected.get("warranty") is not None:
            assert warranty == expected["warranty"]
        if expected.get("qty") is not None:
            assert qty == expected["qty"]
            
    print("✅ 全部主管指示解析用例通过！")

def test_mock_db_sync():
    print("\n--- [测试 2] 模拟前序订单放行扣减库存后，后续挂起任务动态更新测试 ---")
    
    mock_task = {
        "opp_id": "OPP-8849",
        "product_name": "英伟达 RTX 5090",
        "quantity": 50,
        "unit": "盒",
        "current_stock": 60,
        "stock_status": "SUFFICIENT",
        "shortage_qty": 0,
        "risk_reasons": ["偏高风险 (VP特批)", "低毛利特批"]
    }
    
    # 模拟 1: 物理库存 60
    conn60 = MagicMock()
    cur60 = MagicMock()
    cur60.fetchone.return_value = (60, "盒", "英伟达 RTX 5090")
    conn60.cursor.return_value.__enter__.return_value = cur60
    
    res1 = sync_dynamic_inventory(mock_task, conn60)
    print("前序未放行前:")
    print(f"  可用库存: {res1['current_stock']}盒, 状态: {res1['stock_status']}, 缺口: {res1['shortage_qty']}")
    assert res1['current_stock'] == 60
    assert res1['stock_status'] == "SUFFICIENT"
    assert res1['shortage_qty'] == 0
    
    # 模拟 2: 前序 #A0008 放行扣减 50 台，数据库实际物理库存更新为 10 台
    conn10 = MagicMock()
    cur10 = MagicMock()
    cur10.fetchone.return_value = (10, "盒", "英伟达 RTX 5090")
    conn10.cursor.return_value.__enter__.return_value = cur10
    
    res2 = sync_dynamic_inventory(mock_task, conn10)
    print("前序 #A0008 放行扣减 50 台后，后续 #A0009 动态拉取:")
    print(f"  可用库存: {res2['current_stock']}盒, 状态: {res2['stock_status']}, 缺口: {res2['shortage_qty']}")
    print(f"  动态风控告警标签: {res2['risk_reasons']}")
    
    assert res2['current_stock'] == 10
    assert res2['stock_status'] == "SHORTAGE"
    assert res2['shortage_qty'] == 40
    assert any("现货库存告急" in r and "缺口40盒" in r for r in res2['risk_reasons'])
    
    print("✅ 物理库存动态联动与风控告警生成测试完全通过！")

if __name__ == "__main__":
    test_instruction_extraction()
    test_mock_db_sync()
