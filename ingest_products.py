import os
import sys
import psycopg
from dotenv import load_dotenv
import dashscope
from pgvector.psycopg import register_vector

load_dotenv()

DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

# 预置纯 3C 智能终端与企业级 IT 电子设备专属商业数据集 (涵盖专属赠品配件与无赠品DIY散件)
DEFAULT_SAMPLE_PRODUCTS = [
    # 1. 旗舰智能手机整机 (专属赠品：手机壳、防窥/防爆钢化膜)
    {"opp_id": "OPP-001", "product_name": "苹果18 Pro Max 512G 暗夜紫", "category_lvl1": "3C整机", "unit": "台", "price": 9999.00, "cost_price": 7800.00, "warranty_cost_per_year": 350.00, "stock": 150},
    {"opp_id": "OPP-002", "product_name": "苹果18 标准版 256G 远峰蓝", "category_lvl1": "3C整机", "unit": "台", "price": 5999.00, "cost_price": 4600.00, "warranty_cost_per_year": 200.00, "stock": 600},
    {"opp_id": "OPP-005", "product_name": "华为 Mate70 Pro+ 16GB+512GB 羽砂黑", "category_lvl1": "3C整机", "unit": "台", "price": 8999.00, "cost_price": 6900.00, "warranty_cost_per_year": 300.00, "stock": 200},
    {"opp_id": "OPP-8848", "product_name": "华为 Mate70 RS 非凡大师 16G+1TB 瑞红", "category_lvl1": "3C整机", "unit": "台", "price": 12999.00, "cost_price": 9500.00, "warranty_cost_per_year": 500.00, "stock": 40},
    {"opp_id": "OPP-006", "product_name": "小米15 Ultra 徕卡专业影像旗舰 钛金属", "category_lvl1": "3C整机", "unit": "台", "price": 6499.00, "cost_price": 5100.00, "warranty_cost_per_year": 220.00, "stock": 350},

    # 2. 蓝牙无线耳机 (专属赠品：硅胶保护套、防摔挂钩保护套)
    {"opp_id": "OPP-021", "product_name": "苹果 AirPods Pro 2 主动降噪蓝牙无线耳机", "category_lvl1": "3C数码", "unit": "副", "price": 1899.00, "cost_price": 1350.00, "warranty_cost_per_year": 120.00, "stock": 500},
    {"opp_id": "OPP-022", "product_name": "华为 FreeBuds Pro 3 星闪无线降噪蓝牙耳机", "category_lvl1": "3C数码", "unit": "副", "price": 1499.00, "cost_price": 1050.00, "warranty_cost_per_year": 100.00, "stock": 400},
    {"opp_id": "OPP-023", "product_name": "索尼 WF-1000XM5 旗舰降噪真无线蓝牙耳机", "category_lvl1": "3C数码", "unit": "副", "price": 1699.00, "cost_price": 1180.00, "warranty_cost_per_year": 110.00, "stock": 300},

    # 3. 商务办公笔记本与电竞工作站 (专属赠品：配套无线/电竞鼠标、机械键盘、防震电脑包)
    {"opp_id": "OPP-012", "product_name": "联想 ThinkPad X1 Carbon AI 商务轻薄笔记本电脑", "category_lvl1": "3C整机", "unit": "台", "price": 12999.00, "cost_price": 9800.00, "warranty_cost_per_year": 400.00, "stock": 120},
    {"opp_id": "OPP-009", "product_name": "联想 拯救者 Y9000P 专业电竞游戏笔记本", "category_lvl1": "3C整机", "unit": "台", "price": 9999.00, "cost_price": 7900.00, "warranty_cost_per_year": 300.00, "stock": 180},
    {"opp_id": "OPP-010", "product_name": "苹果 MacBook Pro 16英寸 M4 Max 深度黑", "category_lvl1": "3C整机", "unit": "台", "price": 24999.00, "cost_price": 18500.00, "warranty_cost_per_year": 800.00, "stock": 50},
    {"opp_id": "OPP-013", "product_name": "华硕 ROG 枪神 8 Plus 超竞版 旗舰游戏笔记本", "category_lvl1": "3C整机", "unit": "台", "price": 21999.00, "cost_price": 16800.00, "warranty_cost_per_year": 700.00, "stock": 60},

    # 4. 智能平板设备
    {"opp_id": "OPP-016", "product_name": "苹果 iPad Pro 13英寸 M4芯片 512G 深空灰", "category_lvl1": "3C平板", "unit": "台", "price": 11499.00, "cost_price": 8200.00, "warranty_cost_per_year": 350.00, "stock": 100},

    # 5. 独立显卡 (专属赠品：ARGB 发光重型显卡支架、千斤顶磁吸支架)
    {"opp_id": "OPP-8849", "product_name": "英伟达 NVIDIA GeForce RTX 5090 24GB AI算力显卡", "category_lvl1": "电脑硬件", "unit": "盒", "price": 15999.00, "cost_price": 11500.00, "warranty_cost_per_year": 600.00, "stock": 60},
    {"opp_id": "OPP-024", "product_name": "英伟达 NVIDIA GeForce RTX 5080 16GB 光追电竞显卡", "category_lvl1": "电脑硬件", "unit": "盒", "price": 9999.00, "cost_price": 7400.00, "warranty_cost_per_year": 400.00, "stock": 100},
    {"opp_id": "OPP-025", "product_name": "AMD Radeon RX 7900 XTX 24GB 旗舰游戏显卡", "category_lvl1": "电脑硬件", "unit": "盒", "price": 7999.00, "cost_price": 5800.00, "warranty_cost_per_year": 350.00, "stock": 80},

    # 6. 企业级 IT 服务器与网络硬件
    {"opp_id": "OPP-007", "product_name": "思科 Catalyst 9300 48口 PoE+ 企业级核心千兆交换机", "category_lvl1": "企业IT", "unit": "台", "price": 18800.00, "cost_price": 12000.00, "warranty_cost_per_year": 1200.00, "stock": 30},
    {"opp_id": "OPP-008", "product_name": "戴尔 PowerEdge R760 2U双路企业级机架式服务器", "category_lvl1": "企业IT", "unit": "台", "price": 48000.00, "cost_price": 32000.00, "warranty_cost_per_year": 2500.00, "stock": 15},

    # 7. DIY 硬件核心散件 (⚠️ 严格不设捆绑赠品，仅支持适度商业延保服务)
    {"opp_id": "OPP-031", "product_name": "三星 990 PRO 2TB NVMe M.2 PCIe 4.0 旗舰固态硬盘", "category_lvl1": "电脑硬件", "unit": "片", "price": 1399.00, "cost_price": 920.00, "warranty_cost_per_year": 60.00, "stock": 500},
    {"opp_id": "OPP-032", "product_name": "希捷银河 Exos X20 16TB 7200转 企业级机械硬盘", "category_lvl1": "电脑硬件", "unit": "块", "price": 2199.00, "cost_price": 1480.00, "warranty_cost_per_year": 90.00, "stock": 300},
    {"opp_id": "OPP-033", "product_name": "瓦尔基里 GL360 一体式水冷CPU散热器", "category_lvl1": "电脑硬件", "unit": "套", "price": 799.00, "cost_price": 480.00, "warranty_cost_per_year": 50.00, "stock": 250},
    {"opp_id": "OPP-034", "product_name": "猫头鹰 NH-D15 G2 双塔旗舰风冷散热器", "category_lvl1": "电脑硬件", "unit": "个", "price": 899.00, "cost_price": 550.00, "warranty_cost_per_year": 40.00, "stock": 200},
    {"opp_id": "OPP-011", "product_name": "intel 酷睿 Ultra 9 285K 旗舰台式机处理器", "category_lvl1": "电脑硬件", "unit": "盒", "price": 4499.00, "cost_price": 3300.00, "warranty_cost_per_year": 150.00, "stock": 200},
    {"opp_id": "OPP-035", "product_name": "AMD 锐龙 9 9950X 16核32线程 台式机处理器", "category_lvl1": "电脑硬件", "unit": "盒", "price": 4299.00, "cost_price": 3150.00, "warranty_cost_per_year": 150.00, "stock": 180},
    {"opp_id": "OPP-036", "product_name": "华硕 ROG MAXIMUS Z890 HERO 旗舰电脑主板", "category_lvl1": "电脑硬件", "unit": "块", "price": 4999.00, "cost_price": 3600.00, "warranty_cost_per_year": 200.00, "stock": 100},
    {"opp_id": "OPP-037", "product_name": "海韵 PRIME TX-1000 1000W 钛金全模组电脑电源", "category_lvl1": "电脑硬件", "unit": "台", "price": 2399.00, "cost_price": 1600.00, "warranty_cost_per_year": 80.00, "stock": 150},

    # 8. 专属赠品配件与高频数码外设 (既可独立销售，亦作为赠品折算与库存扣减)
    {"opp_id": "OPP-003", "product_name": "苹果18 芳纶纤维磁吸防摔保护壳 远峰蓝", "category_lvl1": "3C配件", "unit": "个", "price": 199.00, "cost_price": 45.00, "warranty_cost_per_year": 0.00, "stock": 5000},
    {"opp_id": "OPP-015", "product_name": "华为 Mate70 AR高透防爆钢化保护膜", "category_lvl1": "3C配件", "unit": "张", "price": 39.00, "cost_price": 8.00, "warranty_cost_per_year": 0.00, "stock": 8000},
    {"opp_id": "OPP-041", "product_name": "AirPods Pro 液体硅胶防摔保护套 带金属挂钩", "category_lvl1": "3C配件", "unit": "个", "price": 69.00, "cost_price": 15.00, "warranty_cost_per_year": 0.00, "stock": 6000},
    {"opp_id": "OPP-018", "product_name": "罗技 MX Master 3S 无线蓝牙人体工学商务鼠标", "category_lvl1": "3C外设", "unit": "只", "price": 699.00, "cost_price": 240.00, "warranty_cost_per_year": 0.00, "stock": 1500},
    {"opp_id": "OPP-042", "product_name": "拯救者 K7 客制化热插拔有线无线机械键盘 87键", "category_lvl1": "3C外设", "unit": "把", "price": 399.00, "cost_price": 160.00, "warranty_cost_per_year": 0.00, "stock": 1800},
    {"opp_id": "OPP-043", "product_name": "ROG 铝合金 ARGB 发光重型显卡支架", "category_lvl1": "3C配件", "unit": "个", "price": 199.00, "cost_price": 65.00, "warranty_cost_per_year": 0.00, "stock": 3000},
    {"opp_id": "OPP-017", "product_name": "倍思 140W 氮化镓 GaN 多口超级快充套装", "category_lvl1": "3C配件", "unit": "套", "price": 299.00, "cost_price": 85.00, "warranty_cost_per_year": 0.00, "stock": 3000},
]

