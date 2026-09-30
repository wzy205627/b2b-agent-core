import os
import re
from typing import TypedDict, Optional, List, Annotated, Any
from dotenv import load_dotenv

# LangGraph 核心库
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.types import interrupt, Command
from langgraph.prebuilt import ToolNode

# 消息与大模型
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, AnyMessage, RemoveMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# PostgreSQL 持久化 Checkpointer
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

# 导入企业级双路召回 + Rerank 工具
from agent_tools import query_product_database
from freebie_rules import filter_and_calc_freebies, detect_category_rule
import psycopg

# 1. 加载环境变量与数据库连接
load_dotenv()
DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable")

# 2. 导入高可用大模型网关 (15秒超时控制、主备自动漂移、断路器熔断)
from llm_gateway import llm_gateway, circuit_breaker, CircuitBreakerOpenError

tools = [query_product_database]


# ==================== 财务成本与赠品核算基准 ====================

# 专属赠品与配件底线核算成本映射表
ACCESSORY_COST_MAP = {
    # 独立显卡专属赠品配件
    "ARGB发光重型显卡支架": 65.0,
    "ARGB发光显卡支架": 65.0,
    "ARGB显卡支架": 65.0,
    "发光显卡支架": 65.0,
    "重型显卡支架": 65.0,
    "显卡支架": 65.0,
    "千斤顶显卡支架": 25.0,
    "千斤顶支架": 25.0,
    "支架": 35.0,
    "12VHPWR": 35.0,
    "显卡转接线": 35.0,

    # 蓝牙无线耳机专属赠品配件
    "耳机保护套": 15.0,
    "耳机硅胶套": 15.0,
    "硅胶保护套": 15.0,
    "耳机套": 15.0,
    "保护套": 15.0,
    "防丢绳": 10.0,
    
    # 笔记本电脑专属赠品外设与配件
    "客制化机械键盘": 160.0,
    "机械键盘": 160.0,
    "电竞键盘": 160.0,
    "键盘": 160.0,
    "电竞鼠标": 110.0,
    "游戏鼠标": 110.0,
    "无线静音鼠标": 120.0,
    "无线蓝牙鼠标": 120.0,
    "无线鼠标": 120.0,
    "静音鼠标": 120.0,
    "商务鼠标": 120.0,
    "原装鼠标": 240.0,
    "鼠标": 110.0,
    "双肩包": 55.0,
    "电脑包": 55.0,
    "内胆包": 50.0,
    "鼠标垫": 20.0,

    # 手机专属赠品配件
    "芳纶纤维磁吸防摔保护壳": 45.0,
    "芳纶纤维保护壳": 45.0,
    "芳纶纤维": 45.0,
    "微泵液冷保护壳": 60.0,
    "微泵液冷壳": 60.0,
    "手机保护壳": 45.0,
    "手机壳": 45.0,
    "保护壳": 45.0,
    "手机套": 45.0,
    "皮套": 80.0,
    "壳": 45.0,
    "防爆钢化保护膜": 10.0,
    "防爆钢化膜": 10.0,
    "高清防窥钢化膜": 10.0,
    "防窥钢化膜": 10.0,
    "防窥膜": 10.0,
    "防爆膜": 8.0,
    "钢化膜": 10.0,
    "保护膜": 8.0,
    "AR膜": 8.0,
    "膜": 8.0,
    "快充套装": 85.0,
    "氮化镓快充": 85.0,
    "氮化镓": 85.0,
    "快充头": 85.0,
    "快充": 85.0,
    "充电器": 85.0,
    "充": 85.0,
    "数据线": 25.0,
    "线": 20.0,
}

def parse_freebie_concessions(freebie_items: List[Any], order_quantity: int, product_name: str = "") -> tuple[float, List[dict]]:
    """
    解析销售申请中口头承诺附赠的配件与礼品，严格根据主标的商品品类进行白名单核验：
    1. 非本品类赠品（例如显卡送防爆钢化膜）直接无视过滤并剔除；
    2. 兼容大模型可能输出的 JSON 格式或残缺字符串，杜绝畸形名称；
    3. 散件及企业 IT 硬件严格无赠品。
    """
    return filter_and_calc_freebies(freebie_items, product_name, order_quantity)


# 3. 定义数据结构
class ExtractionSchema(BaseModel):
    is_matched: bool = Field(description="是否在商品库或对话中成功匹配到了合法的商品商机。若未检索到或商品不存在，必须设为 False")
    opportunity_id: Optional[str] = Field(default=None, description="商机编号，格式必须如 OPP-8848 或 OPP-002。若未匹配到有效商品，必须为 None")
    product_name: Optional[str] = Field(default=None, description="匹配到的官方商品全名。若未匹配到有效商品，必须为 None")
    discount: Optional[float] = Field(default=1.0, description="折扣率，必须是 0 到 1 之间的小数，如 0.88。若无特殊折扣则为 1.0")
    quantity: int = Field(default=1, description="销售申请采购的数量，若申请中提及则提取，默认1")
    unit: Optional[str] = Field(default="台", description="商品计量单位（如 台、本、个、箱、盒、张）")
    unit_price: Optional[float] = Field(default=0.0, description="官方标准单价")
    cost_price: Optional[float] = Field(default=0.0, description="工具返回该商品的硬件底线成本价 (BOM cost)")
    warranty_cost_per_year: Optional[float] = Field(default=0.0, description="工具返回该商品每年延保基准成本")
    current_stock: Optional[int] = Field(default=0, description="当前可用库存数量")
    stock_status: Optional[str] = Field(default="UNKNOWN", description="库存可用状态：SUFFICIENT (充足) 或 SHORTAGE (短缺)")
    shortage_qty: Optional[int] = Field(default=0, description="库存缺口数量")
    warranty_years: int = Field(default=0, description="销售口头承诺附赠的额外延保年数，如'送2年延保'提取2，'送1年原厂质保'提取1，若未赠送延保必须为0")
    freebie_items: List[str] = Field(default_factory=list, description="销售口头承诺附赠的免费配件/礼品清单，如['500个保护壳', '快充头']，若未提及赠品则为空列表")

