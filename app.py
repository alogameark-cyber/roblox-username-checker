import os
import time
import threading
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")
ROBLOX_VALIDATE_URL = "https://auth.roblox.com/v1/usernames/validate"
MAX_BATCH = 30
MIN_INTERVAL = 1.5
_last_call = 0.0
_lock = threading.Lock()

def validate_name(name):
    global _last_call
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    payload = {
        "username": name,
        "birthday": "2000-01-01",
        "context": "Signup"
    }
    try:
        response = requests.post(
            ROBLOX_VALIDATE_URL,
            json=payload,
            headers={"User-Agent": "UsernameAvailabilityChecker/1.0"},
            timeout=12
        )
        if response.status_code in (403, 429):
            return {"username": name, "status": "error",
                    "message": f"Roblox giới hạn hoặc từ chối yêu cầu (HTTP {response.status_code}). Thử lại sau."}
        response.raise_for_status()
        data = response.json()
        code = data.get("code")
        if code == 0:
            return {"username": name, "status": "available",
                    "message": "API Roblox báo tên hợp lệ/khả dụng; hãy xác nhận lại khi đăng ký."}
        if code == 1:
            return {"username": name, "status": "taken",
                    "message": "Roblox báo tên đã được sử dụng."}
        return {"username": name, "status": "invalid",
                "message": data.get("message", "Tên không hợp lệ hoặc không khả dụng.")}
    except requests.RequestException as exc:
        return {"username": name, "status": "error",
                "message": f"Không kiểm tra được với Roblox: {str(exc)[:140]}"}
    except ValueError:
        return {"username": name, "status": "error",
                "message": "Roblox trả về dữ liệu không đọc được."}

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.post("/api/check")
def check():
    body = request.get_json(silent=True) or {}
    names = body.get("usernames", [])
    if not isinstance(names, list) or not names:
        return jsonify(error="Hãy tạo danh sách username trước."), 400
    if len(names) > MAX_BATCH:
        return jsonify(error=f"Mỗi lượt tối đa {MAX_BATCH} username."), 400

    clean = []
    for name in names:
        if not isinstance(name, str):
            continue
        name = name.strip()
        if (3 <= len(name) <= 20 and
            all(c.isascii() and (c.isalnum() or c == "_") for c in name) and
            not name.startswith("_") and not name.endswith("_") and "__" not in name):
            clean.append(name)
    clean = list(dict.fromkeys(clean))
    if not clean:
        return jsonify(error="Không có username nào đúng định dạng cơ bản."), 400

    results = [validate_name(name) for name in clean]
    return jsonify(results=results, checked=len(results), max_batch=MAX_BATCH)

@app.get("/health")
def health():
    return jsonify(status="ok")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
