import os
from dotenv import load_dotenv
import uuid
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import asyncio
import time
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# 引入熔断器与大模型网关
from llm_gateway import circuit_breaker, CircuitBreakerOpenError


# LangGraph 核心
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.errors import GraphRecursionError
from langchain_openai import ChatOpenAI

# PostgreSQL Checkpointer
from datetime import datetime
import psycopg
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

# 1. 环境与模型初始化
load_dotenv()

DB_URI = "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable"
pool: Optional[ConnectionPool] = None
graph = None

llm = ChatOpenAI(
    model=os.getenv("DASHSCOPE_MODEL_NAME", "qwen3.8-flash"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    temperature=0
)

# 2. 导入与主图集成
from phase2_full_agent import builder
from freebie_rules import inspect_proposal_elements, CATEGORY_FREEBIE_CONFIGS, detect_category_rule

def init_graph(checkpointer: PostgresSaver):
    return builder.compile(checkpointer=checkpointer)

def detect_category_code(sales_input: str) -> str:
    """
    根据销售提单文本自动提取商品品类代码：
    A - 显卡类 (RTX 5090, RTX 5080, RX 7900, 显卡...)
    B - 手机类 (苹果18, Mate70, 小米15, 手机...)
    C - 耳机类 (AirPods, FreeBuds, 索尼降噪, 耳机...)
    D - 笔记本电脑类 (ThinkPad, 拯救者, MacBook, 枪神, 笔记本...)
    E - 硬盘类 (固态硬盘, 机械硬盘, 990 PRO, Exos, 硬盘, SSD...)
    F - 企业IT类 (交换机, 服务器, Catalyst, PowerEdge...)
    G - DIY散件类 (CPU, 处理器, Ultra 9, 9950X, 散热器, 水冷, 主板, 电源...)
    Z - 其他通用商品
    """
    text = (sales_input or "").lower()
    if any(k in text for k in ["显卡", "rtx", "5090", "5080", "7900", "geforce", "radeon"]):
        return "A"
    if any(k in text for k in ["手机", "苹果18", "mate70", "小米15", "iphone", "pro max", "远峰蓝", "羽砂黑"]):
        return "B"
    if any(k in text for k in ["耳机", "airpods", "freebuds", "1000xm5", "降噪豆"]):
        return "C"
    if any(k in text for k in ["笔记本", "thinkpad", "拯救者", "macbook", "枪神", "电脑", "商务本", "游戏本"]):
        return "D"
    if any(k in text for k in ["固态", "机械硬盘", "990 pro", "exos", "硬盘", "ssd", "nvme"]):
        return "E"
    if any(k in text for k in ["交换机", "服务器", "catalyst", "poweredge"]):
        return "F"
    if any(k in text for k in ["cpu", "处理器", "intel", "酷睿", "i7", "i9", "ultra 9", "amd", "锐龙", "9950x", "散热", "水冷", "风冷", "主板", "电源"]):
        return "G"
    return "Z"

# 缓存历史老任务的规整编号映射，保证同一个历史线程每次刷新编号固定一致
LEGACY_ORDER_CACHE: Dict[str, str] = {}
LEGACY_CAT_COUNTERS: Dict[str, int] = {}

def normalize_order_identifier(raw_order_id: Optional[str], thread_id: str, product_text: str = "") -> str:
    """
    确保返回符合业务分类规则的规范编号 (如 A0001, B0001, C0001...)：
    1. 如果 raw_order_id 已经符合规则 (单字母 + 4位数字)，直接返回；
    2. 如果是历史遗留的 th-xxxx 或 test-xxxx，根据商品名称和内容自动检测品类代码并生成稳定的规范流水号。
    """
    import re
    if raw_order_id and re.match(r'^[A-Z][0-9]{4}$', str(raw_order_id)):
        return raw_order_id
    
    if thread_id in LEGACY_ORDER_CACHE:
        return LEGACY_ORDER_CACHE[thread_id]
        
    cat_code = detect_category_code(product_text)
    LEGACY_CAT_COUNTERS[cat_code] = LEGACY_CAT_COUNTERS.get(cat_code, 0) + 1
    normalized_id = f"{cat_code}{LEGACY_CAT_COUNTERS[cat_code]:04d}"
    LEGACY_ORDER_CACHE[thread_id] = normalized_id
    return normalized_id

def get_next_order_id(category_code: str) -> str:
    """原子全局递增获取某品类的规范序列号，彻底避免跨日期与历史已存在 ID 碰撞"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS global_order_sequences (
                    category_code VARCHAR(10) PRIMARY KEY,
                    current_seq INT NOT NULL DEFAULT 0
                );
            """)
            cur.execute("""
                INSERT INTO global_order_sequences (category_code, current_seq)
                VALUES (%s, (
                    SELECT COALESCE(MAX(SUBSTRING(thread_id FROM 2)::INT), 0)
                    FROM checkpoints
                    WHERE thread_id ~ %s
                ) + 1)
                ON CONFLICT (category_code)
                DO UPDATE SET current_seq = GREATEST(
                    global_order_sequences.current_seq + 1,
                    (SELECT COALESCE(MAX(SUBSTRING(thread_id FROM 2)::INT), 0) + 1 FROM checkpoints WHERE thread_id ~ %s)
                )
                RETURNING current_seq;
            """, (category_code, f'^{category_code}\\d{{4}}$', f'^{category_code}\\d{{4}}$'))
            seq = cur.fetchone()[0]
    return f"{category_code}{seq:04d}"