class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    sales_input: str                 # 销售原始输入
    opportunity_id: Optional[str]    # 提取/查库获得的商机 ID
    product_name: Optional[str]      # 匹配到的商品全名
    discount: Optional[float]        # 提取的折扣
    final_discount: Optional[float]  # 最终生效折扣 (人工审批后)
    approval_comment: Optional[str]  # 审批意见
    order_id: Optional[str]          # 规范化提单编号 (如 A0001, B0001)
    created_at: Optional[str]        # 提单时间戳 (精确到秒，如 2026-09-13 18:35:42)
    
    # 销售-主管双向协作与闭环驳回字段
    task_status: Optional[str]              # PENDING_APPROVAL | REJECTED_FOR_REVISION | COMPLETED
    supervisor_decision: Optional[str]      # APPROVE | REJECT
    supervisor_instructions: Optional[str]  # 主管驳回时填写的具体修改要求
    target_discount: Optional[float]        # 主管整改建议目标折扣率
    target_warranty_years: Optional[int]    # 主管整改建议目标延保年数
    target_quantity: Optional[int]          # 主管整改建议目标数量 (缺口缩减)
    target_freebies: Optional[dict]         # 主管整改建议目标赠品明细
    revision_count: int                     # 修改轮次计数 (默认 0)
    
    # 业务数值与财务穿透核心字段 (防资损维度 1 + 维度 4)
    quantity: Optional[int]          # 订购数量
    unit: Optional[str]              # 量词单位
    unit_price: Optional[float]      # 单价
    cost_price: Optional[float]      # 硬件单台底线成本 (BOM)
    total_amount: Optional[float]    # 订单折前总金额 (List Revenue)
    final_amount: Optional[float]    # 订单折后实际总金额 (Contract Revenue)
    bom_total_cost: Optional[float]  # 硬件 BOM 总成本
    warranty_years: Optional[int]    # 额外赠送延保年数
    warranty_cost_per_year: Optional[float] # 每年延保基准成本
    warranty_total_cost: Optional[float]    # 延保服务总成本
    freebie_items: Optional[List[str]]      # 赠品名称列表
    freebie_details: Optional[List[dict]]   # 赠品详细核算清单
    freebie_total_cost: Optional[float]     # 赠品折算总成本
    combined_total_cost: Optional[float]    # 综合履约总成本 (BOM + 延保 + 赠品)
    true_profit: Optional[float]            # 真实净毛利 (Revenue - Combined Cost)
    true_margin: Optional[float]            # 真实综合毛利率 %
    surface_profit: Optional[float]         # 标面毛利 (未扣除隐形让利)
    surface_margin: Optional[float]         # 标面毛利率 %
    margin_risk_level: Optional[str]        # 利润风险等级: CRITICAL_LOSS | VP_SPECIAL | DIRECTOR_REVIEW | NORMAL
    approval_level: Optional[str]           # 建议审批层级: CFO / VP / 总监 / 自动放行
    recovery_suggestions: Optional[List[str]]# 商业决策与毛利恢复建议
    
    # 库存约束字段
    current_stock: Optional[int]     # 可用库存
    stock_status: Optional[str]      # SUFFICIENT | SHORTAGE
    shortage_qty: Optional[int]      # 缺货量
    risk_reasons: Optional[List[str]]# 命中的风控原因列表
    
    # 内环自愈核心字段
    crm_error: Optional[str]         # CRM API 的报错日志
    retry_count: int                 # 重试计数器

def fallback_parse_from_messages(state: AgentState) -> ExtractionSchema:
    """当大模型解析出现超时或网络异常时，从工具调用返回的结构化商品数据与原始提单中进行确定性兜底提取，保障系统 100% 不崩溃"""
    sales_input = state.get("sales_input", "")
    print("[Fallback Parser] 🛡️ 触发确定性兜底提取引擎...")
    
    # 0. 优先运行统一工业级 NLP 预处理流水线
    try:
        from sales_nlp_pipeline import nlp_pipeline
        nlp_res = nlp_pipeline.parse_and_restore(sales_input)
    except Exception:
        nlp_res = {}

    main_prod_name = nlp_res.get("main_product", {}).get("product_name") or nlp_res.get("product_term", "")
    quantity = nlp_res.get("quantity", 1)
    unit = nlp_res.get("unit", "台")
    discount = nlp_res.get("discount", 1.0)
    has_warranty = nlp_res.get("has_warranty", False)
    warranty_years = nlp_res.get("warranty_years", 0)
    
    freebie_items = []
    for fb in nlp_res.get("freebie_items", []):
        freebie_items.append(f"{fb.get('quantity', 1)}{fb.get('unit', '个')}{fb.get('freebie_name', '')}")

    # 1. 尝试从工具历史消息中定位已检索出的商品数据
    product_data = {}
    for m in reversed(state.get("messages", [])):
        content = getattr(m, "content", "")
        if isinstance(content, str) and ("opp_id" in content or "opportunity_id" in content or "product_name" in content):
            try:
                import json
                j_obj = json.loads(content)
                candidates = []
                if isinstance(j_obj, dict):
                    if "candidates" in j_obj and isinstance(j_obj["candidates"], list) and len(j_obj["candidates"]) > 0:
                        candidates = j_obj["candidates"]
                    elif j_obj.get("opportunity_id") or j_obj.get("opp_id"):
                        candidates = [j_obj]
                
                if candidates:
                    # 品牌与主品强校验：优先匹配 main_prod_name 中的核心品牌
                    matched_cand = None
                    if main_prod_name:
                        for cand in candidates:
                            cname = cand.get("product_name", "")
                            if any(b in main_prod_name for b in ["华硕", "ROG", "枪神"]) and any(b in cname for b in ["华硕", "ROG", "枪神"]):
                                matched_cand = cand
                                break
                            elif any(b in main_prod_name for b in ["联想", "拯救者", "Y9000P"]) and any(b in cname for b in ["联想", "拯救者", "Y9000P"]):
                                matched_cand = cand
                                break
                            elif any(b in main_prod_name for b in ["苹果", "iPhone", "远峰蓝"]) and any(b in cname for b in ["苹果", "iPhone", "远峰蓝"]):
                                matched_cand = cand
                                break
                            elif any(b in main_prod_name for b in ["华为", "Mate", "羽砂黑"]) and any(b in cname for b in ["华为", "Mate", "羽砂黑"]):
                                matched_cand = cand
                                break
                    
                    product_data = matched_cand if matched_cand else candidates[0]
                    break
            except Exception:
                pass

    matched_opp_id = product_data.get("opportunity_id") or product_data.get("opp_id")
    if product_data and matched_opp_id:
        stock_val = int(product_data.get("current_stock") if product_data.get("current_stock") is not None else product_data.get("stock", 0))
        unit_price_val = float(product_data.get("unit_price") if product_data.get("unit_price") is not None else product_data.get("price", 0.0))
        cost_price_val = float(product_data.get("cost_price", 0.0))
        warranty_rate_val = float(product_data.get("warranty_cost_per_year", 0.0))

        return ExtractionSchema(
            is_matched=True,
            opportunity_id=matched_opp_id,
            product_name=product_data.get("product_name"),
            discount=discount,
            quantity=quantity,
            unit=product_data.get("unit", unit),
            unit_price=unit_price_val,
            cost_price=cost_price_val,
            warranty_cost_per_year=warranty_rate_val,
            current_stock=stock_val,
            stock_status="充足" if stock_val >= quantity else "短缺",
            shortage_qty=max(0, quantity - stock_val),
            warranty_years=warranty_years,
            freebie_items=freebie_items
        )
    else:
        return ExtractionSchema(is_matched=False)

