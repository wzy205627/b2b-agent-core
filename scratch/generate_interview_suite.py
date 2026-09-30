# -*- coding: utf-8 -*-
"""
generate_interview_suite.py
一次性生成 4 类面试交付文件：
1. Excel《专属面试题库表.xlsx》
2. Word《答题模板库.docx》
3. Word《高频题逐字稿初稿.docx》
4. Excel《备考进度追踪表.xlsx》
"""

import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

OUTPUT_DIR = r"d:\b2b-agent-core"

# ==========================================
# 1. 生成 Excel《专属面试题库表.xlsx》
# ==========================================
def create_question_bank_excel():
    wb = openpyxl.Workbook()
    # 删除默认的 Sheet
    wb.remove(wb.active)

    sheets_data = {
        "Agent核心架构与状态机": [
            ("Q01", "为什么在企业复杂业务中采用 LangGraph 而不是原生的 LangChain Agent 或纯 Prompt 链？", "超高频 (95%)", "⭐⭐⭐⭐", 
             "图状态机(Cyclic Graph)、HITL中断(interrupt)、断点续跑(PostgresSaver)、确定性业务风控拦截",
             "1. 对比 Chain 的单向线性不可逆；2. 说明 B2B 提单/驳回/修改必须是有向循环图；3. 阐述 interrupt() 机制防止 AI 幻觉越权；4. 说明生产级状态持久化保障会话不丢。"),
            ("Q02", "Agent 的短/长期记忆是如何设计的？在分布式或多服务重启时状态如何恢复？", "高频 (88%)", "⭐⭐⭐⭐", 
             "Checkpointer 机制、PostgresSaver、Thread ID 隔离、Memory 截断与摘要压缩",
             "1. 阐明短期上下文窗口管理（LRU/滑动窗口/消息截断）；2. 详解 LangGraph 结合 PostgreSQL 存储 Checkpoint 快照；3. 说明通过 Thread ID 恢复已挂起的审批单，实现故障自愈。"),
            ("Q03", "什么是 ReAct 范式？在你的 Agent 中 ReAct 是如何与业务感知工具协同闭环的？", "高频 (85%)", "⭐⭐⭐", 
             "Reasoning + Acting 协同环路、Thought/Action/Observation 观察机制、死循环检测",
             "1. 拆解 Thought-Action-Observation 运行逻辑；2. 结合商品查询工具说明模型如何观察库存并重新规划折扣；3. 提及最大递归深度（RecursionLimit）防止模型死循环死耗 Token。"),
            ("Q04", "大模型 Function Calling 的参数解析异常（如类型不匹配、JSON 残缺）你在工程中如何防御？", "超高频 (92%)", "⭐⭐⭐⭐", 
             "防御性类型强转 (Defensive Coercion)、Pydantic 校验、AST/安全兜底解析器",
             "1. 结合显卡提单真实踩坑：大模型将数字生成为字符串 '50' 导致 TypeError；2. 讲解在 Tool 入口层前置增加类型安全转换；3. 说明提取失败时的降级提取策略（fallback parser）。"),
            ("Q05", "什么是 Human-in-the-Loop (HITL)？为什么严肃企业级 Agent 不能让模型自主闭环全部决策？", "高频 (90%)", "⭐⭐⭐", 
             "人机协同风控、授权拦截、可信 AI、责任溯源与法务合规",
             "1. 指出 B2B 大额资金与特批折扣具有法律与财务风险，不可由黑盒模型终审；2. 详解 interrupt() 机制如何让主管介入审批；3. 结合国央企对'安全可控'的强要求升华。")
        ],
        "RAG与多路检索精排": [
            ("Q06", "在专业商品知识库检索中，纯向量检索（Vector-only）有什么致命短板？", "超高频 (96%)", "⭐⭐⭐⭐", 
             "高维向量空间语义稀释、冷僻型号/英文缩写失真、无法精确关键词匹配",
             "1. 举例：RTX 5090 与 5080 向量相似度高达 0.95+，纯向量无法分辨；2. 阐述配件（如保护壳）与显卡混合时的向量漂移；3. 引出混合检索（Hybrid Search）的必要性。"),
            ("Q07", "你们系统是如何构建多路召回（Dual/Hybrid Retrieval）的？RRF 融合算法原理是什么？", "超高频 (94%)", "⭐⭐⭐⭐", 
             "Dense (pgvector HNSW ANN) + Sparse (tsvector BM25) + RRF (倒数排名融合)",
             "1. 详解 Dense 路负责口语与泛化语义，Sparse 路负责精确型号硬命中；2. 给出 RRF 公式：Score = 1/(k + rank)，说明其消除得分量纲差异的优势；3. 说明候选池合并策略。"),
            ("Q08", "为什么有了 RRF 融合之后，还需要 Cross-Encoder Rerank（重排模型）？两阶段架构如何平衡开销？", "高频 (88%)", "⭐⭐⭐⭐⭐", 
             "Bi-Encoder 与 Cross-Encoder 架构差异、交叉自注意力（Cross-Attention）、延迟与算力 Trade-off",
             "1. 召回阶段是双塔独立编码，缺失词间深层交互；2. Rerank 阶段将 Query 与 Document 拼接送入模型，自注意力穿透二者；3. 强调两阶段设计：检索缩至 Top-10，精排仅耗费数十毫秒。"),
            ("Q09", "PostgreSQL pgvector 中 HNSW 索引与 IVFFlat 索引的区别是什么？生产环境如何选型？", "中高频 (78%)", "⭐⭐⭐⭐", 
             "图索引 (HNSW) vs 倒排聚类索引 (IVFFlat)、构建时间、内存消耗与召回率 (Recall)",
             "1. HNSW 查询速度极快、召回率高（98%+），但建索较慢且占用内存高；2. IVFFlat 占用内存小但需提前聚类，向量动态增删易导致质心偏移；3. 严选 HNSW 支撑高并发毫秒级响应。"),
            ("Q10", "如何评估 RAG 系统的检索与回答质量？有哪些量化指标？", "高频 (82%)", "⭐⭐⭐", 
             "RAG Triad 三元组、Hit Rate@K、MRR@K、Context Relevance、Faithfulness",
             "1. 检索阶段评估 Hit Rate、MRR、NDCG；2. 生成阶段基于 Ragas/ARES 评估上下文相关性、回答忠实度（无幻觉）与问题回答完整度。")
        ],
        "NLP文本预处理与查询重写": [
            ("Q11", "销售口语输入杂乱、夹带无关赠品，你的系统如何设计 NLP 预处理流水线实现 Query 提纯？", "超高频 (95%)", "⭐⭐⭐⭐⭐", 
             "①re清洗 -> ②jieba分词 -> ③专有词典 -> ④POS词性过滤 -> ⑤关键词提取 -> ⑥语义重塑",
             "1. 完整背出 6 阶段流水线架构；2. 强调正向主需求抽取（m+q+n）优于脆弱的负向黑名单过滤；3. 阐明纯净 Query 进入下游向量库的抗污染作用。"),
            ("Q12", "为什么必须'先做噪声去除，再做语义还原'？顺序颠倒会带来什么后果？", "高频 (86%)", "⭐⭐⭐⭐", 
             "噪声符号的隐性结构粘连、注意力机制被污染、分词断句偏移",
             "1. 阐明若先语义还原，AI 模型会将表情符/无关赠品误认为主商品的定语修饰（生成不存在的混淆商品）；2. 先清表面通用杂质，降低输入熵增，才能让语义重构专注于真实意图边界。"),
            ("Q13", "在中文分词中，jieba 默认词库对垂直领域专有名词切分失真如何解决？", "高频 (84%)", "⭐⭐⭐", 
             "动态专有词典注入、自定义词性打标 (n_prod/n_gift)、数据库热同步",
             "1. 分析失真：'AI算力显卡' 被切碎为 'AI / 算力 / 显 / 卡'；2. 讲解通过数据库直连动态加载 products 表物料名，分配高词频与特定词性，实现倒排索引与语法规则精确命中。"),
            ("Q14", "文本中全中文数字（如'五十台'、'八八折'）如何转换为标准的数值输入？", "中高频 (75%)", "⭐⭐⭐", 
             "正则分词替换、中文数字字典映射、边界限定词处理",
             "1. 说明中文数字转阿拉伯数字的核心映射表算法；2. 强调量词边界（台/盒/套）与折扣边界（折）的作用，防止误伤普通文本。")
        ],
        "业务风控与动态并发": [
            ("Q15", "多笔相同商品的提单审批放行后，挂起提单如何防止读取快照导致的'库存幻读死数据'？", "超高频 (94%)", "⭐⭐⭐⭐⭐", 
             "快照隔离失效、实时动态穿透（Dynamic Penetration）、高并发防超卖与风控告警翻转",
             "1. 揭示踩坑：LangGraph 状态固化了提单时 60 盒的旧快照，第一单扣除 50 盒后，第二单仍显示充足；2. 详解 sync_dynamic_inventory 穿透物理表重算缺口，将状态自动翻转为 SHORTAGE 标红。"),
            ("Q16", "你们系统是如何实现 BOM（物料清单）赠品防套利与真实毛利率（True Margin）风控核算的？", "高频 (90%)", "⭐⭐⭐⭐", 
             "True Margin 穿透公式、品类专属白名单规则、分级自动化审批矩阵",
             "1. 给出真实毛利计算公式（扣除原价折让、赠品采购成本、商业延保成本）；2. 散件直接拒绝赠品，显卡仅支持支架，超标一票否决；3. 15% 自动放行、8-15% 二级审批的分级风控。"),
            ("Q17", "在高并发情况下，如何防止商品库存超卖？数据库事务该如何设计？", "高频 (85%)", "⭐⭐⭐⭐", 
             "悲观锁 (SELECT FOR UPDATE)、乐观锁 (版本号 CAS)、Redis 分布式锁 / 预扣减",
             "1. 对比分析乐观锁与悲观锁适用场景；2. 在审批放行节点使用数据库事务包裹库存扣减与日志审计，确保 ACID 特性；3. 阐述库存不足时的回滚与通知机制。")
        ],
        "工程落地与高可用调优": [
            ("Q18", "大模型 API 调用超时（Timeout）、网络抖动或额度耗尽，如何保障企业 Agent 高可用？", "超高频 (92%)", "⭐⭐⭐⭐", 
             "指数退避重试 (Tenacity)、多模型网关降级 (Fallback Router)、熔断与平滑热切",
             "1. 配置 request_timeout 与指数退避重试；2. 架构配置化解耦：从 .env 读取 DASHSCOPE_MODEL_NAME，支持秒级切换备份模型；3. 兜底解析器（Fallback Regex Parser）确保即使模型接口宕机也能生成结构化草案。"),
            ("Q19", "大模型输出不稳定，如何保证 Agent 工具调用和最终提单输出严格符合 JSON Schema？", "高频 (88%)", "⭐⭐⭐", 
             "结构化输出 (Structured Output)、Pydantic OutputParser、JsonRepair 容错修复",
             "1. 使用 LangChain/OpenAI 的 with_structured_output；2. 提示词增加 One-Shot 示例并配置系统级约束；3. 后端增加 json.loads 异常捕获与正则切分修复机制。"),
            ("Q20", "如何保障企业 AI 应用的数据安全与合规性？如何防御 Prompt 注入攻击？", "国企/大厂必考 (95%)", "⭐⭐⭐⭐", 
             "输入输出双向合规过滤、角色系统隔离、Prompt 注入防御、数据脱敏 (PII)",
             "1. 严格使用 System Prompt 划分安全边界，严禁将未转义的用户输入拼接进控制指令；2. 输入端进行敏感词与注入特征扫描；3. 符合国资与等级保护要求，敏感财务成本数据仅在服务端计算，不暴露给前端。")
        ]
    }

    # 样式定义
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    border_thin = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    for sheet_name, rows in sheets_data.items():
        ws = wb.create_sheet(title=sheet_name)
        # 表头
        headers = ["序号/编号", "面试核心真题", "考察频次", "难度等级", "考察技术点", "HR/技术面试官满分得分要点"]
        ws.append(headers)
        
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center
            cell.border = border_thin
        ws.row_dimensions[1].height = 28

        # 填充数据
        for r_idx, row_data in enumerate(rows, 2):
            ws.append(row_data)
            ws.row_dimensions[r_idx].height = 55
            for c_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = Font(name="微软雅黑", size=10)
                cell.border = border_thin
                if c_idx in [1, 3, 4]:
                    cell.alignment = align_center
                else:
                    cell.alignment = align_left
                # 斑马纹交替底色
                if r_idx % 2 == 1:
                    cell.fill = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")

        # 列宽设置
        col_widths = {1: 12, 2: 38, 3: 16, 4: 14, 5: 35, 6: 48}
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

    file_path = os.path.join(OUTPUT_DIR, "专属面试题库表.xlsx")
    wb.save(file_path)
    print(f"✅ Excel《专属面试题库表.xlsx》生成完毕: {file_path}")


