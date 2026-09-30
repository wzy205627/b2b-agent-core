import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db")

def setup_db():
    print(f"Connecting to Postgres database: {DB_URI} ...")
    # 使用 autocommit=True 执行系统级 DDL 操作 (如 CREATE EXTENSION)
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            print("1. Enabling pgvector extension...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            print("2. Recreating products table with vector(1024) and tsvector...")
            cur.execute("DROP TABLE IF EXISTS products CASCADE;")
            cur.execute("""
                CREATE TABLE products (
                    id SERIAL PRIMARY KEY,
                    opp_id VARCHAR(50) NOT NULL UNIQUE,
                    product_name TEXT NOT NULL,
                    category_lvl1 VARCHAR(50),
                    unit VARCHAR(20),
                    price NUMERIC(12, 2) DEFAULT 0.00,
                    cost_price NUMERIC(12, 2) DEFAULT 0.00,
                    warranty_cost_per_year NUMERIC(10, 2) DEFAULT 200.00,
                    stock INT DEFAULT 0,
                    embedding VECTOR(1024),
                    search_vector TSVECTOR
                );
            """)
            
            print("3. Creating trigger for automatic tsvector generation...")
            cur.execute("""
                CREATE OR REPLACE FUNCTION products_search_vector_trigger() RETURNS trigger AS $$
                BEGIN
                  new.search_vector := to_tsvector('simple', new.product_name || ' ' || coalesce(new.category_lvl1, '') || ' ' || coalesce(new.unit, ''));
                  RETURN new;
                END
                $$ LANGUAGE plpgsql;
            """)
            
            cur.execute("""
                DROP TRIGGER IF EXISTS tsvectorupdate ON products;
                CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
                ON products FOR EACH ROW EXECUTE FUNCTION products_search_vector_trigger();
            """)
            
            print("4. Creating HNSW vector index & GIN full-text search index...")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS products_embedding_hnsw_idx 
                ON products USING hnsw (embedding vector_cosine_ops);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS products_search_vector_gin_idx 
                ON products USING gin(search_vector);
            """)
            
            print(">> Database infrastructure setup completed successfully!")

if __name__ == "__main__":
    setup_db()