# ==================== 节点逻辑实现 ====================

SYSTEM_PROMPT = """你是一个专业的 B2B 智能提单与防资损风控 Agent。
销售人员会向你提交日常口语化的提单申请（例如：“帮我下 500 台远峰蓝苹果18，给客户打 8.8 折，并承诺送 2 年延保和 500 个保护壳”）。

你的职责与纪律如下：
1. 识别销售申请中的核心商业要素：
   - 标的商品名称、意向订购数量（如 500）、量词单位（如 '台'、'本'、'个'、'箱'）和申请折扣率（如 0.88）。
2. 敏锐识别销售的【变相降价与隐形让利承诺】（极重要，防止资损）：
   - 额外延保承诺：如“送2年延保”、“保修延长至3年”、“赠送原厂质保1年”等，精准识别延保年数；
   - 捆绑附赠配件/礼品：如“送500个保护壳”、“赠送原装手机壳”、“送快充头”、“附赠钢化膜”等，精准识别赠品名称与数量。
3. 如果申请中缺少明确的商机编号（OPP-xxxx），你必须调用 `query_product_database` 工具查询候选商品：
   - 调用工具时，【务必】传入提取到的 `requested_quantity` 和 `requested_unit`，工具会自动完成量词对齐与库存/成本信息携带！
4. 工具返回候选商品列表后，请结合语境、量词对齐得分与库存状态进行深度意图研判：
   - 优先选择量词完全对齐（如申请'台'则匹配'台'）且置信度高的商品，坚决不要误选跨类目混淆项（如误将笔记本电脑选为纸质笔记本，或误将整机选为保护壳）！
5. 选定最准确的商机编号与商品全称后，向用户汇报并进入参数流转。

6. 【防死循环与查库止损铁律（极重要）】：
   - 你对同一次提单最多只能发起 2 次工具调用（初次查询与一次同义词微调查询）。
   - 如果工具返回 "status": "low_confidence" 或 "not_found"，且经过一次微调仍未找到匹配项，说明商品库中确实无此商品！
   - 【严禁】无休止地更换同义词或反复调用工具！此时你必须立即停止调用工具，直接向销售人员回复纯文本说明：“抱歉，在商品库中未能检索到与该商品匹配的有效商机，无法完成自动提单，请核对商品型号与名称。”

7. 【3C 专属赠品配件绑定规则与 DIY 硬件散件无赠品铁律】：
   - 旗舰手机：专属赠品为手机保护壳、防爆/防窥钢化膜；
   - 蓝牙无线耳机：专属赠品为耳机保护套、硅胶防摔挂钩套；
   - 笔记本电脑：专属赠品为配套无线/电竞鼠标、机械键盘、双肩电脑包/内胆包；
   - 独立显卡：专属赠品为 ARGB 重型显卡支架、千斤顶磁吸显卡支架；
   - 【DIY 硬件散件无赠品铁律（极重要）】：
     对于 固态硬盘 (SSD)、机械硬盘 (HDD)、水冷/风冷散热器、CPU处理器、主板、电源 等 DIY 电脑硬件散件，【严禁提取任何附赠配件或赠品】（freebie_items 必须为空列表 []）！此类散件只支持提取合理的商业延保期限（如送1~3年延保），切勿提取任何配件赠品！

8. 【主卖商品与随单赠品配件彻底解耦铁律（极重要，违者严惩）】：
   - 销售人员在提单时经常同时包含主卖商品（整机标的）与随单赠品配件（例如：“帮我下 50 台华硕游戏笔记本，申请打 8.8 折，并送 2 年延保和 50 个拯救者 K7 客制化机械键盘”）。
   - 【严禁混淆主品与赠品】：在调用 `query_product_database` 查询时，查询词 query 必须是纯净的主卖商品标的（如 "华硕游戏笔记本"），【绝不能】包含赠品配件名称（如 "拯救者键盘"）！
   - 【严禁被赠品品牌干扰整机选型】：例如销售人员提单买的是“华硕游戏笔记本”，随单赠送了“拯救者键盘”，你选定的商机编号【必须是华硕游戏笔记本 (OPP-013)】，【严禁】误选为联想拯救者笔记本 (OPP-009)！赠品只能作为赠品让利条款计入 freebie_items，绝不能喧宾夺主篡改主卖商品标的！"""