# 3. 生命周期与应用实例化
@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, graph
    pool = ConnectionPool(conninfo=DB_URI, max_size=20, kwargs={"autocommit": True})
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS order_sequences (
                    category_code VARCHAR(10) NOT NULL,
                    order_date DATE NOT NULL,
                    current_seq INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (category_code, order_date)
                );
            """)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    graph = init_graph(checkpointer)
    yield
    if pool:
        pool.close()

app = FastAPI(title="B2B Agent 智能审批服务", lifespan=lifespan)

# 允许前端 Next.js (跨域调用)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. 请求与响应 DTO 定义
class SubmitRequest(BaseModel):
    sales_input: str = Field(..., example="帮我下 500 台远峰蓝苹果18，给客户打 8.8 折，并承诺送 2 年延保和 500 个保护壳")
    thread_id: Optional[str] = None

class ResumeRequest(BaseModel):
    approved_discount: float = Field(..., example=0.85)
    comment: str = Field(..., example="同意特批，但不可低于 8.5 折")

class SupervisorDecisionRequest(BaseModel):
    action: str = Field(..., example="approve")  # "approve" | "reject"
    approved_discount: Optional[float] = Field(None, example=0.90)
    comment: Optional[str] = Field(None, example="同意特批放行")
    instructions: Optional[str] = Field(None, example="变相让利过多导致毛利率跌破红线！要求延保最多1年，壳砍半至250个，折扣不得低于9折")
    target_discount: Optional[float] = Field(None, example=0.90)
    target_warranty_years: Optional[int] = Field(None, example=1)
    target_quantity: Optional[int] = Field(None, example=500)
    target_freebies: Optional[dict] = Field(None, example={})

class SalesResubmitRequest(BaseModel):
    revised_input: str = Field(..., example="帮我下 500 台远峰蓝苹果18，给客户打 9 折，承诺送 1 年延保和 250 个保护壳")

class PreflightCheckRequest(BaseModel):
    sales_input: str = Field(..., example="帮我下 60 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9.0 折")

# 5. REST 核心接口

@app.post("/api/submit")
def submit_approval(req: SubmitRequest):
    """销售提交申请单"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if req.thread_id:
        thread_id = req.thread_id
        order_id = req.thread_id
        created_at = now_str
    else:
        cat_code = detect_category_code(req.sales_input)
        order_id = get_next_order_id(cat_code)
        thread_id = order_id
        created_at = now_str

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 30  # 物理断路器：支持多轮驳回与工具流转，杜绝死循环
    }

    try:
        # 启动图执行
        graph.invoke(
            {
                "sales_input": req.sales_input, 
                "retry_count": 0, 
                "revision_count": 0,
                "order_id": order_id,
                "created_at": created_at
            },
            config=config
        )
    except GraphRecursionError:
        return {
            "thread_id": thread_id,
            "order_id": order_id,
            "created_at": created_at,
            "status": "CIRCUIT_BREAKER",
            "message": "⚠️ 触发系统防死循环保护（Recursion Limit）：Agent 循环调用超限，已强制切断",
            "current_values": {}
        }
    except Exception as e:
        return {
            "thread_id": thread_id,
            "order_id": order_id,
            "created_at": created_at,
            "status": "ERROR",
            "message": f"执行异常: {str(e)}",
            "current_values": {}
        }

    # 检查状态机执行后的快照
    state = graph.get_state(config)
    if state.next and state.tasks and state.tasks[0].interrupts:
        interrupt_val = state.tasks[0].interrupts[0].value
        return {
            "thread_id": thread_id,
            "order_id": order_id,
            "created_at": created_at,
            "status": interrupt_val.get("task_status", "PENDING_APPROVAL"),
            "message": "已命中风控红线，已挂起等待主管审批",
            "interrupt_data": interrupt_val,
            "current_values": state.values
        }
    
    # 若未能成功提取到商机编号，说明库中无此商品并提前终止
    if not state.values.get("opportunity_id"):
        return {
            "thread_id": thread_id,
            "order_id": order_id,
            "created_at": created_at,
            "status": "NOT_FOUND",
            "message": "商品库中未能匹配到相关商品，提单已安全终止，请核对商品型号",
            "current_values": state.values
        }

    return {
        "thread_id": thread_id,
        "order_id": order_id,
        "created_at": created_at,
        "status": "COMPLETED",
        "message": "无需人工干预，各项指标合规，已自动通过",
        "current_values": state.values
    }

