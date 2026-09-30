import requests
import time

print("Starting debug post...")
t0 = time.time()
try:
    r = requests.post(
        "http://127.0.0.1:8000/api/submit",
        json={"sales_input": "帮我下 10 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9 折，送 1 年延保和 10 个显卡支架"},
        timeout=30
    )
    print(f"Status: {r.status_code}, Elapsed: {time.time()-t0:.2f}s")
    print("Response JSON:", r.json())
except Exception as e:
    print("Error occurred:", e)