def agent_intent_node(state: AgentState):
    print(f"\n[Node: Agent Intent] 正在分析销售意图、让利承诺与业务约束...")
    messages = state.get("messages", [])
    
    # 检查 messages 中是否已有与当前 sales_input 完全一致的 HumanMessage
    has_current_user_msg = any(
        isinstance(m, HumanMessage) and m.content == state["sales_input"] 
        for m in messages
    )
    
    new_messages = []
    if not messages or not has_current_user_msg:
        sys_msg = SystemMessage(content=SYSTEM_PROMPT)
        user_msg = HumanMessage(content=state["sales_input"])
        messages = [sys_msg, user_msg]
        new_messages = [sys_msg, user_msg]
    try:
        response = llm_gateway.invoke(messages, tools=tools)
        return {"messages": new_messages + [response]}
    except Exception as e:
        print(f"[Node: Agent Intent] ⚠️ LLM 网关调用异常/超时 ({e})，启用生产高可用确定性规则引擎直接召回商品...")
        from sales_nlp_pipeline import nlp_pipeline
        from agent_tools import query_product_database
        nlp_res = nlp_pipeline.parse_and_restore(state["sales_input"])
        prod_term = nlp_res.get("product_term") or state["sales_input"]
        qty = nlp_res.get("quantity") or 1
        unit = nlp_res.get("unit") or "台"
        tool_out = query_product_database.invoke({"query": prod_term, "requested_quantity": qty, "requested_unit": unit})
        fallback_ai_msg = AIMessage(content=f"已通过确定性规则引擎检索到商品数据：{tool_out}")
        return {"messages": new_messages + [fallback_ai_msg]}

def should_call_tools(state: AgentState):
    """判断 LLM 是否发起了工具调用"""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        print(f"[Router] ⚡ 发现工具调用请求: {[tc['name'] for tc in last_message.tool_calls]}，路由至 ToolNode")
        return "tools"
    print(f"[Router] 🎯 工具调用完毕或无需工具，路由至参数结构化解析节点")
    return "parse_params"

def parse_params_node(state: AgentState):
    """从对话与工具调用历史中，由结构化模型精准解析出商机、数值约束与库存财务状态"""
    print(f"\n[Node: Parse Params] 解析提取业务数值、赠品延保与库存财务参数...")
    
    prompt = f"""
    请阅读销售原始申请以及与商品库的工具交互返回的候选商品，精准提取最终提单参数与让利条款：
    原始销售申请: "{state['sales_input']}"
    
    交互历史与候选商品 (包含成本、单价、库存信息):
    {[m.content for m in state['messages'] if m.content]}
    
    提取规则：
    1. 若成功在商品库中匹配到有效商品：
       - 提取商机编号 (opportunity_id)、商品全称 (product_name)、申请折扣率 (discount，如 0.88，未提及折扣则为 1.0)
       - 提取订购数量 (quantity，如 500) 和量词单位 (unit，如'台')
       - 提取该商品的官方单价 (unit_price)、硬件底线BOM成本 (cost_price)、每年延保基准成本 (warranty_cost_per_year)
       - 提取当前库存 (current_stock)、库存状态 (stock_status)、缺口量 (shortage_qty)
       - 敏锐捕捉变相让利承诺：
         * 提取口头赠送的延保年数 warranty_years (如'送2年延保'提取2，未提及则为0)
         * 提取口头承诺附赠的配件/赠品 freebie_items 列表 (如['50个显卡支架']，未提及则为空列表)
         * 【格式铁律】：freebie_items 必须是普通文本字符串列表（例如 ['50个显卡支架']），严禁输出任何 JSON 格式对象！
         * 【品类排他铁律】：显卡只能送显卡支架；手机只能送手机壳/钢化膜/快充；耳机只能送保护套；电脑只能送键盘/鼠标/电脑包；散件绝不设赠品！若销售口头提到了不属于该商品的赠品（例如显卡提报送钢化膜或手机壳），严禁录入，直接忽略！
       - 将 is_matched 设为 True
    2. 注意辨别销售意图是整机设备还是配件，准确选出对应商机。
    3. 若商品库中明确未检索到该商品（或返回 low_confidence / not_found），不要捏造商机编号！请将 is_matched 设为 False，opportunity_id 设为 None。
    """
    try:
        result = llm_gateway.invoke_structured(prompt, schema=ExtractionSchema)
    except Exception as e:
        print(f"[Node: Parse Params] ⚠️ 大模型网关调用发生异常/熔断 ({e})，正在执行高可用确定性兜底解析...")
        result = fallback_parse_from_messages(state)


    if result.is_matched and result.opportunity_id:
        qty = result.quantity or 1
        price = result.unit_price or 0.0
        disc = result.discount if (result.discount is not None and result.discount > 0) else 1.0
        cost_price = result.cost_price or 0.0
        warranty_rate = result.warranty_cost_per_year or 0.0
        warranty_years = result.warranty_years or 0
        freebie_items = result.freebie_items or []
        p_name = result.product_name or ""

        # 1. 营收计算
        total_amt = round(price * qty, 2)
        final_amt = round(total_amt * disc, 2)
        
        # 2. 硬件 BOM 总成本
        bom_total_cost = round(cost_price * qty, 2)
        
        # 3. 延保服务折算成本 (费率 * 年数 * 订购台数)
        warranty_total_cost = round(warranty_rate * warranty_years * qty, 2)
        
        # 4. 赠品/配件折算成本 (严格按标的商品品类进行专属白名单过滤与名称清洗)
        freebie_total_cost, freebie_details = parse_freebie_concessions(freebie_items, qty, p_name or state['sales_input'])
        freebie_items = [d["name"] for d in freebie_details]
        
        # 5. 综合履约总成本与穿透毛利
        combined_total_cost = round(bom_total_cost + warranty_total_cost + freebie_total_cost, 2)
        true_profit = round(final_amt - combined_total_cost, 2)
        true_margin = round((true_profit / final_amt * 100), 2) if final_amt > 0 else 0.0
        
        # 6. 标面毛利（未考虑隐形让利前的基线）
        surface_profit = round(final_amt - bom_total_cost, 2)
        surface_margin = round((surface_profit / final_amt * 100), 2) if final_amt > 0 else 0.0
        
        print(f"[Node: Parse Params] ✅ 成功识别商机 -> ID: {result.opportunity_id}, 商品: {result.product_name}")
        print(f"  • 订购数值: {qty}{result.unit} × ¥{price:,.2f} = 标面总额 ¥{total_amt:,.2f} (申请折后实收: ¥{final_amt:,.2f}, 折扣: {disc*10:.1f}折)")
        print(f"  • 硬件BOM成本: 单台¥{cost_price:,.2f} | 总BOM成本 ¥{bom_total_cost:,.2f}")
        if warranty_years > 0:
            print(f"  • 隐形让利(延保): 承诺赠送 {warranty_years} 年延保 | 折合成本 ¥{warranty_total_cost:,.2f} (费率 ¥{warranty_rate}/台/年)")
        if freebie_total_cost > 0:
            print(f"  • 隐形让利(赠品): 附赠 {len(freebie_details)} 项配件 | 折合成本 ¥{freebie_total_cost:,.2f} (清单: {freebie_items})")
        print(f"  • 综合履约总成本: ¥{combined_total_cost:,.2f} | 真实净毛利: ¥{true_profit:,.2f} | 真实综合毛利率: {true_margin:.2f}% (标面毛利率: {surface_margin:.2f}%)")
        print(f"  • 库存状态: {result.stock_status} (现存 {result.current_stock}{result.unit}, 缺口: {result.shortage_qty}{result.unit})")
        
        return {
            "opportunity_id": result.opportunity_id,
            "product_name": result.product_name,
            "discount": disc,
            "quantity": qty,
            "unit": result.unit,
            "unit_price": price,
            "cost_price": cost_price,
            "warranty_years": warranty_years,
            "warranty_cost_per_year": warranty_rate,
            "warranty_total_cost": warranty_total_cost,
            "freebie_items": freebie_items,
            "freebie_details": freebie_details,
            "freebie_total_cost": freebie_total_cost,
            "bom_total_cost": bom_total_cost,
            "combined_total_cost": combined_total_cost,
            "total_amount": total_amt,
            "final_amount": final_amt,
            "true_profit": true_profit,
            "true_margin": true_margin,
            "surface_profit": surface_profit,
            "surface_margin": surface_margin,
            "current_stock": result.current_stock,
            "stock_status": result.stock_status,
            "shortage_qty": result.shortage_qty,
            "retry_count": state.get("retry_count", 0)
        }
    else:
        print(f"[Node: Parse Params] ⚠️ 未能匹配到有效商机（未收录或不存在），标记不进入风控")
        return {
            "opportunity_id": None,
            "product_name": None,
            "discount": 1.0,
            "quantity": 0,
            "unit": None,
            "unit_price": 0.0,
            "cost_price": 0.0,
            "warranty_years": 0,
            "warranty_cost_per_year": 0.0,
            "warranty_total_cost": 0.0,
            "freebie_items": [],
            "freebie_details": [],
            "freebie_total_cost": 0.0,
            "bom_total_cost": 0.0,
            "combined_total_cost": 0.0,
            "total_amount": 0.0,
            "final_amount": 0.0,
            "true_profit": 0.0,
            "true_margin": 0.0,
            "surface_profit": 0.0,
            "surface_margin": 0.0,
            "current_stock": 0,
            "stock_status": "NOT_FOUND",
            "shortage_qty": 0,
            "retry_count": state.get("retry_count", 0)
        }

