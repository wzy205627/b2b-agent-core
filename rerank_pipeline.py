import os
import sys
from dotenv import load_dotenv
import dashscope
from dual_retrieval import search_dual

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    raise ValueError("DASHSCOPE_API_KEY 未配置，请检查 .env 文件！")
dashscope.api_key = DASHSCOPE_API_KEY


def compute_rrf(dense_hits: list[dict], sparse_hits: list[dict], k: int = 60, top_k: int = 5) -> list[dict]:
    """
    RRF (Reciprocal Rank Fusion 倒数排名融合算法)
    公式: RRF_Score(d) = sum( 1 / (k + rank_m(d)) )
    
    参数:
      - dense_hits: ANN 稠密向量召回榜单 (包含 intra-list rank: 1, 2, 3...)
      - sparse_hits: BM25 稀疏关键字召回榜单 (包含 intra-list rank: 1, 2, 3...)
      - k: 工业级平滑常数 (默认 60)
      - top_k: 融合后输出给 Rerank 模型的候选集大小
    """
    doc_map = {}

    # 1. 累计 Dense 榜单得分
    for item in dense_hits:
        opp_id = item["opp_id"]
        rank = item["rank"]
        rrf_contrib = 1.0 / (k + rank)
        doc_map[opp_id] = {
            "opp_id": opp_id,
            "product_name": item["product_name"],
            "category_lvl1": item.get("category_lvl1"),
            "unit": item.get("unit"),
            "price": item.get("price", 0.0),
            "cost_price": item.get("cost_price", 0.0),
            "warranty_cost_per_year": item.get("warranty_cost_per_year", 200.0),
            "stock": item.get("stock", 0),
            "dense_rank": rank,
            "dense_score": item["score"],
            "sparse_rank": None,
            "sparse_score": None,
            "rrf_score": rrf_contrib
        }

    # 2. 累计 Sparse 榜单得分
    for item in sparse_hits:
        opp_id = item["opp_id"]
        rank = item["rank"]
        rrf_contrib = 1.0 / (k + rank)
        if opp_id in doc_map:
            doc_map[opp_id]["sparse_rank"] = rank
            doc_map[opp_id]["sparse_score"] = item["score"]
            doc_map[opp_id]["rrf_score"] += rrf_contrib
        else:
            doc_map[opp_id] = {
                "opp_id": opp_id,
                "product_name": item["product_name"],
                "category_lvl1": item.get("category_lvl1"),
                "unit": item.get("unit"),
                "price": item.get("price", 0.0),
                "cost_price": item.get("cost_price", 0.0),
                "warranty_cost_per_year": item.get("warranty_cost_per_year", 200.0),
                "stock": item.get("stock", 0),
                "dense_rank": None,
                "dense_score": None,
                "sparse_rank": rank,
                "sparse_score": item["score"],
                "rrf_score": rrf_contrib
            }

    # 3. 按 RRF 融合总分降序排列
    sorted_docs = sorted(doc_map.values(), key=lambda x: x["rrf_score"], reverse=True)
    for i, doc in enumerate(sorted_docs, start=1):
        doc["rrf_rank"] = i
        doc["rrf_score"] = round(doc["rrf_score"], 6)

    return sorted_docs[:top_k]


def rerank_candidates(query: str, candidates: list[dict], top_n: int = 3) -> list[dict]:
    """
    调用通义千问交叉编码器 qwen3.7-text-rerank 对候选集进行终审精排
    计算 Query 与每个 Document 之间的深度全注意力跨编码相关性得分
    使用结构化上下文注入（类目、单位、单价、库存），极大提升对量词和同名商品的辨识能力
    """
    if not candidates:
        return []

    doc_texts = [
        f"商品: {c['product_name']} | 类目: {c.get('category_lvl1', '')} | 计量单位: {c.get('unit', '')} | 单价: ¥{c.get('price', 0)} | 现货库存: {c.get('stock', 0)}{c.get('unit', '')}"
        for c in candidates
    ]
    
    resp = dashscope.TextReRank.call(
        model="qwen3.7-text-rerank",
        query=query,
        documents=doc_texts,
        top_n=top_n,
        return_documents=False
    )
    
    if resp.status_code != 200:
        raise RuntimeError(f"百炼 Rerank API 调用失败 [Code {resp.status_code}]: {resp.message}")

    results = resp.output["results"]
    reranked_list = []
    
    for final_rank, item in enumerate(results, start=1):
        original_idx = item["index"]
        relevance_score = round(float(item["relevance_score"]), 4)
        
        doc = dict(candidates[original_idx])
        doc["final_rank"] = final_rank
        doc["rerank_score"] = relevance_score
        reranked_list.append(doc)
        
    return reranked_list