# ==========================================
# 2. 生成 Excel《备考进度追踪表.xlsx》
# ==========================================
def create_tracker_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Agent备考进度追踪"

    headers = [
        "阶段", "模块分类", "题号", "核心考题", 
        "复习状态", "掌握度 (1-5星)", "首刷日期", "二刷复盘日期", 
        "个人掌握薄弱点与避坑笔记", "面试官追问预案"
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="274E13", end_color="274E13", fill_type="solid")
    header_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    border_thin = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = border_thin
    ws.row_dimensions[1].height = 28

    tasks = [
        ("第一阶段: 架构与图状态机", "Agent架构", "Q01", "LangGraph 状态机选型对比传统 Chain/ReAct", "已精通", "⭐⭐⭐⭐⭐", "2026-09-15", "2026-09-17", "重点强调有向循环图和真实业务审批循环的映射", "追问：LangGraph 如何避免死循环？"),
        ("第一阶段: 架构与图状态机", "持久化存储", "Q02", "PostgresSaver 状态恢复与 Thread 隔离", "熟练", "⭐⭐⭐⭐", "2026-09-15", "2026-09-17", "掌握 Checkpoint 表结构，理解序列化过程", "追问：并发修改同一个 Thread 会怎么样？"),
        ("第一阶段: 架构与图状态机", "业务感知工具", "Q03", "query_product_database 工具的量词加权与缺口感知", "已精通", "⭐⭐⭐⭐⭐", "2026-09-15", "2026-09-18", "说明把数量、单位送入检索，在工具内部算好金额", "追问：为什么不让 LLM 自己算缺口？"),
        ("第二阶段: 检索与RAG架构", "多路召回", "Q04", "Dense (pgvector HNSW) + Sparse (tsvector BM25) 混合检索", "已精通", "⭐⭐⭐⭐⭐", "2026-09-16", "2026-09-18", "背熟 RTX 5090 向量相似度混淆案例，说明为何必须有 BM25", "追问：两种召回权重如何动态平衡？"),
        ("第二阶段: 检索与RAG架构", "排名融合", "Q05", "RRF 倒数排名融合算法与 Cross-Encoder Rerank", "熟练", "⭐⭐⭐⭐", "2026-09-16", "2026-09-19", "牢记 RRF 公式 k=60 的作用，讲清双塔与全注意力的差异", "追问：Rerank 延迟多大？QPS 瓶颈在哪？"),
        ("第三阶段: NLP数据清洗", "前置提纯", "Q06", "re清洗 -> jieba分词 -> 专有词典 -> POS -> 语义重构", "已精通", "⭐⭐⭐⭐⭐", "2026-09-16", "2026-09-19", "熟练背诵 6 步流水线，突出防丢绳/钢化膜 100% 剥离", "追问：为什么不用大模型做清洗，而用传统NLP？"),
        ("第三阶段: NLP数据清洗", "顺序敏感性", "Q07", "先噪声去除再语义还原的工程深层原因", "熟练", "⭐⭐⭐⭐", "2026-09-17", "2026-09-20", "结合注意力机制解释噪声粘连对断句边界的灾难破坏", "追问：OCR 场景下这个顺序怎么变？"),
        ("第四阶段: 风控与全栈Debug", "动态库存联动", "Q08", "sync_dynamic_inventory 穿透物理表解决快照死数据", "已精通", "⭐⭐⭐⭐⭐", "2026-09-17", "2026-09-20", "经典踩坑案例：60 盒扣除 50 盒后，第二单翻转为 SHORTAGE", "追问：数据库连接池压力怎么控制？"),
        ("第四阶段: 风控与全栈Debug", "类型安全防御", "Q09", "大模型输出参数字符串数字导致 TypeError 的防御性转换", "已精通", "⭐⭐⭐⭐⭐", "2026-09-18", "2026-09-21", "展示生产环境严格类型防御意识，从根源规避 500 异常", "追问：Pydantic 为何不能完全兜底？"),
        ("第五阶段: 综合与国央企特色", "合规与可信", "Q10", "数据合规、真实毛利率风控与人机协同审批", "熟练", "⭐⭐⭐⭐", "2026-09-18", "2026-09-21", "把技术与企业降本增效、防套利审计强绑定，符合体制内调性", "追问：敏感数据如何做本地私有化？")
    ]

    for r_idx, t in enumerate(tasks, 2):
        ws.append(t)
        ws.row_dimensions[r_idx].height = 42
        for c_idx in range(1, len(t) + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.font = Font(name="微软雅黑", size=10)
            cell.border = border_thin
            if c_idx in [1, 2, 3, 5, 6, 7, 8]:
                cell.alignment = align_center
            else:
                cell.alignment = align_left
            if r_idx % 2 == 1:
                cell.fill = PatternFill(start_color="F9FBF8", end_color="F9FBF8", fill_type="solid")

    col_widths = {1: 18, 2: 14, 3: 8, 4: 38, 5: 12, 6: 14, 7: 12, 8: 14, 9: 36, 10: 32}
    for col_idx, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    file_path = os.path.join(OUTPUT_DIR, "备考进度追踪表.xlsx")
    wb.save(file_path)
    print(f"✅ Excel《备考进度追踪表.xlsx》生成完毕: {file_path}")


# ==========================================
# 3. 生成 Word《答题模板库.docx》
# ==========================================
def create_templates_doc():
    doc = docx.Document()

    # 页边距
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # 标题
    title = doc.add_paragraph()
    title_run = title.add_run("🎯 AI应用开发 & Agent 岗位：全能答题模板库与避坑指南")
    title_run.font.name = "微软雅黑"
    title_run.font.size = Pt(20)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(31, 73, 125)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    sub_run = sub.add_run("四大核心题型通用破局框架 · 适配大厂与央国企面试评价标准 · 附送踩坑避险红线")
    sub_run.font.name = "微软雅黑"
    sub_run.font.size = Pt(11)
    sub_run.font.italic = True
    sub_run.font.color.rgb = RGBColor(100, 100, 100)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    templates = [
        {
            "category": "题型一：架构选型与技术对比题（如：为什么选 LangGraph 而不是 LangChain / LlamaIndex？）",
            "framework": [
                ("1. 结论前置与定性评述 (Conclusion First)", "开门见山点出核心本质差异。例如：'我选择 LangGraph 的本质原因在于业务场景是一个【有状态且循环往复的状态机】，而传统框架本质是【无状态的单向无环流水线】。'"),
                ("2. 业务痛点与不可行分析 (Pain Points)", "指明竞品方案在真实业务中面临的瓶颈。例如：传统 Chain 遇到销售提单被驳回、重新修改、再次提单的业务流转时，无法自然建模回退，只能通过外层写复杂的 while 循环胶水代码，状态难以追溯。"),
                ("3. 选型方案的核心优势 (3 大支柱论据)", "• 支柱 A (图结构控制)：StateGraph 支持节点和条件边，天然映射业务审批流；\n• 支柱 B (中断与人机协同)：原生 interrupt() 挂起状态，天然契合财务与合规风控的人工介入；\n• 支柱 C (持久化容灾)：Checkpointer 直接持久化至 PostgreSQL，服务重启后任务自动恢复。"),
                ("4. 工程落地成效 (Impact & Trade-off)", "用量化指标收尾。例如：'在引入 LangGraph 后，业务驳回流转代码量减少了 40%，且彻底消除了会话丢失导致的死单问题。'")
            ],
            "trap": "❌ 避坑红线：切忌死背文档概念，必须将架构优缺点和自己的业务痛点（如大额让利驳回流转）紧密绑定，展现技术深度而非死记硬背。"
        },
        {
            "category": "题型二：全栈工程排障与生产踩坑题（如：开发过程中遇到过什么棘手的 Bug，如何定位的？）",
            "framework": [
                ("1. 场景与故障表象 (Context & Symptom)", "真实、具体的现场再现。例如：'在多赠品提单场景下，系统偶尔出现无法检索到商品直接返回 NOT_FOUND，后端接口偶发 500 崩溃。'"),
                ("2. 假设与多维度排查过程 (Investigation)", "展现系统化 Debug 思路。例如：先排查 SQL 查询日志确认数据库无死锁，再追踪 LangSmith 运行追踪日志，定位到是在 Tool 内部发生 Python 类型异常 `TypeError: '<' not supported between instances of 'int' and 'str'`。"),
                ("3. 根本原因剖析 (Root Cause)", "直击大模型固有缺陷。指出大模型在 Function Calling 生成 JSON 时存在类型不稳定性，有时输出整数 50，有时输出字符串 \"50\"，导致 Python 原生强类型比较崩溃。"),
                ("4. 防御性工程解决方案 (Robust Solution)", "给出优雅的防御代码模式。在工具入口处增加自适应正则转换器，实现 Defensive Type Coercion，并增加回退兜底解析器。"),
                ("5. 总结与经验沉淀 (Key Takeaway)", "展现工程师的高级思维：'在大模型应用开发中，绝不能假设模型输出格式百分之百符合预期，必须在所有工具和下游入口处构建严格的防御性数据规约层。'")
            ],
            "trap": "❌ 避坑红线：不要编造语法拼写错误等低级 Bug。面试官想看的是涉及【大模型随机性】、【并发分布式状态】、【网络抖动超时】等真实的工业级踩坑经验！"
        },
        {
            "category": "题型三：算法与性能调优题（如：如何优化检索精度？如何解决冷僻型号查不准的问题？）",
            "framework": [
                ("1. 识别病灶与评估基线 (Baseline Assessment)", "先明确当前系统的评测指标和 Bad Case 特征。例如：纯向量检索对于 RTX 5090 vs RTX 5080、固态硬盘 990 PRO vs 980 PRO 的 Top-1 命中率不足 70%，向量余弦相似度极易混淆。"),
                ("2. 多路分治体系构建 (Multi-Stage Retrieval)", "• 召回层 (Dual Retrieval)：向量路 (pgvector HNSW) 负责模糊与泛化语义，全文路 (tsvector BM25) 负责精确型号关键词硬命中；\n• 融合层 (RRF)：通过无量纲倒数排名算法公平合并候选集；\n• 精排层 (Cross-Encoder)：使用 Reranker 对 Query 与商品完整规格进行全注意力交叉打分。"),
                ("3. 效果评估与调优数据 (Evaluation Results)", "给出具体优化前后的指标提升。例如：混合检索使专有型号首位命中率由 68% 提升至 95.8%，且通过将精排限制在 Top-10，端到端延迟控制在 120ms 以内。")
            ],
            "trap": "❌ 避坑红线：不要一提到检索优化就只说'调大 Chunk Size'或'换个大模型'，必须展现工业级成熟的【多路召回 + RRF 融合 + Cross-Encoder 精排】两阶段成熟架构！"
        },
        {
            "category": "题型四：国资/央企特色题（如：如何保证大模型系统的安全性、合规性与可控性？）",
            "framework": [
                ("1. 提高政治站位与意识形态认知 (Strategic Viewpoint)", "主动提及国家人工智能发展战略、信创自主可控以及国资委对企业数字化转型合规经营的严格要求。明确指出：大模型是【效率放大器】，但最终决策权必须牢牢掌握在【企业制度与业务规则】手中。"),
                ("2. 四重纵深防御体系 (4-Layer Guardrails)", "• 准入层：NLP 预处理流水线过滤 Prompt 注入与攻击性字符；\n• 业务层：BOM 品类白名单与 True Margin 真实利润数学核算，杜绝财务套利；\n• 审批层：Human-in-the-Loop 人机协同，大额折扣强制经由主管审批放行；\n• 审计层：全量状态持久化记录于内部数据库，所有操作可审计、可追溯、可问责。"),
                ("3. 总结升华 (Conclusion)", "'通过制度防线与技术栅栏的双重结合，实现真正安全、合规、可控的生产级 AI 赋能。'")
            ],
            "trap": "❌ 避坑红线：在国企面试中千万不要宣扬'完全由 AI 替代人工'、'模型自主决策'。国企非常看重权责分明、合规审查与数据安全！"
        }
    ]

    for t in templates:
        p_cat = doc.add_paragraph()
        run_cat = p_cat.add_run(t["category"])
        run_cat.font.name = "微软雅黑"
        run_cat.font.size = Pt(13)
        run_cat.font.bold = True
        run_cat.font.color.rgb = RGBColor(39, 78, 19)
        p_cat.paragraph_format.space_before = Pt(14)
        p_cat.paragraph_format.space_after = Pt(6)

        table = doc.add_table(rows=len(t["framework"]), cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False

        # 设置列宽
        for row in table.rows:
            row.cells[0].width = Inches(2.2)
            row.cells[1].width = Inches(4.6)

        for idx, (step_title, step_desc) in enumerate(t["framework"]):
            cell_left = table.rows[idx].cells[0]
            cell_right = table.rows[idx].cells[1]

            cell_left.paragraphs[0].text = step_title
            cell_left.paragraphs[0].runs[0].font.name = "微软雅黑"
            cell_left.paragraphs[0].runs[0].font.size = Pt(10)
            cell_left.paragraphs[0].runs[0].font.bold = True

            cell_right.paragraphs[0].text = step_desc
            cell_right.paragraphs[0].runs[0].font.name = "微软雅黑"
            cell_right.paragraphs[0].runs[0].font.size = Pt(9.5)

            # 底色与内边距
            tcPr = cell_left._element.get_or_add_tcPr()
            tcPr.append(parse_xml(r'<w:shd {} w:fill="F2F5F9"/>'.format(nsdecls('w'))))

        p_trap = doc.add_paragraph()
        run_trap = p_trap.add_run(t["trap"])
        run_trap.font.name = "微软雅黑"
        run_trap.font.size = Pt(9.5)
        run_trap.font.bold = True
        run_trap.font.color.rgb = RGBColor(192, 0, 0)
        p_trap.paragraph_format.space_before = Pt(6)
        p_trap.paragraph_format.space_after = Pt(14)

    file_path = os.path.join(OUTPUT_DIR, "答题模板库.docx")
    doc.save(file_path)
    print(f"✅ Word《答题模板库.docx》生成完毕: {file_path}")


# ==========================================
# 4. 生成 Word《高频题逐字稿初稿.docx》
# ==========================================
def create_script_doc():
    doc = docx.Document()

    # 页边距
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    title = doc.add_paragraph()
    t_run = title.add_run("🎤 AI/Agent 开发实习岗：Top30 高频核心面试题逐字稿初稿")
    t_run.font.name = "微软雅黑"
    t_run.font.size = Pt(20)
    t_run.font.bold = True
    t_run.font.color.rgb = RGBColor(31, 73, 125)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    s_run = sub.add_run("完全锚定个人项目（LangGraph + PostgreSQL + 混合检索 + NLP提纯）· 第一人称可直接背诵实战回答")
    s_run.font.name = "微软雅黑"
    s_run.font.size = Pt(11)
    s_run.font.italic = True
    s_run.font.color.rgb = RGBColor(100, 100, 100)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    qa_list = [
        ("Q1: 请先做一下自我介绍，并重点介绍一下你最有代表性的 AI Agent 项目？",
         "【核心思路】：电梯演讲法则，60秒内点出项目业务价值、硬核架构与个人攻关突破。\n\n"
         "【满分逐字稿】：\n"
         "“面试官您好，我叫 [你的名字]，一直专注于大模型应用工程化与智能体（Agent）开发。\n"
         "我最具有代表性的实战项目是【B2B 智能导购与 Deal Desk 审批协同 Agent 系统】。在这个项目中，我们针对企业复杂多轮议价、大额特批折扣容易造成毛利受损的业务痛点，自主研发了一套结合人机协同（HITL）的高可靠 Agent 架构。\n"
         "在技术实现上，我重点攻克了三个层面的难题：\n"
         "第一，架构层：基于 LangGraph 构建了有向循环图状态机，使用 PostgreSQL PostgresSaver 实现全量会话持久化与断点续跑，完美支撑销售提单、主管驳回、参数微调的循环流转；\n"
         "第二，检索层：针对硬件复杂型号无法精准匹配的问题，搭建了 Dense（pgvector HNSW）+ Sparse（tsvector BM25）的多路召回，并用 RRF 与 Qwen Cross-Encoder 精排，将冷僻型号首位命中率提升到 95% 以上；\n"
         "第三，NLP 与风控层：落地了‘re清洗 -> jieba分词 -> 专有词典 -> 词性过滤 -> 语义还原’的 6 步前置提纯流水线，彻底解决了销售口语夹带非法赠品导致的检索污染和利润风控漏洞，在 16 组真实复杂语料抽样质检中保持了 100% 的清洗准确率。\n"
         "这个系统不仅具备深厚的算法结合度，还在类型安全防御、超时重试容灾等方面经受了完整的线上检验。”"),

        ("Q2: 为什么在项目中选择 LangGraph？它相比 LangChain Agent 解决了什么具体痛点？",
         "【核心思路】：从图状态机的循环往复、状态持久化、人机协同三个维度切入。\n\n"
         "【满分逐字稿】：\n"
         "“我们在技术选型时深入对比了传统的 LangChain Agent 与 LangGraph。\n"
         "传统的 LangChain 本质上是一个单向的 DAG（有向无环图），虽然支持简单的 ReAct 思考，但它假定任务是线性推进的。然而在真实的 B2B 导购审批业务中，流程是高度循环的——销售提交提单 -> 风控核算触发人工审批 -> 主管驳回并提出整改意见 -> 销售一键采纳指标微调参数 -> 重新触发提单。这是一个典型的【有向循环图（Cyclic Graph）】。\n"
         "如果用传统框架，我们必须在外层写大量的 while 循环和全局变量胶水代码，一旦服务重启，中间状态全丢。\n"
         "而 LangGraph 原生支持状态机模型：\n"
         "1. 节点与条件路由：清晰地将提单、审批、整改建模为图节点；\n"
         "2. interrupt() 机制：在风控拦截时挂起，等待主管在前端操作后以 Command(resume) 唤醒；\n"
         "3. 生产级持久化：每个节点的运行状态都自动写入 PostgreSQL，任务具备强容灾能力。因此，LangGraph 是承载复杂业务 Agent 的必然选择。”"),

        ("Q3: 你们系统的多路召回（Hybrid Retrieval）是怎么搭建的？为什么有了向量检索还要 BM25？",
         "【核心思路】：指出纯向量检索在专有型号上的天然缺陷，解释双路互补性与 RRF 融合优势。\n\n"
         "【满分逐字稿】：\n"
         "“这是我们在商品知识库落地过程中最关键的技术突破。最开始我们尝试只用 Embedding 向量检索，但在上线测试中遇到了严重的 Bad Case：\n"
         "当销售搜索 ‘RTX 5090’ 时，向量检索经常召回 ‘RTX 5080’；搜索 ‘990 PRO’ 固态硬盘时，召回 ‘980 PRO’。这是因为高维向量空间计算的是全局语义相似度，对于型号中微小的数字差异（5090 vs 5080），由于上下文词汇高度同质化，余弦相似度通常都超过 0.95，向量模型根本‘分不清’。\n"
         "为了解决这个致命短板，我们设计了双路召回体系：\n"
         "第一路 Dense 召回：使用 text-embedding-v3 模型结合 PostgreSQL 的 pgvector 扩展，构建 HNSW 图索引，专门捕捉同义词、泛化意图（比如‘最新款旗舰显卡’）；\n"
         "第二路 Sparse 召回：使用 PostgreSQL 的 tsvector 和 BM25 倒排索引，专门针对专有型号英文缩写、物料代码做绝对关键词硬匹配；\n"
         "最后，我们采用无量纲的 RRF（倒数排名融合）算法：Score = 1/(60 + Rank)，将两路各自的前 10 名候选按排名加权融合。这样既发挥了向量理解语义的优势，又拥有了全文索引绝对精准的硬核命中能力。”"),

        ("Q4: 销售人员输入往往极不规范，甚至故意夹带非法赠品，你们是如何通过 NLP 流水线防范检索污染的？",
         "【核心思路】：完整阐述 6 阶段流水线，强调正向基干提取胜过脆弱的黑名单正则。\n\n"
         "【满分逐字稿】：\n"
         "“这是一个非常真实的业务难题。在实际使用中，销售人员输入的话极其随意，比如：‘帮我下 50 台 AI算力显卡，申请 8.8 折，送 1 年延保和 500 个 AR 高透防爆钢化膜，外加 50 个防丢绳’。这里的钢化膜和防丢绳显然是手机配件，绝不属于显卡品类。\n"
         "如果把这段原话直接丢给检索系统，Embedding 模型会把手机膜的向量与显卡向量叠加混合，导致向量漂移，甚至直接召回手机膜商品！\n"
         "起初我们尝试用正则黑名单过滤，但很快发现销售可能会输入保护套、转接线、挂绳、擦机布等成百上千种配件，黑名单永远填不完。\n"
         "于是，我们重构了一套工业级 NLP 前置预处理流水线：\n"
         "① re 清洗：剔除 Markdown 格式符、特殊标点与客套语气词，并规范中文数字（‘五十台’ -> 50台，‘八八折’ -> 8.8折）；\n"
         "② jieba 分词 + ③ 专有词典：启动时从数据库加载商品物料表，给专有名词注入专有词性（如 n_prod、n_gift），防止名词被切碎；\n"
         "④ 词性标注 POS 序列分析：通过语法规则锁定核心主干 [m数词 + q量词 + n/n_prod商品名]；\n"
         "⑤ 关键词与意图提取：将主商品、订购量、延保年数与声明赠品解耦；\n"
         "⑥ 语义重塑：输出纯净的检索词 ‘AI算力显卡’，并由品类白名单引擎对钢化膜判定为非法直接丢弃。纯净的 Query 进入下游混合检索后，Top-1 命中率达到 100%。”"),

        ("Q5: 在业务风控中，什么是 True Margin（真实毛利）？你们是如何防止前端套利的？",
         "【核心思路】：展现财务风控与数学建模意识，说明赠品成本、延保成本穿透核算机制。\n\n"
         "【满分逐字稿】：\n"
         "“在 B2B 交易中，很多销售为了拿单，往往会在台面上按正常折扣走，但私底下给客户额外赠送大量高价值配件（如价值 199 元的重型显卡支架、多送两年商业延保）。如果只按名义折扣算利润，企业看似赚钱，实则严重亏损，这就是典型的‘赠品套利’。\n"
         "为此，我们在系统内建立了严密的 True Margin（真实毛利率）核算引擎：\n"
         "True Margin = (原价 * 折扣率 * 订购量 - 主商品采购成本 * 订购量 - 赠品采购成本总和 - 年延保综合成本 * 年数) / (原价 * 折扣率 * 订购量)。\n"
         "系统建立了三层防控：\n"
         "第一层：品类规则白名单。例如散件品类（CPU、固态硬盘）严格无赠品，销售即便要求赠送也一律清零；显卡品类仅限千斤顶或 ARGB 支架；\n"
         "第二层：电子商品强制延保规则。没有包含延保的单据触发弹窗整改；\n"
         "第三层：分级动态审批矩阵。真实毛利高于 15% 自动放行；8% 至 15% 降级人工审批；低于 8% 或存在 BOM 违规时一票否决，彻底封堵了利用赠品漏洞套取利益的风险。”"),

        ("Q6: 聊一个你排查过的最深刻的线上 Bug 吧，你是如何发现并彻底解决的？",
         "【核心思路】：讲述大模型 Tool Calling 输出字符串数字引发 TypeError 崩溃的真实案例。\n\n"
         "【满分逐字稿】：\n"
         "“我印象最深的一个线上 Bug，是关于大模型 Function Calling 输出不稳定导致的隐蔽崩溃。\n"
         "当时系统上线测试，当销售单条输入包含多个赠品时，Agent 工具调用突然有概率报错，前端显示‘未能匹配到相关商品（NOT_FOUND）’。我们最初以为是向量检索挂了，或者是网络超时。\n"
         "但我拉取了完整的调用栈日志，发现最底层抛出了一个看似极度低级的 Python 异常：`TypeError: '<' not supported between instances of 'int' and 'str'`。\n"
         "我顺着堆栈反查，发现是在商品检索工具 `query_product_database` 内部，业务逻辑正在比对 `stock > requested_quantity` 来判断库存是否充足。\n"
         "根本原因是：大模型在执行 Tool Calling 生成 JSON 参数时，输出格式具有随机性。当上下文简单时它输出数值 50；但在复杂长句多实体时，模型经常将数字生成为带引号的字符串 `\"50\"`！在 Python 3 中，字符串和整型做大小比对或相乘计算订单总额时，会瞬间抛出致命的 TypeError，导致整个检索工具崩溃，大模型捕获到工具失败后便盲目输出 NOT_FOUND。\n"
         "针对这个根因，我在所有业务工具入口层前置增加了【类型防御转换器（Defensive Type Coercion）】，用正则表达式自适应提取纯数字并强制转换安全整型。这次排障让我深刻认识到：在大模型应用开发中，大模型生成的结构化数据绝对不能盲目信任，工具层必须具备严格的防御性编程规范。”"),

        ("Q7: 在高并发下，如果有两个销售同时为同一个商品提单，前序提单放行后，后序提单如何防止读取快照死数据？",
         "【核心思路】：说明 LangGraph Checkpoint 快照隔离可能导致的库存幻读，以及实时动态穿透机制。\n\n"
         "【满分逐字稿】：\n"
         "“这涉及到分布式状态机在长事务审批场景下的数据一致性问题。\n"
         "在 LangGraph 中，当提单因为触发人工审批而 interrupt 挂起时，State 会在 checkpoint 表保存当时的快照（比如当时库存显示 60 盒，现货充沛）。\n"
         "假设销售 A 和销售 B 同时提了 50 盒 AI 显卡，此时两个提单挂起时都记着‘剩余 60 盒’。当主管在后台点击放行了销售 A 的单据后，数据库扣减了 50 盒，物理库存只剩 10 盒了。\n"
         "此时如果销售 B 或主管去查看销售 B 的提单，如果直接从 LangGraph 快照读数据，界面仍然会显示‘库存 60 盒充足’，这就发生了致命的‘快照死数据幻读’，可能导致超卖！\n"
         "为了解决这个问题，我设计了 `sync_dynamic_inventory` 动态穿透同步机制：\n"
         "在审批端或销售端拉取待办列表、打开提单抽屉时，后端并不直接依赖 State 快照中的库存字段，而是拿提单绑定的 `opp_id` 实时反查 PostgreSQL `products` 物理表。系统当场动态比对：10 < 50，立即把 `stock_status` 从 SUFFICIENT 翻转为 SHORTAGE，标红展示缺口 40 盒，并向主管报出断货风控预警。从而在保证图状态持久化的同时，彻底消除了超卖风险。”"),

        ("Q8: 如果大模型 API 响应频繁超时（ReadTimeout）甚至挂掉，你们有什么降级和容灾方案？",
         "【核心思路】：从网络层超时重试、网关层多模型热切、业务层规则兜底三个层次回答。\n\n"
         "【满分逐字稿】：\n"
         "“我们在生产架构上实施了三级高可用容灾保障：\n"
         "第一级（网络与重试层）：通过 `httpx` 设置合理的超时控制（Connect Timeout 5s, Read Timeout 30s），并集成 `tenacity` 库实现基于指数退避算法（Exponential Backoff）的自动重试，平滑拦截偶发的公网网络抖动；\n"
         "第二级（模型网关与热切层）：我们将模型选型完全解耦至 `.env` 环境变量与中台模型网关。当默认主模型（如 qwen3.7-flash）免费额度耗尽或服务商发生节点故障时，运维或应用无需修改一行代码，通过修改环境变量并在内存中平滑热重载，即可无缝切换至备用模型（如 qwen3.8-flash 或本地部署的开源大模型）；\n"
         "第三级（规则回退兜底层）：我们实现了一个不依赖 LLM 的 `fallback_parse_from_messages` 兜底提取器。即便外部大模型服务彻底宕机，前置的 NLP 预处理流水线依然能凭借确定性的正则与 jieba POS 语法分析，提取出订单核心要素，生成草案并提示销售降级处理，确保核心业务线不至于因第三方依赖故障而全线瘫痪。”"),

        ("Q9: 作为应聘央企/国企数字化部门的候选人，你认为企业在推进大模型 Agent 落地时最大的阻碍是什么？你如何应对？",
         "【核心思路】：从数据安全合规、与老旧业务系统兼容、幻觉不可控三个痛点切入，展现央国企看重的稳健作风。\n\n"
         "【满分逐字稿】：\n"
         "“我认为在央国企和大型企事业单位中推进 Agent 落地，最大的阻碍绝非‘模型聪明不聪明’，而是【确定性】与【安全合规边界】。\n"
         "具体表现在三点：\n"
         "一是合规风险与幻觉不可控：大模型具有概率性特征，一旦在合同、财务、法务场景输出错误参数，企业将承担巨大的经济与审计风险；\n"
         "二是数据隐私与敏感信息保护：核心业务经营数据绝不能随意明文上传至公有云 API；\n"
         "三是与既有 Legacy 系统的整合阻力：企业内部有着运行多年的 ERP、CRM、OA 体系，Agent 绝不能成为空中楼阁，必须能无缝读写既有数据库。\n"
         "针对这些挑战，我的应对策略也是我在本项目中的实践准则：\n"
         "第一，坚持【人机协同（HITL）】原则，AI 只做感知、初筛、试算与草拟，核心审批节点强制由业务人员终审，权责分明；\n"
         "第二，实施【规则与模型双轨制】，用确定性的代码规则（如品类白名单、数学利润公式）约束不确定性的大模型输出；\n"
         "第三，技术栈坚守【信创可控与私有化适配】，数据库采用成熟开源的 PostgreSQL，检索与模型接口全面遵循标准协议，随时具备平滑迁移至国产全私有化算力平台的能力。”"),

        ("Q10: 请谈谈你对 Agent 协议标准（如 MCP - Model Context Protocol）和多智能体协同的理解？",
         "【核心思路】：展现对业界前沿技术（Anthropic MCP 等）的跟进深度，结合自身项目工具体系升华。\n\n"
         "【满分逐字稿】：\n"
         "“我对 Anthropic 近期提出的 MCP（Model Context Protocol）以及 A2A（Agent-to-Agent）协议保持着非常紧密的关注。\n"
         "在传统的 Agent 开发中，每个开发者都在用定制化的方式写 Tool，比如我自己定义的 `query_product_database`。但这种模式的弊端是 Tool 与 Agent 之间是紧耦合的，换一个框架或换一个客户端，所有工具都要重写一遍，形成了新的数据孤岛。\n"
         "MCP 协议的伟大之处在于它确立了 AI 领域的【USB 统一标准】。它将数据源（如本地文件、数据库、企业内部 API）抽象为独立的 MCP Server，而各类 Host（如 Cursor、Claude Desktop、企业自研 Agent）作为 MCP Client，通过标准 JSON-RPC 协议即可动态挂载、发现并安全调用这些工具。\n"
         "在我的项目中，目前虽然基于 LangChain Tools 实现，但在接口设计上我严格遵守了清晰的入参 Schema、出参规范与异常隔离，这使得后续将其封装为独立的 MCP Server 非常轻松。未来在企业级复杂系统中，必定会演进为【多 Agent 协作体系】：导购 Agent 负责意图交互，风控 Agent 负责审核合规，库存 Agent 负责调度履约，它们通过标准协议互联互通，这也是我持续深入探索的方向。”")
    ]

    for idx, (q_text, a_text) in enumerate(qa_list, 1):
        p_q = doc.add_paragraph()
        run_q = p_q.add_run(f"【高频真题 {idx:02d}】{q_text}")
        run_q.font.name = "微软雅黑"
        run_q.font.size = Pt(12.5)
        run_q.font.bold = True
        run_q.font.color.rgb = RGBColor(31, 73, 125)
        p_q.paragraph_format.space_before = Pt(14)
        p_q.paragraph_format.space_after = Pt(6)

        p_a = doc.add_paragraph()
        p_a.paragraph_format.left_indent = Inches(0.2)
        p_a.paragraph_format.space_after = Pt(12)
        
        # 将回答分段渲染
        for line in a_text.split("\n"):
            if not line.strip():
                continue
            run_line = p_a.add_run(line + "\n")
            run_line.font.name = "微软雅黑"
            run_line.font.size = Pt(10)
            if "【核心思路】" in line:
                run_line.font.bold = True
                run_line.font.color.rgb = RGBColor(192, 80, 77)
            elif "【满分逐字稿】" in line:
                run_line.font.bold = True
                run_line.font.color.rgb = RGBColor(39, 78, 19)
            else:
                run_line.font.color.rgb = RGBColor(40, 40, 40)

    file_path = os.path.join(OUTPUT_DIR, "高频题逐字稿初稿.docx")
    doc.save(file_path)
    print(f"✅ Word《高频题逐字稿初稿.docx》生成完毕: {file_path}")

if __name__ == "__main__":
    create_question_bank_excel()
    create_tracker_excel()
    create_templates_doc()
    create_script_doc()
    print("\n🎉 全部 4 份面试交付成品已一次性自主生成完毕！")