def risk_node(state: AgentState):
    opp_id = state['opportunity_id']
    prod_name = state.get('product_name')
    discount = state.get('discount', 1.0)
    qty = state.get('quantity', 1)
    unit = state.get('unit') or '台'
    unit_price = state.get('unit_price', 0.0)
    cost_price = state.get('cost_price', 0.0)
    total_amt = state.get('total_amount', 0.0)
    final_amt = state.get('final_amount', round(total_amt * discount, 2))
    bom_cost = state.get('bom_total_cost', round(cost_price * qty, 2))
    warranty_years = state.get('warranty_years', 0)
    warranty_cost = state.get('warranty_total_cost', 0.0)
    freebie_cost = state.get('freebie_total_cost', 0.0)
    combined_cost = state.get('combined_total_cost', round(bom_cost + warranty_cost + freebie_cost, 2))
    true_profit = state.get('true_profit', round(final_amt - combined_cost, 2))
    true_margin = state.get('true_margin', round((true_profit / final_amt * 100), 2) if final_amt > 0 else 0.0)
    surface_margin = state.get('surface_margin', 0.0)
    stock = state.get('current_stock', 0)
    stock_status = state.get('stock_status', 'UNKNOWN')
    shortage = state.get('shortage_qty', 0)
    freebie_items = state.get('freebie_items', [])
    freebie_details = state.get('freebie_details', [])

    print(f"\n[Node: Risk] 检查防资损核心风控矩阵 (底线成本/真实毛利率/变相让利/大额/现存库存)...")
    print(f"  • 商品: [{opp_id}] {prod_name}")
    print(f"  • 订购: {qty}{unit} (标价: ¥{unit_price:,.2f}, BOM底线成本: ¥{cost_price:,.2f})")
    print(f"  • 实收总额: ¥{final_amt:,.2f} (折后单价: ¥{unit_price*discount:,.2f}, 申请折扣: {discount*10:.1f}折)")
    print(f"  • 综合总成本: ¥{combined_cost:,.2f} (硬件: ¥{bom_cost:,.2f}, 延保: ¥{warranty_cost:,.2f}, 赠品: ¥{freebie_cost:,.2f})")
    print(f"  • 真实净毛利: ¥{true_profit:,.2f} | 真实综合毛利率: {true_margin:.2f}% (标面毛利率: {surface_margin:.2f}%)")

    risk_reasons = []
    margin_risk_level = "NORMAL"
    approval_level = "自动放行"

    # 1. 极危资损红线：击穿硬件底线成本价 (单台实收 < BOM成本 或 真实净毛利为负)
    unit_selling_price = round(unit_price * discount, 2)
    if (unit_selling_price < cost_price) or (true_profit < 0):
        loss_unit = round(cost_price - unit_selling_price, 2)
        risk_reasons.append(f"🚨 击穿BOM底线成本 (单台折后¥{unit_selling_price:,.2f} < BOM成本¥{cost_price:,.2f}，单台净亏损¥{loss_unit:,.2f})")
        margin_risk_level = "CRITICAL_LOSS"
        approval_level = "CFO / 财务总监一票否决级特批"
    elif true_margin < 15.0:
        # 2. 偏高红线：真实综合毛利率低于 15% 战略警戒线
        risk_reasons.append(f"⚠️ 低毛利特批 (真实综合毛利率 {true_margin:.1f}% 低于 15% 战略底线)")
        margin_risk_level = "VP_SPECIAL"
        approval_level = "业务副总裁 (VP) 特批"
    elif true_margin < 25.0:
        # 3. 中度常规审批
        margin_risk_level = "DIRECTOR_REVIEW"
        approval_level = "部门总监 / 区域经理常规审批"
        if discount < 0.85:
            risk_reasons.append(f"特价折扣超权 ({discount*10:.1f}折低于8.5折常规底线)")

    # 4. 隐形变相让利独立预警与商业决策建议
    concession_total = round(warranty_cost + freebie_cost, 2)
    dilution_margin = round(surface_margin - true_margin, 2)
    recovery_suggestions = []
    if concession_total > 0:
        concession_desc = []
        if warranty_years > 0:
            concession_desc.append(f"赠{warranty_years}年延保(成本¥{warranty_cost:,.2f})")
        if freebie_items:
            concession_desc.append(f"赠{len(freebie_items)}项配件(成本¥{freebie_cost:,.2f})")
        
        risk_reasons.append(f"🎁 变相让利警报 ({' + '.join(concession_desc)}，侵蚀利润 ¥{concession_total:,.2f}，导致毛利率下降 {dilution_margin:.1f}%)")
        
        # 商业博弈建议
        if warranty_years > 0:
            margin_without_warranty = round(((final_amt - bom_cost - freebie_cost) / final_amt * 100), 2) if final_amt > 0 else 0.0
            recovery_suggestions.append(f"若取消额外延保承诺，真实毛利率将由 {true_margin:.1f}% 回升至 {margin_without_warranty:.1f}% (挽回 ¥{warranty_cost:,.2f})")
        if freebie_cost > 0:
            margin_without_freebies = round(((final_amt - bom_cost - warranty_cost) / final_amt * 100), 2) if final_amt > 0 else 0.0
            recovery_suggestions.append(f"若取消赠送配件，真实毛利率将由 {true_margin:.1f}% 回升至 {margin_without_freebies:.1f}% (挽回 ¥{freebie_cost:,.2f})")

    # 5. 大额金额红线 (单笔折后总金额 >= 50 万元)
    if final_amt >= 500000.0:
        risk_reasons.append(f"大额采购特批 (总金额 ¥{final_amt:,.2f} 达50万大单级)")

    # 6. 现货短缺红线 (申请量大于现存库存)
    if stock_status == "SHORTAGE" or (qty > stock):
        risk_reasons.append(f"现货库存告急 (申请{qty}{unit}，现存仅{stock}{unit}，缺口{shortage}{unit})")

    # 补充常规折扣校验
    if discount < 0.85 and not any("特价折扣超权" in r or "击穿BOM" in r for r in risk_reasons):
        risk_reasons.append(f"特价折扣超权 ({discount*10:.1f}折低于8.5折底线)")
        if margin_risk_level == "NORMAL":
            margin_risk_level = "DIRECTOR_REVIEW"
            approval_level = "部门总监 / 区域经理常规审批"

    if risk_reasons:
        print(f"[Node: Risk] ⚠️ 触发多维风控拦截 (命中 {len(risk_reasons)} 项红线，等级: {margin_risk_level})，挂起等待【{approval_level}】...")
        for r in risk_reasons:
            print(f"    - {r}")
            
        interrupt_payload = {
            "reason": "；".join(risk_reasons),
            "risk_reasons": risk_reasons,
            "margin_risk_level": margin_risk_level,
            "approval_level": approval_level,
            "opp_id": opp_id,
            "product_name": prod_name,
            "quantity": qty,
            "unit": unit,
            "unit_price": unit_price,
            "cost_price": cost_price,
            "total_amount": total_amt,
            "final_amount": final_amt,
            "requested_discount": discount,
            "bom_total_cost": bom_cost,
            "warranty_years": warranty_years,
            "warranty_cost_per_year": state.get('warranty_cost_per_year', 0.0),
            "warranty_total_cost": warranty_cost,
            "freebie_items": freebie_items,
            "freebie_details": freebie_details,
            "freebie_total_cost": freebie_cost,
            "combined_total_cost": combined_cost,
            "true_profit": true_profit,
            "true_margin": true_margin,
            "surface_profit": state.get('surface_profit', round(final_amt - bom_cost, 2)),
            "surface_margin": surface_margin,
            "recovery_suggestions": recovery_suggestions,
            "current_stock": stock,
            "stock_status": stock_status,
            "shortage_qty": shortage,
            "task_status": "PENDING_APPROVAL",
            "order_id": state.get('order_id'),
            "created_at": state.get('created_at'),
            "revision_count": state.get('revision_count', 0),
            "supervisor_instructions": state.get('supervisor_instructions'),
            "previous_input": state.get('sales_input')
        }
        human_decision = interrupt(interrupt_payload)
        action = human_decision.get("action", "approve")
        if action == "reject":
            instructions = human_decision.get("instructions") or human_decision.get("comment", "方案让利过大，请调整报价与权益后重新提交")
            print(f"\n[Node: Risk] 🛑 主管已驳回提单！修改意见: {instructions}")
            return {
                "supervisor_decision": "REJECT",
                "supervisor_instructions": instructions,
                "target_discount": human_decision.get("target_discount"),
                "target_warranty_years": human_decision.get("target_warranty_years"),
                "target_quantity": human_decision.get("target_quantity"),
                "target_freebies": human_decision.get("target_freebies"),
                "task_status": "REJECTED_FOR_REVISION",
                "approval_comment": f"主管驳回：{instructions}",
                "risk_reasons": risk_reasons,
                "margin_risk_level": margin_risk_level,
                "approval_level": approval_level
            }
        else:
            approved_discount = human_decision.get("approved_discount", discount)
            comment = human_decision.get("comment", f"{approval_level}特批放行")
            print(f"\n[Node: Risk] ✅ 收到主管 Resume 批准指令！最终批准折扣: {approved_discount}，批语: {comment}")
            return {
                "supervisor_decision": "APPROVE",
                "final_discount": approved_discount,
                "approval_comment": comment,
                "task_status": "COMPLETED",
                "risk_reasons": risk_reasons,
                "margin_risk_level": margin_risk_level,
                "approval_level": approval_level
            }
    
    print("[Node: Risk] ✅ 各项数值合规（真实毛利率充沛、无资损击穿、折扣合规且现货充足），系统秒级自动放行")
    return {
        "supervisor_decision": "APPROVE",
        "final_discount": discount,
        "approval_comment": "真实毛利率充沛，各项指标合规，系统自动放行",
        "task_status": "COMPLETED",
        "risk_reasons": [],
        "margin_risk_level": "NORMAL",
        "approval_level": "自动放行"
    }

