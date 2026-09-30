import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_order_naming():
    print("=== 开始自动化测试：提单分类编号规范化与精确下单时间戳 ===")
    
    # 1. 显卡类提单首单 (A0001)
    print("\n[Test 1] 提交显卡类提单（首单）...")
    payload1 = {
        "sales_input": "帮我下 10 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9 折，送 1 年延保和 10 个显卡支架"
    }
    r1 = requests.post(f"{BASE_URL}/api/submit", json=payload1).json()
    print("返回结果 1:", r1.get("thread_id"), r1.get("order_id"), r1.get("created_at"), r1.get("status"))
    assert r1.get("order_id") == "A0001" or r1.get("thread_id") == "A0001", f"预期 A0001，实际 {r1.get('order_id')}"
    assert ":" in (r1.get("created_at") or ""), "created_at 必须包含时分秒"

    # 2. 显卡类提单次单 (A0002)
    print("\n[Test 2] 提交显卡类提单（次单）...")
    payload2 = {
        "sales_input": "帮我下 5 盒 英伟达 RTX 5080 16GB 光追电竞显卡，申请打 9.2 折"
    }
    r2 = requests.post(f"{BASE_URL}/api/submit", json=payload2).json()
    print("返回结果 2:", r2.get("thread_id"), r2.get("order_id"), r2.get("created_at"))
    assert r2.get("order_id") == "A0002" or r2.get("thread_id") == "A0002", f"预期 A0002，实际 {r2.get('order_id')}"

    # 3. 手机类提单 (B0001)
    print("\n[Test 3] 提交手机类提单...")
    payload3 = {
        "sales_input": "帮我下 20 台 苹果18 标准版 256G 远峰蓝，申请打 8.8 折，送 1 年延保和 20 个保护壳"
    }
    r3 = requests.post(f"{BASE_URL}/api/submit", json=payload3).json()
    print("返回结果 3:", r3.get("thread_id"), r3.get("order_id"), r3.get("created_at"))
    assert r3.get("order_id") == "B0001" or r3.get("thread_id") == "B0001", f"预期 B0001，实际 {r3.get('order_id')}"

    # 4. 耳机类提单 (C0001)
    print("\n[Test 4] 提交耳机类提单...")
    payload4 = {
        "sales_input": "帮我下 30 副 苹果 AirPods Pro 2 主动降噪蓝牙无线耳机，申请打 9 折，送 30 个保护套"
    }
    r4 = requests.post(f"{BASE_URL}/api/submit", json=payload4).json()
    print("返回结果 4:", r4.get("thread_id"), r4.get("order_id"), r4.get("created_at"))
    assert r4.get("order_id") == "C0001" or r4.get("thread_id") == "C0001", f"预期 C0001，实际 {r4.get('order_id')}"

    # 5. 硬盘类提单 (E0001)
    print("\n[Test 5] 提交固态硬盘类提单...")
    payload5 = {
        "sales_input": "帮我下 50 片 三星 990 PRO 2TB 固态硬盘，申请打 9 折，送 1 年延保"
    }
    r5 = requests.post(f"{BASE_URL}/api/submit", json=payload5).json()
    print("返回结果 5:", r5.get("thread_id"), r5.get("order_id"), r5.get("created_at"))
    assert r5.get("order_id") == "E0001" or r5.get("thread_id") == "E0001", f"预期 E0001，实际 {r5.get('order_id')}"

    # 6. 主管审批工作台待办任务队列拉取测试
    print("\n[Test 6] 检查 /api/pending-tasks 待办任务列表...")
    pending_res = requests.get(f"{BASE_URL}/api/pending-tasks").json()
    print(f"当前共有 {pending_res.get('total')} 个待主管审批任务")
    task_a1 = next((t for t in pending_res["tasks"] if t.get("order_id") == "A0001" or t.get("thread_id") == "A0001"), None)
    assert task_a1 is not None, "必须在待办列表中找到 A0001 提单"
    print("A0001 待办任务数据:", {
        "thread_id": task_a1.get("thread_id"),
        "order_id": task_a1.get("order_id"),
        "created_at": task_a1.get("created_at"),
        "task_status": task_a1.get("task_status")
    })
    assert ":" in task_a1.get("created_at"), "A0001 必须具有精确到秒的 created_at"

    # 7. 主管驳回 A0001 并流转至销售端
    print("\n[Test 7] 主管驳回 A0001，要求销售修改...")
    reject_res = requests.post(
        f"{BASE_URL}/api/supervisor/decision/{task_a1['thread_id']}",
        json={
            "action": "reject",
            "instructions": "【主管整改指示】：请将折扣调整为 9.5 折，延保缩减至 1 年，重新提交！",
            "target_discount": 0.95,
            "target_warranty_years": 1
        }
    ).json()
    print("驳回结果:", reject_res.get("status"), reject_res.get("message"))

    # 8. 销售端检查【待我修改】队列中的提单编号与下单时间
    print("\n[Test 8] 检查销售端 /api/sales/returned-tasks...")
    returned_res = requests.get(f"{BASE_URL}/api/sales/returned-tasks").json()
    returned_a1 = next((t for t in returned_res["tasks"] if t.get("order_id") == "A0001" or t.get("thread_id") == "A0001"), None)
    assert returned_a1 is not None, "销售端必须包含 A0001 待修改任务"
    print("销售端 A0001 待修改信息:", {
        "order_id": returned_a1.get("order_id"),
        "created_at": returned_a1.get("created_at"),
        "product_name": returned_a1.get("product_name"),
        "revision_count": returned_a1.get("revision_count")
    })
    assert returned_a1.get("order_id") == "A0001", "销售端提单编号必须为 A0001"
    assert ":" in returned_a1.get("created_at"), "销售端必须有精确下单时间"

    print("\n🎉 全部 8 项提单规则化编号与精确下单时间测试全部通过！")

if __name__ == "__main__":
    test_order_naming()