@app.get("/api/circuit-status")
def get_circuit_status():
    """获取大模型断路器当前状态与指标"""
    return circuit_breaker.get_status()

def serialize_state_values(values: dict) -> dict:
    """过滤剥离庞大的原始消息历史，仅保留干净的业务与风控参数，确保 JSON 序列化极速且 100% 安全"""
    if not isinstance(values, dict):
        return {}
    res = {}
    for k, v in values.items():
        if k == "messages":
            continue  # 剥离成千上万字的大模型 Prompt 与对话历史
        elif isinstance(v, (str, int, float, bool, list, dict, type(None))):
            res[k] = v
        else:
            res[k] = str(v)
    return res

def safe_dumps(data: dict) -> str:
    """保证任意对象（含异常/特殊对象）均能安全转为 JSON 字符串"""
    return json.dumps(data, default=str, ensure_ascii=False)

@app.post("/api/submit-stream")
async def submit_proposal_stream(req: SubmitRequest):
    """
    通信架构层：SSE 流式输出接口
    - 后端每 1 秒向下游推送一次心跳保活包与节点进展
    - 若断路器已熔断，直接推送 CIRCUIT_OPEN 事件，触发前端兜底表单降级
    - 主动探查 LangGraph interrupt() 挂起状态，精准秒级断流，彻底杜绝前端连接挂死转圈
    """
    async def event_generator():
        import traceback
        try:
            # 1. 检查断路器
            try:
                circuit_breaker.before_call()
            except CircuitBreakerOpenError as ce:
                yield f"data: {safe_dumps({'event': 'CIRCUIT_OPEN', 'message': str(ce), 'fallback_required': True})}\n\n"
                return

            cat_code = detect_category_code(req.sales_input)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if req.thread_id:
                thread_id = req.thread_id
                order_id = req.thread_id
                created_at = now_str
            else:
                order_id = get_next_order_id(cat_code)
                thread_id = order_id
                created_at = now_str

            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 30
            }

            # 推送连接建立与初始事件
            yield f"data: {safe_dumps({'event': 'STARTED', 'thread_id': thread_id, 'order_id': order_id, 'message': 'Agent 接收到提单请求，正在启动状态机分析...'})}\n\n"

            # 在独立线程池中异步运行 LangGraph
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                None,
                lambda: graph.invoke(
                    {
                        "sales_input": req.sales_input, 
                        "retry_count": 0, 
                        "revision_count": 0,
                        "order_id": order_id,
                        "created_at": created_at
                    },
                    config=config
                )
            )

            step_messages = [
                "正在执行 NLP 预处理、剥离表层杂质与无关配件...",
                "正在调用 pgvector 稠密向量与 BM25 全文索引混合召回...",
                "正在执行 Cross-Encoder 交叉重排，锁定最优物理物料...",
                "正在核算 True Margin 真实利润与 BOM 让利风控边界..."
            ]
            step_idx = 0
            max_wait_seconds = 40.0  # 绝对硬时间红线：40秒内必须收尾
            start_wait_time = time.time()

            # 心跳保活与状态感知双循环 (每 1 秒探查一次，彻底消除挂死！)
            while True:
                elapsed = time.time() - start_wait_time

                # 1. 核心关键修复：主动探查当前 State 是否已命中 interrupt() 写入数据库
                try:
                    current_state = graph.get_state(config)
                    if current_state and current_state.tasks and any(t.interrupts for t in current_state.tasks):
                        itask = next(t for t in current_state.tasks if t.interrupts)
                        interrupt_val = itask.interrupts[0].value
                        clean_vals = serialize_state_values(current_state.values)
                        print(f"[SSE Stream] ⚡ 发现 LangGraph 已进入 interrupt 挂起状态！立即向前端推送 INTERRUPT 事件结束连接")
                        yield f"data: {safe_dumps({'event': 'INTERRUPT', 'thread_id': thread_id, 'order_id': order_id, 'created_at': created_at, 'status': interrupt_val.get('task_status', 'PENDING_APPROVAL'), 'message': '已命中风控红线，已挂起等待主管审批', 'interrupt_data': interrupt_val, 'current_values': clean_vals})}\n\n"
                        return
                except Exception as se:
                    print(f"[SSE Stream] 探查快照异常: {se}")

                # 2. 如果线程池中的图执行已经彻底结束
                if future.done():
                    break

                # 3. 超过绝对硬预算强制跳出，触发超时降级
                if elapsed > max_wait_seconds:
                    print(f"[SSE Stream] ⚠️ 达到绝对硬时间红线 ({max_wait_seconds}s)，后台未及时完成，转入确定性降级...")
                    break

                # 4. 正常心跳推进
                step_idx += 1
                msg = step_messages[step_idx % len(step_messages)]
                yield f"data: {safe_dumps({'event': 'HEARTBEAT', 'step': step_idx, 'message': msg})}\n\n"
                await asyncio.sleep(1.0)

            # 超时保护判定：若心跳跳出后线程仍未完成，直接触发降级表单
            if not future.done():
                yield f"data: {safe_dumps({'event': 'TIMEOUT', 'thread_id': thread_id, 'order_id': order_id, 'created_at': created_at, 'status': 'TIMEOUT', 'message': 'AI 解析运算超时，已为您无缝切换至生产高可用标准提单表单', 'fallback_required': True})}\n\n"
                return

            # 获取图执行结果与状态 (捕获异常与断路器)
            if future.done():
                try:
                    future.result()
                except GraphRecursionError:
                    yield f"data: {safe_dumps({'event': 'ERROR', 'status': 'CIRCUIT_BREAKER', 'message': '⚠️ 触发系统防死循环保护（Recursion Limit）：Agent 循环调用超限，已强制切断'})}\n\n"
                    return
                except Exception as e:
                    err_msg = str(e)
                    is_circuit = "熔断" in err_msg or isinstance(e, CircuitBreakerOpenError)
                    yield f"data: {safe_dumps({'event': 'ERROR', 'status': 'ERROR', 'is_circuit': is_circuit, 'message': f'执行异常: {err_msg}', 'fallback_required': True})}\n\n"
                    return

            state = graph.get_state(config)
            clean_vals = serialize_state_values(state.values)
            if state and state.tasks and any(t.interrupts for t in state.tasks):
                itask = next(t for t in state.tasks if t.interrupts)
                interrupt_val = itask.interrupts[0].value
                yield f"data: {safe_dumps({'event': 'INTERRUPT', 'thread_id': thread_id, 'order_id': order_id, 'created_at': created_at, 'status': interrupt_val.get('task_status', 'PENDING_APPROVAL'), 'message': '已命中风控红线，已挂起等待主管审批', 'interrupt_data': interrupt_val, 'current_values': clean_vals})}\n\n"
                return

            if not state.values.get("opportunity_id"):
                yield f"data: {safe_dumps({'event': 'NOT_FOUND', 'thread_id': thread_id, 'order_id': order_id, 'created_at': created_at, 'status': 'NOT_FOUND', 'message': '商品库中未能匹配到相关商品，提单已安全终止，请核对商品型号', 'current_values': clean_vals, 'fallback_required': True})}\n\n"
                return

            yield f"data: {safe_dumps({'event': 'COMPLETED', 'thread_id': thread_id, 'order_id': order_id, 'created_at': created_at, 'status': 'COMPLETED', 'message': '无需人工干预，各项指标合规，已自动通过', 'current_values': clean_vals})}\n\n"
        except BaseException as ex:
            print(f"[SSE Stream Exception]: {type(ex)} {ex}")
            traceback.print_exc()
            with open("scratch/sse_error.log", "w", encoding="utf-8") as f:
                f.write(f"Exception: {type(ex)}: {ex}\n")
                f.write(traceback.format_exc())
            yield f"data: {safe_dumps({'event': 'ERROR', 'status': 'ERROR', 'message': f'服务端生成流异常: {str(ex)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")



