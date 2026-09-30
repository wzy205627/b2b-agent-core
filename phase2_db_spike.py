import os
from dotenv import load_dotenv

# 加载 .env 激活 LangSmith
load_dotenv()

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

# 引入 Postgres 持久化相关的包
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver


class SimpleApprovalState(TypedDict):
    opportunity_id: str
    discount: float
    final_discount: Optional[float]
    approval_comment: Optional[str]

def intent_node(state: SimpleApprovalState):
    print("\n[Node: Intent] 识别到销售提单申请...")
    return {"opportunity_id": "OPP-9901", "discount": 0.75}

def risk_node(state: SimpleApprovalState):
    print(f"[Node: Risk] 当前申请折扣: {state['discount'] * 10} 折")
    if state["discount"] < 0.85:
        print("[Node: Risk] 触发风控红线！正在挂起并持久化到 PostgreSQL...")
        human_decision = interrupt({
            "reason": "特价折扣超出销售权限",
            "requested_discount": state["discount"],
            "opp_id": state["opportunity_id"]
        })
        return {
            "final_discount": human_decision["approved_discount"],
            "approval_comment": human_decision["comment"]
        }
    return {"final_discount": state["discount"], "approval_comment": "系统自动放行"}

def execute_node(state: SimpleApprovalState):
    print("\n[Node: Execute] CRM 系统提单最终确认:")
    print(f"  -> 生效折扣: {state['final_discount'] * 10} 折")
    print(f"  -> 审批批注: {state['approval_comment']}")
    return state

# 编排图（和阶段一完全一样）
builder = StateGraph(SimpleApprovalState)
builder.add_node("intent", intent_node)
builder.add_node("risk", risk_node)
builder.add_node("execute", execute_node)
builder.add_edge(START, "intent")
builder.add_edge("intent", "risk")
builder.add_edge("risk", "execute")
builder.add_edge("execute", END)

# ================= 核心重构区 =================
# 数据库连接 URI (对应 docker-compose 里的配置)
DB_URI = "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable"

if __name__ == "__main__":
    thread_config = {"configurable": {"thread_id": "session-db-001"}}

    # 1. 建立数据库连接池
    with ConnectionPool(DB_URI, max_size=10,kwargs={"autocommit":True}) as pool:
        # 2. 初始化 PostgresSaver
        checkpointer = PostgresSaver(pool)
        
        # 自动在数据库中创建表结构 (checkpoints, checkpoint_blobs, checkpoint_writes)
        checkpointer.setup() 
        
        # 编译图，挂载真实的数据库检查点
        graph = builder.compile(checkpointer=checkpointer)

        # ---------------- 模拟断开执行的场景 ----------------
        
        # 获取当前状态看看是否已经有存货
        current_state = graph.get_state(thread_config)
        
        if not current_state.next:
            print("===== 阶段一：新任务入库 =====")
            # 如果没有挂起的任务，说明是全新的，发起调用
            graph.invoke({}, config=thread_config)
            print("\n[提示] 此时 Python 脚本已经运行结束。你可以假装服务器重启了。")
            
        elif current_state.next[0] == 'risk':
            print("===== 阶段二：从 PostgreSQL 唤醒历史挂起任务 =====")
            print(f"[数据库提取] 发现挂起的中断数据: {current_state.tasks[0].interrupts[0].value}")
            
            human_input = {
                "approved_discount": 0.82, 
                "comment": "总监修改为 8.2 折放行"
            }
            # 携带 Command 恢复执行
            graph.invoke(Command(resume=human_input), config=thread_config)
            
            print("\n[成功] 已清空该 Thread 的中断状态，流转结束。")