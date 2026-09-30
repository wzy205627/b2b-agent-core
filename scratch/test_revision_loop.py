import os
import uuid
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

import sys
sys.path.insert(0, ".")
from phase2_full_agent import builder

load_dotenv()
DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable")

def test_full_collaborative_loop():
    print("=" * 80)
    print("🧪 开始验证【销售-主管双向协同驳回修改闭环】")
    print("=" * 80)
    
    thread_id = f"test-collab-{uuid.uuid4().hex[:6]}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 30
    }
    
    with ConnectionPool(conninfo=DB_URI, max_size=5, kwargs={"autocommit": True}) as pool:
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer)
        
        # Step 1: 销售发起初始提单（高隐形让利导致毛利被严重侵蚀）
        sales_msg_1 = "帮我下 500 台远峰蓝苹果18，给客户打 8.8 折，并承诺送 2 年延保和 500 个保护壳"
        print(f"\n[Step 1 销售提交初始申请] 👤 销售: \"{sales_msg_1}\"")
        graph.invoke({"sales_input": sales_msg_1, "retry_count": 0}, config=config)
        
        # 检查是否在主管审批处挂起
        state_1 = graph.get_state(config)
        assert state_1.next and state_1.tasks and state_1.tasks[0].interrupts, "未能在主管审批点挂起！"
        interrupt_1 = state_1.tasks[0].interrupts[0].value
        print(f"\n[Step 2 主管工作台收到待办] ⏸️ 任务已成功在风控审批节点挂起！")
        print(f"  • 商品: {interrupt_1.get('product_name')} (商机: {interrupt_1.get('opp_id')})")
        print(f"  • 订购台数: {interrupt_1.get('quantity')}{interrupt_1.get('unit')}")
        print(f"  • 申请折扣: {interrupt_1.get('requested_discount')}")
        print(f"  • 标面毛利率: {interrupt_1.get('surface_margin')}% -> 真实综合毛利率: {interrupt_1.get('true_margin')}%")
        print(f"  • 拦截原因: {interrupt_1.get('reason')}")
        print(f"  • 商业建议: {interrupt_1.get('recovery_suggestions')}")
        
        # Step 3: 主管驳回并提出明确修改意见
        reject_payload = {
            "action": "reject",
            "instructions": "变相让利过多导致毛利率跌破红线！要求延保最多1年，壳砍半至250个，申请折扣不得低于9折！"
        }
        print(f"\n[Step 3 主管点击驳回] 🔴 主管提出修改要求: \"{reject_payload['instructions']}\"")
        graph.invoke(Command(resume=reject_payload), config=config)
        
        # Step 4: 检查是否流转至销售端修改节点并挂起
        state_2 = graph.get_state(config)
        assert state_2.next and state_2.tasks and state_2.tasks[0].interrupts, "未能在销售修改节点挂起！"
        interrupt_2 = state_2.tasks[0].interrupts[0].value
        print(f"\n[Step 4 销售端待办通知] 📬 销售端收到被驳回任务！")
        print(f"  • 任务状态: {interrupt_2.get('task_status')}")
        print(f"  • 主管修改指示: {interrupt_2.get('supervisor_instructions')}")
        print(f"  • 当前轮次: 第 {interrupt_2.get('revision_count', 0)} 次修改")
        
        # Step 5: 销售根据主管意见调整后重新提交
        sales_msg_2 = "帮我下 500 台远峰蓝苹果18，给客户打 9 折，承诺送 1 年延保和 250 个保护壳"
        print(f"\n[Step 5 销售重新提单] 👤 销售按指示修改后重新提交: \"{sales_msg_2}\"")
        graph.invoke(Command(resume={"revised_input": sales_msg_2}), config=config)
        
        # Step 6: 检查模型是否重新分析，核算新毛利率并再次流转至主管审批
        state_3 = graph.get_state(config)
        assert state_3.next and state_3.tasks and state_3.tasks[0].interrupts, "重新提单后未流转至主管审批！"
        interrupt_3 = state_3.tasks[0].interrupts[0].value
        print(f"\n[Step 6 主管工作台收到二次审批] 📋 主管看到调整后的最新财务核算：")
        print(f"  • 商品: {interrupt_3.get('product_name')}")
        print(f"  • 新申请折扣: {interrupt_3.get('requested_discount')}")
        print(f"  • 新赠品承诺: {interrupt_3.get('freebie_items')}")
        print(f"  • 新延保年数: {interrupt_3.get('warranty_years')} 年")
        print(f"  • 修复后真实综合毛利率: {interrupt_3.get('true_margin')}% (相比之前已显著提升)")
        print(f"  • 修改轮次: 第 {interrupt_3.get('revision_count', 0)} 轮")
        
        # Step 7: 主管核验毛利率达标，点击同意特批放行
        approve_payload = {
            "action": "approve",
            "approved_discount": 0.90,
            "comment": "调整后毛利达标，且大单数量可观，同意特批放行！"
        }
        print(f"\n[Step 7 主管同意放行] 🟢 主管审批通过: \"{approve_payload['comment']}\"")
        graph.invoke(Command(resume=approve_payload), config=config)
        
        # Step 8: 验证最终完成状态
        state_final = graph.get_state(config)
        assert not state_final.next, f"图未结束！当前还有 next: {state_final.next}"
        print(f"\n[Step 8 订单归档入库] 🎉 全流程成功流转完毕！")
        print(f"  • 最终商机: {state_final.values.get('opportunity_id')}")
        print(f"  • 最终生效折扣: {state_final.values.get('final_discount')}")
        print(f"  • 最终状态: {state_final.values.get('task_status')}")
        print(f"  • 累计修改轮次: {state_final.values.get('revision_count')} 轮")
        print(f"  • 最终审批记录: {state_final.values.get('approval_comment')}")
        print("=" * 80)
        print("✅ 双向协同驳回修改闭环全部测试通过！")

if __name__ == "__main__":
    test_full_collaborative_loop()