def sync_dynamic_inventory(task_data: dict, conn) -> dict:
    """
    根据数据库 products 表实时库存，动态刷新待办任务快照中的可用库存、缺口及风控状态。
    解决前序提单审批放行并扣减库存后，后续挂起的提单仍显示旧快照（死数据）的问题。
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
                
                # 覆盖为最新真实物理库存
                updated["current_stock"] = real_stock
                if order_qty > real_stock:
                    updated["stock_status"] = "SHORTAGE"
                    shortage = order_qty - real_stock
                    updated["shortage_qty"] = shortage
                    
                    # 动态更新风控红线列表
                    reasons = list(updated.get("risk_reasons") or [])
                    # 清理现有的旧库存描述
                    reasons = [r for r in reasons if "库存" not in r]
                    reasons.insert(0, f"现货库存告急 (申请{order_qty}{unit}，现存仅{real_stock}{unit}，缺口{shortage}{unit})")
                    updated["risk_reasons"] = reasons
                else:
                    updated["stock_status"] = "SUFFICIENT"
                    updated["shortage_qty"] = 0
                    # 如果原先因库存不足告警，但现在库存充足了（如补货），移除库存告警
                    reasons = list(updated.get("risk_reasons") or [])
                    updated["risk_reasons"] = [r for r in reasons if "库存" not in r]
    except Exception as e:
        print(f"[sync_dynamic_inventory] 动态查验库存异常: {e}")
        
    return updated

@app.get("/api/pending-tasks")
def get_pending_tasks():
    """主管审批工作台拉取待办任务队列（过滤出等待主管审核的任务，联动真实物理库存）"""
    tasks = []
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT thread_id FROM checkpoints GROUP BY thread_id ORDER BY MAX(checkpoint_id) DESC LIMIT 50;")
            rows = cur.fetchall()

        for row in rows:
            tid = row[0]
            config = {"configurable": {"thread_id": tid}, "recursion_limit": 30}
            state = graph.get_state(config)
            if state.next and state.tasks and state.tasks[0].interrupts:
                interrupt_val = state.tasks[0].interrupts[0].value
                # 只返回等待主管审批的任务
                if interrupt_val.get("task_status") != "REJECTED_FOR_REVISION":
                    # 联动数据库 products 表最新真实库存
                    synced_data = sync_dynamic_inventory(interrupt_val, conn)

                    prod_text = f"{synced_data.get('product_name') or ''} {state.values.get('product_name') or ''} {state.values.get('sales_input') or ''}"
                    raw_oid = synced_data.get("order_id") or state.values.get("order_id")
                    order_id = normalize_order_identifier(raw_oid, tid, prod_text)
                    created_at = synced_data.get("created_at") or state.values.get("created_at")
                    if not created_at:
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    tasks.append({
                        "thread_id": tid,
                        "order_id": order_id,
                        "task_status": synced_data.get("task_status", "PENDING_APPROVAL"),
                        "created_at": created_at,
                        "interrupt_data": synced_data,
                        "current_values": state.values
                    })
    return {"total": len(tasks), "tasks": tasks}

@app.get("/api/sales/returned-tasks")
def get_sales_returned_tasks():
    """销售端拉取【待我修改 (Returned for Revision)】任务队列（联动真实物理库存）"""
    tasks = []
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT thread_id FROM checkpoints GROUP BY thread_id ORDER BY MAX(checkpoint_id) DESC LIMIT 50;")
            rows = cur.fetchall()

        for row in rows:
            tid = row[0]
            config = {"configurable": {"thread_id": tid}, "recursion_limit": 30}
            state = graph.get_state(config)
            if state.next and state.tasks and state.tasks[0].interrupts:
                interrupt_val = state.tasks[0].interrupts[0].value
                # 只返回主管驳回后挂起等待销售修改的任务
                if interrupt_val.get("task_status") == "REJECTED_FOR_REVISION":
                    # 联动数据库 products 表最新真实库存
                    synced_data = sync_dynamic_inventory(interrupt_val, conn)

                    prod_text = f"{synced_data.get('product_name') or ''} {state.values.get('product_name') or ''} {state.values.get('sales_input') or ''}"
                    raw_oid = synced_data.get("order_id") or state.values.get("order_id")
                    order_id = normalize_order_identifier(raw_oid, tid, prod_text)
                    created_at = synced_data.get("created_at") or state.values.get("created_at")
                    if not created_at:
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    tasks.append({
                        "thread_id": tid,
                        "order_id": order_id,
                        "task_status": "REJECTED_FOR_REVISION",
                        "supervisor_instructions": synced_data.get("supervisor_instructions"),
                        "target_discount": synced_data.get("target_discount"),
                        "target_warranty_years": synced_data.get("target_warranty_years"),
                        "target_quantity": synced_data.get("target_quantity"),
                        "target_freebies": synced_data.get("target_freebies"),
                        "previous_input": synced_data.get("previous_input") or state.values.get("sales_input"),
                        "product_name": synced_data.get("product_name"),
                        "opp_id": synced_data.get("opp_id"),
                        "quantity": synced_data.get("quantity"),
                        "unit": synced_data.get("unit"),
                        "unit_price": synced_data.get("unit_price"),
                        "cost_price": synced_data.get("cost_price"),
                        "warranty_cost_per_year": synced_data.get("warranty_cost_per_year"),
                        "current_stock": synced_data.get("current_stock"),
                        "stock_status": synced_data.get("stock_status"),
                        "shortage_qty": synced_data.get("shortage_qty"),
                        "requested_discount": synced_data.get("requested_discount"),
                        "true_margin": synced_data.get("true_margin"),
                        "warranty_years": synced_data.get("warranty_years"),
                        "freebie_items": synced_data.get("freebie_items"),
                        "freebie_details": synced_data.get("freebie_details"),
                        "revision_count": synced_data.get("revision_count", 0),
                        "risk_reasons": synced_data.get("risk_reasons", []),
                        "created_at": created_at,
                        "interrupt_data": synced_data,
                        "current_values": state.values
                    })
    return {"total": len(tasks), "tasks": tasks}

@app.get("/api/products")
def get_product_catalog():
    """获取企业商品与专属赠品物料清单，供前端兜底表单与自适应下拉菜单使用"""
    try:
        with psycopg.connect(DB_URI) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT opp_id, product_name, category_lvl1, unit, price, cost_price, warranty_cost_per_year, stock
                    FROM products ORDER BY id ASC;
                """)
                rows = cur.fetchall()
                items = []
                for r in rows:
                    items.append({
                        "opp_id": r[0],
                        "product_name": r[1],
                        "category": r[2],
                        "category_lvl1": r[2],
                        "unit": r[3],
                        "price": float(r[4]) if r[4] else 0.0,
                        "cost_price": float(r[5]) if r[5] else 0.0,
                        "warranty_cost_per_year": float(r[6]) if r[6] else 0.0,
                        "stock": r[7] or 0
                    })
                return {"total": len(items), "products": items}
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(f"[ERROR in get_product_catalog]: {err_msg}")
        with open("scratch/get_product_catalog.log", "w", encoding="utf-8") as f:
            f.write(err_msg)
        from ingest_products import DEFAULT_SAMPLE_PRODUCTS
        return {"total": len(DEFAULT_SAMPLE_PRODUCTS), "products": DEFAULT_SAMPLE_PRODUCTS, "fallback": True}


