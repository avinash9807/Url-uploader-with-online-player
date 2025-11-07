# worker.py
import os, time, requests

API_BASE = os.getenv("API_BASE", "https://witty-brooks-avinash9807-312e3d00.koyeb.app")
API_KEY = os.getenv("API_KEY", "")

headers = {"X-API-KEY": API_KEY} if API_KEY else {}

def process_loop():
    while True:
        try:
            resp = requests.post(f"{API_BASE}/process_pending?max=2", headers=headers, timeout=120)
            if resp.ok:
                print("Processed:", resp.json())
            else:
                print("Process_pending returned:", resp.status_code, resp.text)
        except Exception as e:
            print("Worker loop error:", e)
        time.sleep(5)  # wait a bit before next round

if __name__ == "__main__":
    process_loop()
