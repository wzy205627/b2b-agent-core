# 🎯 B2B 智能导购与审批 Agent 开发：大厂面试题库与高分破局指南

> 本题库深度结合我们当前的真实企业级落地项目——**基于 LangGraph、PostgreSQL (pgvector + tsvector)、多路召回/混合精排、工业级 NLP 预处理流水线及人机协同（HITL）的 B2B 智能导购与 Deal Desk 审批协同系统**。
> 涵盖了面试 **AI 应用开发 / Agent 开发 / 大模型算法实习生** 时，面试官最喜欢深挖的 **架构设计、混合检索、图状态机、业务防风控、线上故障排查（含真实踩坑案例）** 等高频核心考点，助你在技术面试中展现远超一般实习生的工程落地能力！

--
## 目录
- [第一模块：Agent 核心架构与状态机控制（LangGraph / HITL）](#第一模块agent-核心架构与状态机控制langgraph--hitl)
- [第二模块：NLP 预处理流水线与查询重写（Query Understanding）](#第二模块nlp-预处理流水线与查询重写query-understanding)
- [第三模块：企业级多路召回与混合精排（RAG / Search / Rerank）](#第三模块企业级多路召回与混合精排rag--search--rerank)
- [第四模块：业务风控、动态库存与人机协同审批（Business Logic & Deal Desk）](#第四模块业务风控动态库存与人机协同审批business-logic--deal-desk)
- [第五模块：生产级高可用、踩坑实录与性能调优（线上 Debug 杀手锏）](#第五模块生产级高可用踩坑实录与性能调优线上-debug-杀手锏)
- [第六模块：HR/综合面通用答题策略与个人项目亮点陈述模板](#第六模块hr综合面通用答题策略与个人项目亮点陈述模板)

---

## 第一模块：Agent 核心架构与状态机控制（LangGraph / HITL）

### Q1：为什么在企业级复杂业务中选择 LangGraph，而不是原生的 LangChain Agent 或纯 Prompt 流水线？
- **考点**：状态可控性、循环决策（Cycles）、人机协同（Human-in-the-loop）与企业级确定性。
- **高分回答要点**：
  1. **状态机与有向图（Graph State）**：原生 LangChain 链式调用（Chain）只能顺序执行，而现实业务中销售提单、驳回、修改、再提单是典型的**循环往复图结构（Cyclic Graph）**。LangGraph 允许定义节点（Nodes）与条件路由边（Conditional Edges），严格按业务状态机流转。
  2. **断点持久化与人机协同（HITL Interrupt）**：B2B 大额交易涉及高额让利，AI 绝对不能自主拍板放行。LangGraph 原生支持 `interrupt()` 挂起，把中间状态通过 Checkpointer（如 PostgresSaver）无缝固化到数据库；等待主管审批放行或驳回后，再以 `Command(resume=...)` 唤醒图继续往下走，状态天然保真。
  3. **确定性规约与容错（Guardrails）**：原生 Agent 容易出现死循环或参数幻觉。LangGraph 可以为节点配置独立的校验拦截（如 `freebie_rules`、`preflight_check`），一旦大模型输出非法参数或超纲要求，可由确定性节点强行纠偏，而不是任由大模型自由发散。

---

### Q2：在你的系统中，Checkpointer（状态持久化）是如何实现的？如果服务崩溃，正在审批的任务如何恢复？
- **考点**：分布式会话保持、PostgresSaver 机制、Thread ID 事务隔离。
- **高分回答要点**：
  1. **存储介质**：放弃了玩具级的内存 `MemorySaver`，采用生产级 PostgreSQL 数据库的 `PostgresSaver`，结合连接池 `psycopg_pool.ConnectionPool`。
  2. **快照机制**：LangGraph 在每个节点执行完毕及触发 `interrupt` 时，都会将当前全量 `DealDeskState` 序列化写入 `checkpoint` 表，生成唯一的快照版本。
  3. **任务恢复**：所有提单均绑定唯一 `thread_id`（如 `TH-202609-0001`）。当后端服务重启或节点故障恢复后，销售或主管只需请求该 `thread_id`，Agent 就能直接从 PostgreSQL 中反序列化出挂起时的精确上下文，无缝恢复执行，没有任何状态丢失。

---

### Q3：谈谈什么是“业务感知工具（Business-Aware Tool Calling）”？它与普通的 API/DB Tool 有什么区别？
- **考点**：工具设计的业务厚度、多重参数联动计算。
- **高分回答要点**：
  - 普通的查询工具（Naive Tool）通常只做简单的 `SELECT * FROM products WHERE name LIKE ...`，把所有数据扔回给 LLM。
  - **业务感知工具（以我们的 `query_product_database` 为例）**：
    - **参数联动**：不仅接收商品名 `query`，还同时接收意向订购数量 `requested_quantity` 和量词单位 `requested_unit`；
    - **量词软加权（Unit Alignment）**：比对销售原话中的量词（如“盒”、“台”、“片”）与物理 SKU 规格单位，精准识别同名不同规格的物料，给匹配项动态加权；
    - **动态缺口测算**：在工具内部直接对比实时库存，计算出 `stock_status`（SUFFICIENT / SHORTAGE）及具体的缺口数量 `shortage_qty`；
    - **预估货值与风控前置**：直接在 Tool 中输出官方批复单价和订单预估金额，大幅减轻大模型的数值计算负担，杜绝算术幻觉。

---

## 第二模块：NLP 预处理流水线与查询重写（Query Understanding）

### Q4：销售人员在自然语言输入时往往极其随意（如“帮我下 50 台 AI算力显卡，送 1 年延保和 500 个 AR 高透防爆膜”），你的系统是如何防止非法配件污染检索的？
- **考点**：Query 净化、NLP 预处理流水线、企业级专有分词。
- **高分回答要点**：
  - **核心痛点**：销售误把手机钢化膜当显卡赠品，若直接输入向量检索，Embedding 向量会在“手机膜”与“显卡”中间漂移，导致召回错误商品。
  - **工业级流水线架构**：
    1. **① re 清洗**：正则去除 Markdown 乱码、格式符号、无意义口癖助词（如“帮我看下”、“紧急采购”），并规范中文数字（如“五十台” $\rightarrow$ `50台`，“八八折” $\rightarrow$ `8.8折`）；
    2. **② jieba 精确分词 + ③ 专有词典**：从 PostgreSQL 商品库动态加载 SKU 专有词典（如 `AI算力显卡`、`ROG 铝合金 ARGB 发光重型显卡支架`），防止专有名词被切碎；
    3. **④ 词性标注与语法序列过滤（POS）**：基于 `[m(数词)] + [q(量词)] + [n/n_prod(商品名)]` 的语法规则，正向锁定核心订购商品实体；
    4. **⑤ 意图解耦与 ⑥ 语义还原**：把商品实体、订购数量、折扣、延保、申请赠品拆分为独立结构化字段，重构出纯净无杂质的基干 Query（如仅保留 `AI算力显卡`）送入下游检索；对于不属于显卡品类的“钢化膜/防丢绳”，品类规则库直接阻断并清零。

---

### Q5：为什么必须“先做噪声去除，再做语义还原”，顺序反过来会有什么后果？
- **考点**：NLP 数据清洗顺序敏感性、LLM 注意力干扰机制。
- **高分回答要点**：
  1. **噪声具有“结构粘连”破坏性**：若先做语义还原，非结构化文本中的表情符号、网页标签、无关配件（如“和50个防丢绳”）会被 AI 模型强行当做主商品的修饰成分，导致模型断句错误，误把“防丢绳”融合进商品主体，生成“带防丢绳的AI算力显卡”这类不存在的实体。
  2. **先清表层，后辨深层**：先通过规则与正则剥离表层的语法杂质、标点堆叠与客套废话，降低输入熵增；让后续的分词器和语义重构模型只专注于语义层面的句法关系和结构边界重建，准确率才能达到 100%。

---

## 第三模块：企业级多路召回与混合精排（RAG / Search / Rerank）

### Q6：在商品库检索中，纯向量检索（Vector-only）有什么致命短板？你们是如何设计多路召回的？
- **考点**：Dense vs Sparse、冷僻型号精准匹配、pgvector + tsvector 混合检索。
- **高分回答要点**：
  1. **纯向量检索短板**：
     - 对**专有型号/英文缩写**极度不敏感（例如：`RTX 5090` vs `RTX 5080`、`990 PRO` vs `980 PRO` 在高维向量空间极其接近，余弦相似度可能高达 0.96，导致张冠李戴）；
     - 无法做到**绝对关键字完全匹配（Exact Match）**。
  2. **双路/多路召回设计**：
     - **稠密向量路（Dense）**：基于 `text-embedding-v3` + PostgreSQL `pgvector`（采用 **HNSW ANN 索引**），捕捉同义词、泛化意图与口语化描述（如“苹果最新款手机”召回“苹果18”）；
     - **稀疏全文路（Sparse）**：基于 PostgreSQL `tsvector`（采用 **BM25 倒排索引**），专攻硬核型号、SKU 编号、参数规格的精准命中；
  3. **倒数排名融合（RRF）**：使用无量纲的倒数排名加权公式：
     $$RRF\_Score(d) = \sum_{m \in \{Dense, Sparse\}} \frac{1}{k + rank_m(d)} \quad (k=60)$$
     将两路召回结果公平合并，兼具泛化语义与专有型号硬命中的优势。

---

### Q7：RRF 融合之后为什么还需要 Cross-Encoder Rerank（重排模型）？它的核心计算开销和收益是什么？
- **考点**：Bi-Encoder vs Cross-Encoder、注意力交叉交互、计算复杂度与精度平衡。
- **高分回答要点**：
  1. **原理差异**：
     - 召回阶段（Bi-Encoder）：Query 与 Document 独立编码为向量，计算的是空间夹角，缺乏词与词之间的交叉注意力交互；
     - 重排阶段（Cross-Encoder，如 `qwen3.7-text-rerank`）：将 `[Query, Document]` 拼接后一起送入模型，自注意力机制（Self-Attention）贯穿二者所有 Token，能精确识别条件状语、否定词和微小参数差异。
  2. **工程权衡**：
     - **开销控制**：Cross-Encoder 计算复杂度高，不能用于数万商品的全库扫描；因此采用**两阶段架构（Two-Stage）**：多路召回快速把候选集缩窄到 Top-10，Reranker 只对这 10 个候选做深度评分，将端到端延迟控制在几十毫秒级，精度与性能完美兼顾。

---

## 第四模块：业务风控、动态库存与人机协同审批（Business Logic & Deal Desk）

### Q8：如果销售提交了多笔相同商品的提单，主管先放行了第一笔提单，后续挂起提单的库存如何保证不出现“幻读死数据”？
- **考点**：快照隔离陷阱、实时动态数据穿透、高并发库存防超卖。
- **高分回答要点**：
  - **真实踩坑**：LangGraph 在挂起提单时，State 中存储了当时的商品快照（如库存 60 盒）。主管放行 #A0008 扣减 50 盒后，#A0009 若仍直接读取 Checkpoint 快照，依然显示 60 盒充足，导致风控失效！
  - **工业级解决方案（动态穿透同步）**：
    - 设计 `sync_dynamic_inventory` 联动机制。当前端拉取待办列表（`GET /api/pending-tasks`）或打开抽屉时，系统以当前物料 `opp_id` 实时反查 PostgreSQL `products` 物理表；
    - 动态比对最新物理可用库存，当场重算 `current_stock`、`shortage_qty` 和 `stock_status`（若 60 - 50 = 10 < 50，立即自动将状态翻转为 `SHORTAGE`，标红缺口 40 盒）；
    - 确保审批人视角看到的永远是**物理事实库存**，杜绝审批超卖风险。

---

### Q9：你们系统是如何实现 BOM（物料清单）赠品合规防套利风控的？
- **考点**：真实毛利率核算（True Margin）、赠品成本穿透、品类规则引擎。
- **高分回答要点**：
  1. **品类专属规则与白名单**：
     - 显卡品类（GPU）：仅允许附赠千斤顶/ARGB 发光显卡支架，且强制要求 1 年以上延保；
     - 散件硬件（DIY CPU/固态硬盘）：严格无赠品（none），任何索要赠品均直接无视，成本清零；
     - 手机品类：支持多种赠品（手机壳、钢化膜）供销售按需选择。
  2. **真实毛利（True Margin）核算公式**：
     $$\text{真实利润} = (\text{原价} \times \text{折让比例} \times \text{数量}) - (\text{主商品采购成本} \times \text{数量}) - \text{赠品采购成本总和} - (\text{年延保成本} \times \text{年数})$$
  3. **分级动态审批矩阵**：
     - 若 `True Margin >= 15%`：系统自动放行（Auto-Pass）；
     - 若 `8% <= True Margin < 15%`：降级为人工二级审批；
     - 若 `True Margin < 8%` 或发生 `BOM 违规/库存严重缺货`：一票否决（Reject）或强制整改退回。

---

## 第五模块：生产级高可用、踩坑实录与性能调优（线上 Debug 杀手锏）

> 💡 **面试秘籍**：面试官最爱听你在真实开发中遇到了什么诡异 Bug、如何定位并如何解决的。以下三个案例均来自我们项目的真实实战，讲出来极具说服力！

### 案例 1：大模型 Tool Calling 的“字符串数字类型陷阱（TypeError）”
- **现象**：当提单包含多个赠品时，Agent 工具调用突然崩溃，报错 `TypeError: '<' not supported between instances of 'int' and 'str'`，导致整单提单检索失败（显示商品 NOT_FOUND）。
- **根因**：OpenAI / DashScope 等模型在生成 JSON 参数时，具有随机性，有时输出 `{"requested_quantity": 50}`，有时却输出为字符串 `{"requested_quantity": "50"}`。后端的 Python 业务逻辑在做 `requested_quantity > stock` 比较或计算总金额 `price * requested_quantity` 时，直接触发类型异常崩溃！
- **破局方案**：在工具入口处实现**类型防御转换器（Defensive Type Coercion）**：
  ```python
  if requested_quantity is not None:
      if isinstance(requested_quantity, str):
          m = re.search(r'\d+', requested_quantity)
          req_qty_int = int(m.group(0)) if m else None
      else:
          req_qty_int = int(requested_quantity)
  ```
  彻底杜绝了因大模型类型不稳定引发的生产事故。

---

### 案例 2：模型 API 频繁超时（OpenAITimeoutError）与 Token 额度耗尽平滑迁移
- **现象**：高并发或多轮图递归时，DashScope 接口响应超时（`httpx.ReadTimeout`），导致整个提单接口 500。
- **根因**：使用了默认的单模型单端点，未设置请求超时重试机制，且免费/商用模型额度耗尽时无降级预案。
- **破局方案**：
  1. **配置级解耦**：将模型名、API Key 和 Base URL 全面收拢至 `.env`，消除硬编码；
  2. **重试机制与超时控制**：通过 `request_timeout=30.0` 与 tenacity 指数退避重试，拦截偶发网络抖动；
  3. **平滑模型热替换**：构建对统一 OpenAI API 规范的适配层，实现 `qwen3.7-flash` 到 `qwen3.8-flash` 等模型的零代码无缝热切。

---

### 案例 3：前端“一键采纳指标”点击后数值不变（装饰性按钮排查）
- **现象**：销售在提单被主管驳回后，点击“一键按主管整改指标采纳并生成申请”绿色按钮，微调测算栏里的滑块和数字完全没有变动。
- **根因**：
  - 主管驳回时写入的指示文本（如“建议将折扣回调至9.2折，数量调整为60台”）采用了中文自然语言描述；
  - 前端原有的解析函数仅匹配了固定英文字段，无法有效提取中文句式中的量化指标，导致赋值 `NaN` 或回退到旧值。
- **破局方案**：在前端重构正则自适应抽取器 `extractTargetsFromInstructions`，兼容量词、百分比、折数及空格，提取出有效数值后同步更新 React State，并实时联动微调测算器，实现提单的闭环修改。

---

## 第六模块：HR/综合面通用答题策略与个人项目亮点陈述模板

### 💡 60 秒自我介绍 / 项目亮点“电梯演讲（Elevator Pitch）”模板：

> “面试官您好，我重点负责落地过一个**基于 LangGraph 与多路检索的企业级 B2B 智能导购与审批协同 Agent 系统**。
> 
> 在这个项目中，我主要解决了三个核心工程难题：
> 1. **架构层面**：放弃了玩具级的一刀切 Chain，使用 **LangGraph 构建了具备人机协同（HITL）与 PostgreSQL 持久化状态机**，实现了大额提单的主管断点审批、整改循环流转与实时库存防超卖联动；
> 2. **算法检索层面**：针对专有硬件型号与复杂配件，搭建了 **Embedding 稠密向量（pgvector HNSW）+ tsvector（BM25 倒排）的多路召回**，并结合 **RRF 算法与 Qwen Cross-Encoder 混合精排**，解决了纯向量检索对冷僻型号不敏感的顽疾；
> 3. **NLP 与数据治理层面**：落地了 **‘re清洗 $\rightarrow$ jieba分词 $\rightarrow$ 专有词典 $\rightarrow$ POS语法过滤 $\rightarrow$ 语义还原’ 的前置预处理流水线**，不仅将口语化提单中的错报、非法配件完全剥离，保护了公司的真实毛利率，抽样质检准确率达到 100%。”

---

## 收藏与复习建议
1. 面试前重点背诵 **Q1（LangGraph 价值）**、**Q4（NLP 流水线）**、**Q6（混合检索架构）**；
2. 被问到“遇到过什么难点”时，直接上 **第五模块的 3 个生产踩坑实录**，瞬间拉开与其他只写 Demo 的同学的差距！