@app.post("/api/supervisor/decision/{thread_id}")
def supervisor_decision(thread_id: str, req: SupervisorDecisionRequest):
    """主管审批决策：同意特批放行 OR 驳回要求销售修改"""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}
    state = graph.get_state(config)
    
    if not state.next:
        # 幂等性保障：如果任务已经审批完结，且主管再次点击放行，直接返回已完成状态
        if state.values and (state.values.get("task_status") == "COMPLETED" or state.values.get("supervisor_decision") == "APPROVE"):
            if req.action != "reject":
                return {
                    "thread_id": thread_id,
                    "status": "COMPLETED",
                    "message": "该提单此前已特批放行完成，订单已归档入库，请勿重复操作",
                    "final_values": state.values
                }
            else:
                raise HTTPException(status_code=400, detail="该提单此前已特批放行入库，无法再次驳回修改")
        
        detail_msg = "该提单已审批完结" if state.values else "该提单不存在或已被清除"
        raise HTTPException(status_code=400, detail=f"无法操作：{detail_msg}")

    if req.action == "reject":
        instructions = req.instructions or req.comment or "方案让利过大，请调整报价与权益后重新提交"
        resume_payload = {
            "action": "reject",
            "instructions": instructions,
            "comment": req.comment or f"主管驳回：{instructions}",
            "target_discount": req.target_discount,
            "target_warranty_years": req.target_warranty_years,
            "target_quantity": req.target_quantity,
            "target_freebies": req.target_freebies
        }
        graph.invoke(Command(resume=resume_payload), config=config)
        new_state = graph.get_state(config)
        
        return {
            "thread_id": thread_id,
            "status": "REJECTED_FOR_REVISION",
            "message": f"提单已成功驳回，修改指示已同步至销售端: \"{instructions}\"",
            "instructions": instructions,
            "current_values": new_state.values
        }
    else:
        # 同意放行
        resume_payload = {
            "action": "approve",
            "approved_discount": req.approved_discount or state.values.get("discount", 1.0),
            "comment": req.comment or "同意特批放行"
        }
        graph.invoke(Command(resume=resume_payload), config=config)
        final_state = graph.get_state(config)
        
        return {
            "thread_id": thread_id,
            "status": "COMPLETED",
            "message": f"特批放行成功！订单已归档入库 (生效折扣: {resume_payload['approved_discount']})",
            "final_values": final_state.values
        }