def retrieve_and_rerank(query: str, top_n: int = 3) -> dict:
    """
    端到端企业级检索流水线：
    自然语言 Query -> 双路粗排 (ANN + BM25) -> RRF 融合 -> qwen3.7-text-rerank 精排
    """
    # 1. 双路并行粗排 (单 SQL CTE)
    dual_res = search_dual(query, limit=5)
    
    # 2. RRF 倒数排名融合
    rrf_candidates = compute_rrf(dual_res["dense_hits"], dual_res["sparse_hits"], k=60, top_k=5)
    
    # 3. 交叉编码器精排
    final_results = rerank_candidates(query, rrf_candidates, top_n=top_n)
    
    return {
        "query": query,
        "dense_hits": dual_res["dense_hits"],
        "sparse_hits": dual_res["sparse_hits"],
        "rrf_candidates": rrf_candidates,
        "final_results": final_results
    }


def run_pipeline_demo():
    """演示全链路渐进式演变：Dense -> Sparse -> RRF -> Rerank 决胜局"""
    test_queries = [
        ("决胜测试 1A [意图明确搜手机]", "我想买部苹果18手机 远峰蓝"),
        ("决胜测试 1B [未带手机二字模糊搜]", "苹果18 远峰蓝"),
        ("决胜测试 2 [纯黑话意图对齐]", "想要一款安全的政企商务手机"),
        ("决胜测试 3 [型号精准命中与重排]", "48口 PoE 企业交换机")
    ]
    
    print("\n" + "="*90)
    print("🏆 开始执行企业级【双路召回 + RRF 融合 + Cross-Encoder Rerank】全链路流水线测试")
    print("="*90)

    for label, q in test_queries:
        print(f"\n🌟 【{label}】 搜索词: \"{q}\"")
        output = retrieve_and_rerank(q, top_n=3)
        
        # 阶段 1 & 2: 双路召回原始结果
        print("\n  [阶段 1: Dense 稠密向量粗排 Top-3]")
        for d in output["dense_hits"][:3]:
            print(f"    • Rank {d['rank']}: [{d['opp_id']}] {d['product_name']} (余弦相似度: {d['score']})")
            
        print("  [阶段 2: Sparse 稀疏关键字粗排 Top-3]")
        if output["sparse_hits"]:
            for s in output["sparse_hits"][:3]:
                print(f"    • Rank {s['rank']}: [{s['opp_id']}] {s['product_name']} (ts_rank: {s['score']})")
        else:
            print("    • (无字面词项命中)")
            
        # 阶段 3: RRF 融合后候选池
        print("  [阶段 3: RRF 倒数排名融合候选池 Top-5 (公式: 1/(60+rank))]")
        for c in output["rrf_candidates"]:
            print(f"    • RRF-Rank {c['rrf_rank']}: [{c['opp_id']}] {c['product_name']} "
                  f"[RRF分: {c['rrf_score']} | Dense-Rank: {c['dense_rank']} | Sparse-Rank: {c['sparse_rank']}]")
            
        # 阶段 4: Rerank 终审冠军榜单
        print("  🔥 [阶段 4: qwen3.7-text-rerank 终审精排榜单 Top-3]")
        for f in output["final_results"]:
            print(f"    ⭐ Final Rank {f['final_rank']}: [{f['opp_id']}] {f['product_name']} "
                  f"(Rerank置信度得分: {f['rerank_score']})")
            
        print("-" * 90)


if __name__ == "__main__":
    run_pipeline_demo()
