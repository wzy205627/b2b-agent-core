import os
import sys
import psycopg
from dotenv import load_dotenv
import dashscope
from pgvector.psycopg import register_vector

load_dotenv()

DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

if not DASHSCOPE_API_KEY:
    raise ValueError("DASHSCOPE_API_KEY 未配置，请检查 .env 文件！")
dashscope.api_key = DASHSCOPE_API_KEY


def embed_query(query: str) -> list[float]:
    """调用通义千问 qwen3.7-text-embedding-flash 生成用户搜索词的 1024 维向量"""
    resp = dashscope.TextEmbedding.call(
        model="qwen3.7-text-embedding-flash",
        input=query
    )
    if resp.status_code != 200:
        raise RuntimeError(f"百炼 Embedding API 错误 [Code {resp.status_code}]: {resp.message}")
    return resp.output["embeddings"][0]["embedding"]


def search_dense(query: str, limit: int = 5) -> list[dict]:
    """
    第一路：ANN 稠密向量召回
    利用 HNSW 索引与余弦距离 <=>，寻找语义最接近的商品（擅长模糊意图、近义词、容错）
    """
    query_vec = embed_query(query)
    vec_str = str(query_vec)
    sql = """
        SELECT 
            id, 
            opp_id, 
            product_name,
            category_lvl1,
            unit,
            price,
            cost_price,
            warranty_cost_per_year,
            stock,
            1 - (embedding <=> %s::vector) AS dense_score,
            ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS rank
        FROM products
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (vec_str, vec_str, vec_str, limit))
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "opp_id": r[1],
                    "product_name": r[2],
                    "category_lvl1": r[3],
                    "unit": r[4],
                    "price": float(r[5]) if r[5] is not None else 0.0,
                    "cost_price": float(r[6]) if r[6] is not None else 0.0,
                    "warranty_cost_per_year": float(r[7]) if r[7] is not None else 200.0,
                    "stock": int(r[8]) if r[8] is not None else 0,
                    "score": round(float(r[9]), 4),
                    "rank": r[10],
                    "source": "dense"
                }
                for r in rows
            ]


def build_tsquery(query: str) -> str:
    """
    智能构建 PostgreSQL 稀疏查询：
    1. 提取有效词项（按空格及中英文标点切分）
    2. 使用 '|' (OR 模式) 与 ':*' (前缀通配符)，使匹配多词项的商品获得更高 ts_rank 分数
    例如：'苹果18 远峰蓝' -> '苹果18':* | '远峰蓝':*
    """
    clean_q = query
    for ch in [',', '，', '。', '！', '!', '？', '?', '、', '/', '\\', '-', '_', '(', ')', '（', '）']:
        clean_q = clean_q.replace(ch, ' ')
    tokens = [t.strip() for t in clean_q.split() if t.strip()]
    if not tokens:
        return ""
    # 去除可能破坏 tsquery 语法的单引号
    safe_tokens = [t.replace("'", "") for t in tokens if t.replace("'", "")]
    if not safe_tokens:
        return ""
    return " | ".join(f"'{t}':*" for t in safe_tokens)


def search_sparse(query: str, limit: int = 5) -> list[dict]:
    """
    第二路：BM25 稀疏关键字召回
    利用 GIN 倒排索引与 ts_rank 全文打分，寻找精确词根命中的商品（擅长精准货号、参数、品牌代码）
    """
    tsquery_str = build_tsquery(query)
    if not tsquery_str:
        return []

    sql = """
        SELECT 
            id, 
            opp_id, 
            product_name, 
            ts_rank(search_vector, to_tsquery('simple', %s)) AS sparse_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(search_vector, to_tsquery('simple', %s)) DESC) AS rank
        FROM products
        WHERE search_vector @@ to_tsquery('simple', %s)
        ORDER BY sparse_score DESC
        LIMIT %s;
    """
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (tsquery_str, tsquery_str, tsquery_str, limit))
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "opp_id": r[1],
                    "product_name": r[2],
                    "score": round(float(r[3]), 4),
                    "rank": r[4],
                    "source": "sparse"
                }
                for r in rows
            ]


def search_dual(query: str, limit: int = 5) -> dict:
    """
    核心架构：CTE 单 SQL 极速双路融合召回
    在单次数据库往返中，并发使用 HNSW 与 GIN 双索引，同时返回带有顺位 rank 的 dense 与 sparse 结果
    """
    query_vec = embed_query(query)
    vec_str = str(query_vec)
    tsquery_str = build_tsquery(query)
    
    # 如果关键词完全没有可检索的 token，降级为仅查稠密向量
    if not tsquery_str:
        dense_hits = search_dense(query, limit=limit)
        return {"query": query, "dense_hits": dense_hits, "sparse_hits": []}
    
    cte_sql = """
        WITH dense_hits AS (
            SELECT 
                id, 
                opp_id, 
                product_name,
                category_lvl1,
                unit,
                price,
                cost_price,
                warranty_cost_per_year,
                stock,
                1 - (embedding <=> %(embedding)s::vector) AS score,
                'dense' AS source,
                ROW_NUMBER() OVER (ORDER BY embedding <=> %(embedding)s::vector) AS rank
            FROM products
            ORDER BY embedding <=> %(embedding)s::vector
            LIMIT %(limit)s
        ),
        sparse_hits AS (
            SELECT 
                id, 
                opp_id, 
                product_name,
                category_lvl1,
                unit,
                price,
                cost_price,
                warranty_cost_per_year,
                stock,
                ts_rank(search_vector, to_tsquery('simple', %(tsquery)s)) AS score,
                'sparse' AS source,
                ROW_NUMBER() OVER (ORDER BY ts_rank(search_vector, to_tsquery('simple', %(tsquery)s)) DESC) AS rank
            FROM products
            WHERE search_vector @@ to_tsquery('simple', %(tsquery)s)
            ORDER BY score DESC
            LIMIT %(limit)s
        )
        SELECT id, opp_id, product_name, category_lvl1, unit, price, cost_price, warranty_cost_per_year, stock, score, source, rank FROM dense_hits
        UNION ALL
        SELECT id, opp_id, product_name, category_lvl1, unit, price, cost_price, warranty_cost_per_year, stock, score, source, rank FROM sparse_hits;
    """
    
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            cur.execute(cte_sql, {"embedding": vec_str, "tsquery": tsquery_str, "limit": limit})
            rows = cur.fetchall()
            
            dense_results = []
            sparse_results = []
            
            for r in rows:
                item = {
                    "id": r[0],
                    "opp_id": r[1],
                    "product_name": r[2],
                    "category_lvl1": r[3],
                    "unit": r[4],
                    "price": float(r[5]) if r[5] is not None else 0.0,
                    "cost_price": float(r[6]) if r[6] is not None else 0.0,
                    "warranty_cost_per_year": float(r[7]) if r[7] is not None else 200.0,
                    "stock": int(r[8]) if r[8] is not None else 0,
                    "score": round(float(r[9]), 4),
                    "source": r[10],
                    "rank": r[11]
                }
                if r[10] == "dense":
                    dense_results.append(item)
                else:
                    sparse_results.append(item)
                    
            return {
                "query": query,
                "dense_hits": dense_results,
                "sparse_hits": sparse_results
            }


def run_benchmarks():
    """执行 4 组具有极端代表性的业务测试用例，对比双路召回的互补效果"""
    test_queries = [
        ("测试 1 [双向强命中]", "苹果18 远峰蓝"),
        ("测试 2 [同名歧义防带偏]", "红富士苹果 新鲜水果"),
        ("测试 3 [纯黑话/零字面命中 - 检验 ANN]", "想要一款安全的政企商务手机"),
        ("测试 4 [精确参数/型号直搜 - 检验 BM25]", "48口 PoE")
    ]
    
    print("\n" + "="*80)
    print("🚀 开始执行企业级双路召回 (ANN Dense + BM25 Sparse) 基准测试")
    print("="*80)
    
    for label, q in test_queries:
        print(f"\n👉 【{label}】 搜索词: \"{q}\"")
        res = search_dual(q, limit=4)
        
        print("  🔹 [第一路：ANN 稠密向量召回 (HNSW 语义)]")
        if res["dense_hits"]:
            for item in res["dense_hits"]:
                print(f"     Rank {item['rank']}: [{item['opp_id']}] {item['product_name']} (余弦相似度: {item['score']})")
        else:
            print("     (无命中)")
            
        print("  🔸 [第二路：BM25 稀疏关键字召回 (GIN 倒排)]")
        if res["sparse_hits"]:
            for item in res["sparse_hits"]:
                print(f"     Rank {item['rank']}: [{item['opp_id']}] {item['product_name']} (ts_rank得分: {item['score']})")
        else:
            print("     (无命中 - 说明字面完全未命中词项，这正是单一关键词检索的痛点！)")
            
        print("-" * 80)


if __name__ == "__main__":
    run_benchmarks()