@app.post("/api/sales/resubmit/{thread_id}")
def sales_resubmit(thread_id: str, req: SalesResubmitRequest):
    """销售按主管意见修改后，重新提交提单"""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}
    state = graph.get_state(config)
    
    if not state.next:
        raise HTTPException(status_code=400, detail="该任务未处于待修改状态或已完结")

    # 恢复执行销售修改节点
    graph.invoke(Command(resume={"revised_input": req.revised_input}), config=config)
    new_state = graph.get_state(config)
    
    order_id = new_state.values.get("order_id") or thread_id
    created_at = new_state.values.get("created_at")

    if new_state.next and new_state.tasks and new_state.tasks[0].interrupts:
        interrupt_val = new_state.tasks[0].interrupts[0].value
        return {
            "thread_id": thread_id,
            "order_id": interrupt_val.get("order_id") or order_id,
            "created_at": interrupt_val.get("created_at") or created_at,
            "status": interrupt_val.get("task_status", "PENDING_APPROVAL"),
            "message": "修改方案已重新提交，已重新核算毛利率并挂起等待主管二次审批",
            "interrupt_data": interrupt_val,
            "current_values": new_state.values
        }
        
    return {
        "thread_id": thread_id,
        "order_id": order_id,
        "created_at": created_at,
        "status": "COMPLETED",
        "message": "修改方案数值完全合规，无需人工二次审批，已直接自动放行入库",
        "final_values": new_state.values
    }

