import json
import re
from typing import Optional, Any
from langchain_core.tools import tool
from rerank_pipeline import retrieve_and_rerank

@tool
def query_product_database(
    query: str, 
    requested_quantity: Optional[Any] = None, 
    requested_unit: Optional[str] = None
) -> str:
    """
    根据商品名称、特征描述及采购数值约束（意向数量、量词单位）查询企业商品数据库。
    自动结合量词匹配度、现存库存可用性（现货充足还是缺货）以及官方单价进行深度业务核算。
    
    参数:
      - query: 商品名称、型号或搜索关键词（如 '远峰蓝苹果18'、'笔记本'、'i7-14700K'）
      - requested_quantity: 销售申请中的订购数量（如 500），用于核算库存缺口与订单金额
      - requested_unit: 销售申请中使用的量词（如 '台'、'本'、'个'、'箱'、'盒'），用于排查同名混淆
    """
    # 前置 NLP 预处理与查询净化 (如果大模型把一长串原句传给 query，自动剥离杂音提取纯净商品名)
    clean_query = query.strip()
    try:
        from sales_nlp_pipeline import nlp_pipeline
        nlp_res = nlp_pipeline.parse_and_restore(query)
        if nlp_res.get("product_term") and len(nlp_res["product_term"]) >= 2 and nlp_res["product_term"] != "商品":
            clean_query = nlp_res["product_term"]
    except Exception:
        pass

    print(f"\n[Tool Call] 🔍 正在执行业务感知商品检索: '{query}' -> 纯净Query: '{clean_query}' (申请量: {requested_quantity}{requested_unit or ''}) ...")
    results = retrieve_and_rerank(clean_query, top_n=5)
    
    if not results["final_results"]:
        return json.dumps({"status": "not_found", "message": "未在商品库中检索到匹配记录"}, ensure_ascii=False)
    
    # 安全数值转换 (防止大模型将 requested_quantity 生成为字符串 "50" 导致比较崩溃)
    req_qty_int = None
    if requested_quantity is not None:
        try:
            if isinstance(requested_quantity, str):
                m_num = re.search(r'\d+', requested_quantity)
                req_qty_int = int(m_num.group(0)) if m_num else None
            else:
                req_qty_int = int(requested_quantity)
        except Exception:
            req_qty_int = None

    scored_candidates = []
    for item in results["final_results"]:
        opp_id = item["opp_id"]
        product_name = item["product_name"]
        category = item.get("category_lvl1")
        unit = item.get("unit")
        price = float(item.get("price", 0.0))
        cost_price = float(item.get("cost_price", 0.0))
        warranty_cost_per_year = float(item.get("warranty_cost_per_year", 200.0))
        stock = int(item.get("stock", 0))
        base_score = float(item["rerank_score"])
        
        # 1. 量词匹配度软加权 (Unit Alignment)
        unit_match = None
        score = base_score
        if requested_unit:
            if unit == requested_unit:
                unit_match = True
                score += 0.15  # 量词完全精准对齐，大幅加分
            elif requested_unit in ["个", "件", "批"]:
                unit_match = True  # 通用量词，保持中立
            else:
                unit_match = False
                score -= 0.25  # 量词严重冲突（如买'台'电脑却匹配到'本'文具），予以惩罚
                
        # 2. 现存库存可用性核算 (Inventory Calculation)
        if req_qty_int is not None and req_qty_int > 0:
            if stock >= req_qty_int:
                stock_status = "SUFFICIENT"
                shortage_qty = 0
                score += 0.05  # 现货充足优先
            else:
                stock_status = "SHORTAGE"
                shortage_qty = req_qty_int - stock
        else:
            stock_status = "UNKNOWN"
            shortage_qty = 0
            
        final_score = round(max(0.0, min(1.0, score)), 4)
        
        # 保留置信度达标的候选项
        if final_score >= 0.30:
            scored_candidates.append({
                "opportunity_id": opp_id,
                "product_name": product_name,
                "category": category,
                "unit": unit,
                "unit_price": price,
                "cost_price": cost_price,
                "warranty_cost_per_year": warranty_cost_per_year,
                "current_stock": stock,
                "requested_quantity": req_qty_int or 1,
                "requested_unit": requested_unit,
                "stock_status": stock_status,
                "shortage_qty": shortage_qty,
                "estimated_total_amount": round(price * (req_qty_int or 1), 2),
                "confidence_score": final_score
            })
            
    # 按综合得分降序排列
    scored_candidates.sort(key=lambda x: x["confidence_score"], reverse=True)
    
    if not scored_candidates:
        return json.dumps({
            "status": "low_confidence",
            "message": "商品库中无高相关性匹配项"
        }, ensure_ascii=False)
        
    print(f"[Tool Call] ✅ 查库成功，返回 Top-{len(scored_candidates[:3])} 业务感知候选:")
    for c in scored_candidates[:3]:
        stock_tip = f"现货充足 ({c['current_stock']}{c['unit']})" if c['stock_status'] == 'SUFFICIENT' else f"⚠️缺货 (仅剩{c['current_stock']} 缺口{c['shortage_qty']})"
        print(f"  • [{c['opportunity_id']}] {c['product_name']} | 单价:¥{c['unit_price']} | 库存:{stock_tip} | 得分:{c['confidence_score']}")
        
    return json.dumps({
        "status": "success",
        "candidates": scored_candidates[:3]
    }, ensure_ascii=False)