def sales_revision_node(state: AgentState):
    """
    当主管驳回申请时，流程在此挂起，等待销售人员调整提单方案并重新提交。
    """
    print(f"\n[Node: Sales Revision] ⏸️ 提单已被主管驳回，挂起等待销售端调整申请 (第 {state.get('revision_count', 0)} 轮修改)...")
    sales_payload = {
        "type": "SALES_REVISION_REQUIRED",
        "task_status": "REJECTED_FOR_REVISION",
        "supervisor_instructions": state.get("supervisor_instructions"),
        "target_discount": state.get("target_discount"),
        "target_warranty_years": state.get("target_warranty_years"),
        "target_quantity": state.get("target_quantity"),
        "target_freebies": state.get("target_freebies"),
        "previous_input": state.get("sales_input"),
        "product_name": state.get("product_name"),
        "opp_id": state.get("opportunity_id"),
        "quantity": state.get("quantity"),
        "unit": state.get("unit"),
        "unit_price": state.get("unit_price"),
        "cost_price": state.get("cost_price"),
        "warranty_cost_per_year": state.get("warranty_cost_per_year"),
        "current_stock": state.get("current_stock"),
        "stock_status": state.get("stock_status"),
        "shortage_qty": state.get("shortage_qty"),
        "requested_discount": state.get("discount"),
        "true_margin": state.get("true_margin"),
        "warranty_years": state.get("warranty_years"),
        "freebie_items": state.get("freebie_items"),
        "freebie_details": state.get("freebie_details"),
        "order_id": state.get("order_id"),
        "created_at": state.get("created_at"),
        "revision_count": state.get("revision_count", 0),
        "risk_reasons": state.get("risk_reasons", [])
    }
    sales_response = interrupt(sales_payload)
    revised_text = sales_response.get("revised_input") or state.get("sales_input")
    new_revision_count = state.get("revision_count", 0) + 1
    print(f"[Node: Sales Revision] 📝 收到销售重新提交的提单申请 (第 {new_revision_count} 轮修改): \"{revised_text}\"")
    
    # 清空上一轮的历史消息，确保模型以全新的销售申请重新分析
    msgs_to_remove = [RemoveMessage(id=m.id) for m in state.get("messages", []) if getattr(m, "id", None)]
    return {
        "sales_input": revised_text,
        "task_status": "PENDING_APPROVAL",
        "supervisor_decision": None,
        "revision_count": new_revision_count,
        "messages": msgs_to_remove
    }