@app.post("/api/resume/{thread_id}")
def resume_task(thread_id: str, req: ResumeRequest):
    """向后兼容原有主管审批接口"""
    decision_req = SupervisorDecisionRequest(
        action="approve",
        approved_discount=req.approved_discount,
        comment=req.comment
    )
    return supervisor_decision(thread_id, decision_req)



@app.post("/api/products/restock")
def restock_products():
    """一键重置/恢复所有商品演示库存至初始标准值"""
    from ingest_products import DEFAULT_SAMPLE_PRODUCTS
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for p in DEFAULT_SAMPLE_PRODUCTS:
                cur.execute(
                    "UPDATE products SET stock = %s WHERE opp_id = %s;",
                    (p["stock"], p["opp_id"])
                )
    return {"status": "SUCCESS", "message": f"成功重置 {len(DEFAULT_SAMPLE_PRODUCTS)} 款商品的演示库存！"}

@app.post("/api/preflight-check")
def preflight_check(req: PreflightCheckRequest):
    """销售提单前置智能校验：分析商品品类、赠品完整性与延保必填项"""
    result = inspect_proposal_elements(req.sales_input)
    return result

@app.post("/api/nlp-parse")
def nlp_parse(req: PreflightCheckRequest):
    """
    NLP 提单要素预处理与标准结构化表单解析接口：
    精准提炼主商品及数量、赠送商品及数量、折扣率、延保期限，组装标准结构化表单并返回。
    """
    from sales_nlp_pipeline import nlp_pipeline
    structured_form = nlp_pipeline.extract_structured_form(req.sales_input)
    return {
        "status": "SUCCESS",
        "structured_proposal_form": structured_form,
        **structured_form
    }

@app.get("/api/product-freebie-rules")
def get_product_freebie_rules():
    """获取全品类权威专属赠品配置矩阵 (供主管测算栏与销售工作台展示)"""
    return {"rules": CATEGORY_FREEBIE_CONFIGS, **CATEGORY_FREEBIE_CONFIGS}