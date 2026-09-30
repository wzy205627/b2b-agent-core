from psycopg_pool import ConnectionPool

pool = ConnectionPool("postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable")
with pool.connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'checkpoints';")
        print("Checkpoints columns:", cur.fetchall())
        cur.execute("SELECT thread_id, checkpoint_id, parent_checkpoint_id, checkpoint FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 2;")
        rows = cur.fetchall()
        for r in rows:
            print("thread_id:", r[0], "checkpoint_id:", r[1])
            # see keys in checkpoint json/dict
            if isinstance(r[3], dict):
                print("checkpoint keys:", r[3].keys())
                if 'ts' in r[3]:
                    print("ts:", r[3]['ts'])
            else:
                print("type of checkpoint:", type(r[3]))