def route_after_risk(state: AgentState):
    """风控节点执行后路由：若主管驳回则流向销售修改节点，若批准则流向外部 CRM"""
    if state.get("supervisor_decision") == "REJECT":
        print("[Router] ↩️ 主管驳回提单，流转至销售修改节点 (Sales Revision)")
        return "sales_revision"
    print("[Router] ➡️ 主管批准或系统自动放行，流转至 CRM 订单入库")
    return "crm"

def mock_crm_node(state: AgentState):
    opp_id = state.get("opportunity_id")
    qty = state.get("quantity", 1)
    prod_name = state.get("product_name")
    final_disc = state.get("final_discount", 1.0)
    print(f"\n[Node: CRM API] 准备向外部系统提单 (ID: {opp_id}, 商品: {prod_name}, 订购: {qty}{state.get('unit','台')}, 生效折扣: {final_disc})...")
    
    # 校验规则：必须带有 'OPP-'
    if not opp_id or not opp_id.startswith("OPP-"):
        error_msg = f"API 校验失败：商机编号 '{opp_id}' 格式非法，必须包含 'OPP-' 前缀。"
        print(f"[Node: CRM API] ❌ {error_msg}")
        return {"crm_error": error_msg}
    
    # 真实数据库库存原子扣减事务 (Dynamic Inventory Deduction)
    new_stock = state.get("current_stock", 0)
    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                # 1. 扣减主商品真实库存 (避免负数，原子更新并返回最新可用库存)
                cur.execute(
                    """
                    UPDATE products 
                    SET stock = GREATEST(0, stock - %s) 
                    WHERE opp_id = %s 
                    RETURNING stock;
                    """,
                    (qty, opp_id)
                )
                row = cur.fetchone()
                if row:
                    new_stock = row[0]
                    print(f"[Node: CRM API] 📦 数据库主商品库存原子扣减成功！商品 [{opp_id}] 扣减 {qty} 件，数据库最新可用库存: {new_stock}")
                
                # 2. 同步扣减赠品配件库存 (若存在对应配件SKU)
                freebies = state.get("freebie_details", [])
                for fb in freebies:
                    fb_name = fb.get("name", "")
                    fb_qty = fb.get("quantity", 0)
                    if fb_name and fb_qty > 0:
                        cur.execute(
                            """
                            UPDATE products
                            SET stock = GREATEST(0, stock - %s)
                            WHERE (%s ILIKE concat('%%', product_name, '%%') OR product_name ILIKE concat('%%', %s, '%%'))
                              AND category_lvl1 IN ('3C配件', '3C外设')
                            RETURNING opp_id, product_name, stock;
                            """,
                            (fb_qty, fb_name, fb_name)
                        )
                        updated_fbs = cur.fetchall()
                        for u_id, u_name, u_stock in updated_fbs:
                            print(f"[Node: CRM API] 🎁 赠品配件 [{u_id}] {u_name} 同步扣减 {fb_qty} 件，数据库最新剩余库存: {u_stock}")
    except Exception as e:
        print(f"[Node: CRM API] ⚠️ 数据库库存扣减执行异常: {e}")

    print(f"[Node: CRM API] ✅ API 提单成功！商品 '{prod_name}' 订单已入库。")
    return {"crm_error": None, "current_stock": new_stock}

