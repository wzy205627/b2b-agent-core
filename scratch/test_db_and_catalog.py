import urllib.request
import json
import psycopg

BASE_URL = "http://127.0.0.1:8000"

def restock():
    req = urllib.request.Request(f"{BASE_URL}/api/products/restock", data=b"{}", headers={"Content-Type": "application/json"})
    res = urllib.request.urlopen(req)
    print("Restock result:", json.loads(res.read().decode()), flush=True)

def get_db_stock(opp_id):
    with psycopg.connect("postgresql://postgres:1234@localhost:5432/langgraph_db") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT opp_id, product_name, stock FROM products WHERE opp_id = %s", (opp_id,))
            return cur.fetchone()

def test_flow():
    print("\n=== [1. 重置数据库为初始库存] ===")
    restock()
    gpu_before = get_db_stock("OPP-8849")
    print(f"初始数据库 5090 显卡库存: {gpu_before[2]} 盒")
    assert gpu_before[2] == 60, f"Expected 60, got {gpu_before[2]}"

    print("\n=== [2. 销售首次提单：订购 60 盒 5090 显卡，附赠显卡支架] ===")
    payload1 = {
        "sales_input": "帮我下 60 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9.5 折，送 1 年延保和 60 个显卡支架"
    }
    req1 = urllib.request.Request(f"{BASE_URL}/api/submit", data=json.dumps(payload1).encode(), headers={"Content-Type": "application/json"})
    res1 = urllib.request.urlopen(req1)
    data1 = json.loads(res1.read().decode())
    thread_id = data1["thread_id"]
    print(f"提单成功挂起，Thread ID: {thread_id}, 状态: {data1['status']}")
    interrupt_data = data1.get("interrupt_data", {})
    print(f"提取商品: {interrupt_data.get('product_name')}, 订购量: {interrupt_data.get('quantity')}")
    print(f"提取赠品: {interrupt_data.get('freebie_items')}, 赠品成本: ¥{interrupt_data.get('freebie_total_cost')}")
    print(f"当前库存状态: {interrupt_data.get('stock_status')} (库存: {interrupt_data.get('current_stock')})")
    assert interrupt_data.get('current_stock') == 60

    print("\n=== [3. 主管特批放行入库 (Approve)] ===")
    decision_payload = {
        "action": "approve",
        "approved_discount": 0.95,
        "comment": "同意特批放行，完成提单"
    }
    req_dec = urllib.request.Request(f"{BASE_URL}/api/supervisor/decision/{thread_id}", data=json.dumps(decision_payload).encode(), headers={"Content-Type": "application/json"})
    res_dec = urllib.request.urlopen(req_dec)
    dec_data = json.loads(res_dec.read().decode())
    print("主管审批结果:", dec_data["message"])

    gpu_after = get_db_stock("OPP-8849")
    print(f"\n👉 [核心验证点] 审批完成后 PostgreSQL 数据库中 5090 显卡最新真实库存: {gpu_after[2]} 盒！")
    assert gpu_after[2] == 0, f"Expected 0, got {gpu_after[2]}"

    print("\n=== [4. 销售再次提单：再次下单 60 盒 5090 显卡（检验是否出现死数据）] ===")
    payload2 = {
        "sales_input": "帮我下 60 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9.5 折，送 1 年延保"
    }
    req2 = urllib.request.Request(f"{BASE_URL}/api/submit", data=json.dumps(payload2).encode(), headers={"Content-Type": "application/json"})
    res2 = urllib.request.urlopen(req2)
    data2 = json.loads(res2.read().decode())
    int_data2 = data2.get("interrupt_data", {})
    print(f"第二次提单识别库存: {int_data2.get('current_stock')} 盒, 缺口: {int_data2.get('shortage_qty')} 盒, 状态: {int_data2.get('stock_status')}")
    print(f"风控拦截原因: {int_data2.get('risk_reasons')}")
    assert int_data2.get('current_stock') == 0, f"Expected 0 stock, got {int_data2.get('current_stock')}"
    assert int_data2.get('shortage_qty') == 60, f"Expected shortage 60, got {int_data2.get('shortage_qty')}"
    print("✅ 真实库存动态扣减与缺货拦截闭环验证通过！死数据问题已彻底解决！")

    print("\n=== [5. 验证 DIY 硬件（固态硬盘）严格无赠品约束] ===")
    payload_diy = {
        "sales_input": "帮我下 100 片 三星 990 PRO 2TB 固态硬盘，申请打 9.5 折，送 1 年延保"
    }
    req_diy = urllib.request.Request(f"{BASE_URL}/api/submit", data=json.dumps(payload_diy).encode(), headers={"Content-Type": "application/json"})
    res_diy = urllib.request.urlopen(req_diy)
    diy_data = json.loads(res_diy.read().decode()).get("interrupt_data", {})
    print(f"DIY商品: {diy_data.get('product_name')}")
    print(f"赠品清单: {diy_data.get('freebie_items')}, 赠品成本: ¥{diy_data.get('freebie_total_cost')}")
    print(f"延保年数: {diy_data.get('warranty_years')} 年, 延保成本: ¥{diy_data.get('warranty_total_cost')}")
    assert len(diy_data.get('freebie_items', [])) == 0, "DIY hardware should not have gifts!"
    assert diy_data.get('warranty_years') == 1, "Expected 1 year warranty"
    print("✅ DIY 散件固态硬盘严格无赠品且延保正确提取验证通过！")

    print("\n=== [6. 验证蓝牙耳机专属赠品（保护套）] ===")
    payload_earbuds = {
        "sales_input": "帮我下 200 副 苹果 AirPods Pro 2 降噪耳机，申请打 9 折，送 1 年延保和 200 个保护套"
    }
    req_earbuds = urllib.request.Request(f"{BASE_URL}/api/submit", data=json.dumps(payload_earbuds).encode(), headers={"Content-Type": "application/json"})
    res_earbuds = urllib.request.urlopen(req_earbuds)
    eb_data = json.loads(res_earbuds.read().decode()).get("interrupt_data", {})
    print(f"耳机商品: {eb_data.get('product_name')}")
    print(f"赠品清单: {eb_data.get('freebie_items')}, 赠品明细: {eb_data.get('freebie_details')}")
    print(f"赠品折合成本: ¥{eb_data.get('freebie_total_cost')}")
    assert any("保护套" in item for item in eb_data.get('freebie_items', [])), "Expected 保护套 in freebies"
    assert eb_data.get('freebie_total_cost') == 3000.0, f"Expected 200 * 15 = 3000, got {eb_data.get('freebie_total_cost')}"
    print("✅ 耳机与保护套专属赠品及成本核算（¥15/个）验证通过！")

    print("\n🎉 全部业务测试用例圆满通过！")

if __name__ == "__main__":
    test_flow()
