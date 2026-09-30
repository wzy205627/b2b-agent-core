import json
import time
import httpx

url = "http://127.0.0.1:8000/api/submit-stream"
payload = {
    "sales_input": "帮我下单50台旗舰游戏显卡，申请8.8折，并送两年延保和500个保护壳"
}

start = time.time()
print("Starting request to", url)

try:
    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", url, json=payload) as response:
            print("Status code:", response.status_code)
            print("Headers:", dict(response.headers))
            for chunk in response.iter_raw():
                elapsed = time.time() - start
                print(f"[{elapsed:.2f}s raw chunk] {chunk.decode('utf-8', errors='replace')}")
except Exception as e:
    print(f"Exception after {time.time() - start:.2f}s: {type(e)} {e}")