def reflection_node(state: AgentState):
    current_retry = state["retry_count"] + 1
    print(f"\n[Node: Reflection] 🔄 启动内环自主纠错 (第 {current_retry} 次重试)...")
    
    prompt = f"""
    你在上一步提取了参数：ID="{state['opportunity_id']}", 折扣={state['discount']}。
    但是后端系统报错了：{state['crm_error']}。
    请阅读原始申请：“{state['sales_input']}”，并结合报错信息，重新输出符合要求的商机编号。
    """
    structured_llm = llm.with_structured_output(ExtractionSchema)
    result = structured_llm.invoke(prompt)
    
    print(f"[Node: Reflection] 💡 纠错完成 -> 新商机ID: {result.opportunity_id}")
    return {
        "opportunity_id": result.opportunity_id,
        "product_name": result.product_name,
        "discount": result.discount,
        "retry_count": current_retry,
        "crm_error": None
    }

def check_crm_result(state: AgentState):
    """根据 CRM 节点结果决定走向"""
    if state.get("crm_error") is None:
        return "success"
    if state["retry_count"] >= 3:
        print("\n[Circuit Breaker] 🚨 重试超过 3 次，触发熔断！")
        return "failed"
    return "retry"

def route_after_parse(state: AgentState):
    """检查是否提取到了合法的商机编号，决定进入风控还是安全终止"""
    opp_id = state.get("opportunity_id")
    if not opp_id:
        print("[Router] 🛑 未能获取有效商机编号，提单流程安全终止（不进入风控）。")
        return "end"
    print(f"[Router] ➡️ 成功锁定商机 [{opp_id}]，流转至风控审核节点")
    return "risk"

# ==================== 构建拓扑图 ====================

builder = StateGraph(AgentState)

builder.add_node("agent", agent_intent_node)
builder.add_node("tools", ToolNode(tools))
builder.add_node("parse_params", parse_params_node)
builder.add_node("risk", risk_node)
builder.add_node("sales_revision", sales_revision_node)
builder.add_node("crm", mock_crm_node)
builder.add_node("reflection", reflection_node)

# 拓扑连线
builder.add_edge(START, "agent")
builder.add_conditional_edges(
    "agent",
    should_call_tools,
    {
        "tools": "tools",
        "parse_params": "parse_params"
    }
)
builder.add_edge("tools", "agent")
builder.add_conditional_edges(
    "parse_params",
    route_after_parse,
    {
        "risk": "risk",
        "end": END
    }
)
builder.add_conditional_edges(
    "risk",
    route_after_risk,
    {
        "crm": "crm",
        "sales_revision": "sales_revision"
    }
)
builder.add_edge("sales_revision", "agent")

# CRM 内环自愈条件路由
builder.add_conditional_edges(
    "crm",
    check_crm_result,
    {
        "success": END,
        "retry": "reflection",
        "failed": END
    }
)
builder.add_edge("reflection", "crm")

# ==================== 端到端验证测试 ====================

DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable")

if __name__ == "__main__":
    import uuid
    thread_id = f"session-tool-{uuid.uuid4().hex[:6]}"
    thread_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10
    }

    print(f"\n{'='*80}")
    print(f"🚀 开始测试智能体自主查库提单闭环 ({thread_id})")
    print(f"{'='*80}")

    with ConnectionPool(conninfo=DB_URI, max_size=10, kwargs={"autocommit": True}) as pool:
        checkpointer = PostgresSaver(pool)
        checkpointer.setup() 
        graph = builder.compile(checkpointer=checkpointer)

        # 核心实战测试用例：销售输入中完全没有商机编号，只有商品名，且折扣 0.8 低于风控红线
        initial_state = {
            "sales_input": "帮我下 500 台远峰蓝苹果18，给客户申请打 8 折",
            "retry_count": 0
        }
        
        print(f"\n[销售提交申请] \"{initial_state['sales_input']}\"")
        graph.invoke(initial_state, config=thread_config)

        # ====== 检查是否命中风控并挂起 ======
        current_state = graph.get_state(thread_config)
        if current_state.next and current_state.tasks and current_state.tasks[0].interrupts:
            interrupt_val = current_state.tasks[0].interrupts[0].value
            print(f"\n[Agent 状态] ⏸️ 任务已成功挂起在风控审批节点！")
            print(f"  • 挂起原因: {interrupt_val['reason']}")
            print(f"  • 匹配到的商品: {interrupt_val['product_name']}")
            print(f"  • 自动解析出的商机ID: {interrupt_val['opp_id']}")
            print(f"  • 申请折扣: {interrupt_val['requested_discount']}")

            # ====== 模拟主管审批通过 ======
            print(f"\n{'='*80}")
            print("👤 (模拟主管在 Agent Inbox 点击同意)")
            human_decision = {
                "approved_discount": 0.85, 
                "comment": "同意，但按底线 8.5 折执行"
            }
            print(f"批准意见: {human_decision['comment']}，最终折扣: {human_decision['approved_discount']}")
            print(f"{'='*80}")
            
            # 恢复执行 (Resume)
            graph.invoke(Command(resume=human_decision), config=thread_config)
            
            # 最终状态校验
            final_state = graph.get_state(thread_config)
            print(f"\n[会话完成] 最终状态: 商机ID={final_state.values.get('opportunity_id')}, 最终折扣={final_state.values.get('final_discount')}")