def get_embeddings_batch(texts: list[str], batch_size: int = 20) -> list[list[float]]:
    """
    调用百炼平台 qwen3.7-text-embedding-flash 模型分批生成 1024 维文本稠密向量 (单批 <= 25)
    """
    if not DASHSCOPE_API_KEY:
        raise ValueError("DASHSCOPE_API_KEY 未配置，请检查 .env 文件！")
    
    dashscope.api_key = DASHSCOPE_API_KEY
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        print(f"正在向阿里云百炼请求批量向量化 (Chunk: {len(chunk)}, Offset: {i}/{len(texts)})...")
        resp = dashscope.TextEmbedding.call(
            model="qwen3.7-text-embedding-flash",
            input=chunk
        )
        
        if resp.status_code != 200:
            raise RuntimeError(f"百炼 Embedding API 调用失败 [Code {resp.status_code}]: {resp.message}")
        
        for item in resp.output["embeddings"]:
            all_embeddings.append(item["embedding"])
            
    print(f"成功获取 {len(all_embeddings)} 条文本向量，单条维度: {len(all_embeddings[0])}")
    return all_embeddings

def ingest_products(products: list[dict]):
    """
    将商品列表批量生成向量并写入 PostgreSQL
    - 使用 ON CONFLICT (opp_id) DO UPDATE 保证幂等写入
    - search_vector 字段由数据库底层触发器自动生成并建立倒排索引
    """
    if not products:
        print("传入的商品列表为空，跳过入库。")
        return

    texts = [f"{p['product_name']} {p['category_lvl1']} {p['unit']}" for p in products]
    embeddings = get_embeddings_batch(texts)

    print(f"正在连接 PostgreSQL ({DB_URI}) 执行批量写入与倒排同步...")
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        # 注册 pgvector 适配器
        register_vector(conn)
        with conn.cursor() as cur:
            valid_opp_ids = [p["opp_id"] for p in products]
            cur.execute("DELETE FROM products WHERE NOT (opp_id = ANY(%s));", (valid_opp_ids,))
            upsert_sql = """
                INSERT INTO products (opp_id, product_name, category_lvl1, unit, price, cost_price, warranty_cost_per_year, stock, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (opp_id) DO UPDATE SET
                    product_name = EXCLUDED.product_name,
                    category_lvl1 = EXCLUDED.category_lvl1,
                    unit = EXCLUDED.unit,
                    price = EXCLUDED.price,
                    cost_price = EXCLUDED.cost_price,
                    warranty_cost_per_year = EXCLUDED.warranty_cost_per_year,
                    stock = EXCLUDED.stock,
                    embedding = EXCLUDED.embedding;
            """
            data_tuples = [
                (p["opp_id"], p["product_name"], p["category_lvl1"], p["unit"], p["price"], p["cost_price"], p["warranty_cost_per_year"], p["stock"], emb)
                for p, emb in zip(products, embeddings)
            ]
            cur.executemany(upsert_sql, data_tuples)
    
    print(f"✅ 成功入库/更新 {len(products)} 件商品数据！")

def verify_ingested_data():
    """验证数据库实际入库情况及触发器状态"""
    print("\n--- [正在校验数据库最新数据状态] ---")
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    opp_id, 
                    product_name, 
                    category_lvl1,
                    unit,
                    price,
                    cost_price,
                    warranty_cost_per_year,
                    stock,
                    vector_dims(embedding) as dim
                FROM products 
                ORDER BY id ASC;
            """)
            rows = cur.fetchall()
            print(f"当前 products 表共收录 {len(rows)} 条商品记录:\n")
            for opp_id, name, cat, unit, price, cost, w_cost, stock, dim in rows:
                margin = round(((price - cost) / price) * 100, 1) if price > 0 else 0
                print(f"  • [{opp_id}] {name} | 类目:{cat} | 单位:{unit} | 标价:¥{price} | BOM底线:¥{cost} (基准毛利:{margin}%) | 延保:¥{w_cost}/年 | 库存:{stock}{unit}")

if __name__ == "__main__":
    print("=== 开始执行商品离线索引写入流程 (Offline Indexing) ===")
    ingest_products(DEFAULT_SAMPLE_PRODUCTS)
    verify_ingested_data()
