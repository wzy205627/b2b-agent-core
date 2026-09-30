import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

# 1. 定义图的状态结构
class  SimpleApprovalState(TypedDict):
    opportunity_id: str
    discount: float
    final_discount: Optional[float]
    approval_comment: Optional[str]

# 2. 定义业务节点
def intent_node(state: SimpleApprovalState):
    print("\n[Node: Intent] 识别到销售提单申请...")
    return {"opportunity_id": "OPP-9901", "discount": 0.75}

def risk_node(state: SimpleApprovalState):
    print(f"[Node: Risk] 当前申请折扣: {state['discount'] * 10} 折")
    if state["discount"] < 0.85:
        print("[Node: Risk] 触发风控红线 (低于8.5折)！正在挂起工作流，等待主管审批...")
        # interrupt 会将字典抛给外部，并阻断执行流
        human_decision = interrupt({
            "reason": "特价折扣超出销售权限",
            "requested_discount": state["discount"],
            "opp_id": state["opportunity_id"]
        })
        # 恢复运行后，从 human_decision 提取人类修改的值
        return {
            "final_discount": human_decision["approved_discount"],
            "approval_comment": human_decision["comment"]
        }
    return {"final_discount": state["discount"], "approval_comment": "系统自动放行"}

def execute_node(state: SimpleApprovalState):
    print("\n[Node: Execute] CRM 系统提单最终确认:")
    print(f"  -> 商机编号: {state['opportunity_id']}")
    print(f"  -> 最终生效折扣: {state['final_discount'] * 10} 折")
    print(f"  -> 审批批注: {state['approval_comment']}")
    return state

# 3. 编排图
builder = StateGraph(SimpleApprovalState)
builder.add_node("intent", intent_node)
builder.add_node("risk", risk_node)
builder.add_node("execute", execute_node)

builder.add_edge(START, "intent")
builder.add_edge("intent", "risk")
builder.add_edge("risk", "execute")
builder.add_edge("execute", END)

# 挂载内存检查点并编译
checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# 4. 模拟两阶段执行
if __name__ == "__main__":
    thread_config = {"configurable": {"thread_id": "session-test-001"}}

    print("===== 阶段一：销售发起申请 =====")
    # 第一次运行：在 risk 节点被挂起
    graph.invoke({}, config=thread_config)

    # 查看当前快照，模拟 Agent Inbox 获取待办
    current_state = graph.get_state(thread_config)
    print("\n[系统检测] 工作流当前状态:")
    print(f"  -> 下一个待执行节点: {current_state.next}")
    if current_state.next:
        print(f"  -> 捕获的中断内容: {current_state.tasks[0].interrupts[0].value}")
        #查看当前工作流状态字典里有哪些字段已经被写入,哪些还是None
        print(f"当前工作流状态字典: {current_state.values}")
        # 模拟主管在 Agent Inbox 查看后修改了参数并同意
        print("\n===== 阶段二：主管介入审批 (Resume) =====")
        human_input = {
            "approved_discount": 0.80, # 主管将 7.5 折覆写为 8.0 折
            "comment": "毛利红线，最高只能给 8 折"
        }
        
        # 携带 Command(resume=...) 继续推进执行
        graph.invoke(Command(resume=human_input), config=thread_config)
    else:
        print("  -> 工作流已直接完成，无需人工介入。")