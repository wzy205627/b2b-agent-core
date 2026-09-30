import os
import uuid
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

load_dotenv()

from phase2_full_agent import builder

DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable")

def run_test_case(title: str, sales_input: str, should_interrupt: bool = True):
    print("\n" + "="*80)
    print(f"🧪 测试用例: {title}")
    print(f"📝 销售输入: \"{sales_input}\"")
    print("="*80)

    thread_id = f"test-margin-{uuid.uuid4().hex[:6]}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10
    }

    with ConnectionPool(conninfo=DB_URI, max_size=5, kwargs={"autocommit": True}) as pool:
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer)

        graph.invoke(
            {"sales_input": sales_input, "retry_count": 0},
            config=config
        )

        state = graph.get_state(config)
        
        if state.next and state.tasks and state.tasks[0].interrupts:
            data = state.tasks[0].interrupts[0].value
            print(f"\n[测试结果] ⏸️ 任务成功挂起在风控中断点！")
            print(f"  • 标的商品: [{data['opp_id']}] {data['product_name']}")
            print(f"  • 订购数量: {data['quantity']}{data['unit']} (标价: ¥{data['unit_price']:,.2f}, BOM成本: ¥{data['cost_price']:,.2f})")
            print(f"  • 合同实收: ¥{data['final_amount']:,.2f} (申请折扣: {data['requested_discount']*10:.1f}折)")
            print(f"  • 硬件BOM总成本: ¥{data['bom_total_cost']:,.2f}")
            print(f"  • 延保服务成本: ¥{data['warranty_total_cost']:,.2f} (承诺延保: {data['warranty_years']}年)")
            print(f"  • 赠品配件成本: ¥{data['freebie_total_cost']:,.2f} (赠品清单: {data['freebie_items']})")
            print(f"  • 综合履约总成本: ¥{data['combined_total_cost']:,.2f}")
            print(f"  • 真实综合净利润: ¥{data['true_profit']:,.2f}")
            print(f"  • 真实综合毛利率: {data['true_margin']:.2f}% (未扣让利前标面毛利: {data['surface_margin']:.2f}%)")
            print(f"  • 风险级别: {data['margin_risk_level']} | 建议审批层级: 【{data['approval_level']}】")
            print(f"  • 触发的风控红线:")
            for r in data['risk_reasons']:
                print(f"      - {r}")
            if data.get('recovery_suggestions'):
                print(f"  • 商业挽回建议:")
                for s in data['recovery_suggestions']:
                    print(f"      💡 {s}")

            # 模拟主管特批
            print("\n👤 [模拟审批] 执行特批恢复 (Resume)...")
            decision = {
                "approved_discount": 0.88,
                "comment": "同意特批放行，严格监控履约毛利"
            }
            graph.invoke(Command(resume=decision), config=config)
            final_state = graph.get_state(config)
            print(f"✅ 审批后会话完结: next={final_state.next}, 生效折扣={final_state.values.get('final_discount')}")
            return data
        else:
            print(f"\n[测试结果] 🟢 系统自动放行！无需人工干预。")
            values = state.values
            print(f"  • 标的商品: [{values.get('opportunity_id')}] {values.get('product_name')}")
            print(f"  • 订购数量: {values.get('quantity')}{values.get('unit')} (单价: ¥{values.get('unit_price')})")
            print(f"  • 实收金额: ¥{values.get('final_amount'):,.2f} (折扣: {values.get('discount')*10:.1f}折)")
            print(f"  • 真实毛利率: {values.get('true_margin')}% (净利润: ¥{values.get('true_profit'):,.2f})")
            print(f"  • 放行附言: {values.get('approval_comment')}")
            return values

if __name__ == "__main__":
    print("🚀 开始批量验证防资损核心系统（维度1 财务毛利穿透 + 维度4 变相让利防范）...")
    
    # 用例 1: 表面合规但变相让利 (8.8折 + 延保2年 + 送500个壳)
    case1 = run_test_case(
        title="用例 1: 表面 8.8 折合规，但口头赠送 2 年延保和 500 个保护壳导致真实毛利率暴跌",
        sales_input="帮我下 500 台 远峰蓝苹果18，申请打 8.8 折，并送 2 年延保和 500 个保护壳"
    )

    # 用例 2: 严重击穿 BOM 底线成本 (倒贴做慈善)
    case2 = run_test_case(
        title="用例 2: 客户要求打 7 折击穿硬件底线成本价 (单台亏本卖)",
        sales_input="帮我下 100 台 远峰蓝苹果18，客户要求打 7 折，送 1 年延保"
    )

    # 用例 3: 高毛利健康合规订单 (自动秒级放行)
    case3 = run_test_case(
        title="用例 3: 50 台 9.5 折无赠品高毛利订单 (系统秒级自动放行)",
        sales_input="帮我下 50 台 苹果18，打 9.5 折，无赠品"
    )
