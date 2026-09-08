import json
import sys
import time

import httpx


job_id = sys.argv[1]
url = f"http://127.0.0.1:8010/api/bots/utel-inconcert/batch/{job_id}"
last = None

while True:
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    snapshot = (
        payload.get("status"),
        payload.get("completed"),
        payload.get("success"),
        payload.get("failed"),
        payload.get("pending"),
        payload.get("current_row"),
        payload.get("phase"),
        payload.get("last_error"),
    )
    if snapshot != last:
        print(
            json.dumps(
                {
                    "status": snapshot[0],
                    "completed": snapshot[1],
                    "success": snapshot[2],
                    "failed": snapshot[3],
                    "pending": snapshot[4],
                    "current_row": snapshot[5],
                    "phase": snapshot[6],
                    "last_error": snapshot[7],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        last = snapshot
    if payload.get("status") != "RUNNING":
        print("FINAL_JSON=" + json.dumps(payload, ensure_ascii=False), flush=True)
        break
    time.sleep(5)
