import os
import json
import base64
import hashlib
import httpx
from flask import Flask, request, jsonify
from Crypto.Cipher import AES

app = Flask(__name__)

# 配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a95ecf9f4c68dbb5")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "MvX4Jrucmje9WLm6pe3TMbQAEevidICs")
FEISHU_ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "7cf244c2be37480e015788ab3fdd799e")
API_KEY = os.environ.get("API_KEY", "")
API_BASE_URL = "https://api.302.ai/v1"

processed_messages = set()


def decrypt_feishu(encrypt_str, key):
    key_bs = hashlib.sha256(key.encode()).digest()
    enc = base64.b64decode(encrypt_str)
    iv = enc[:16]
    from Crypto.Cipher import AES as _AES
    cipher = _AES.new(key_bs, _AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(enc[16:])
    pad = decrypted[-1]
    decrypted = decrypted[:-pad]
    return json.loads(decrypted.decode("utf-8"))


def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = httpx.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET})
    return resp.json().get("tenant_access_token")


def send_feishu_message(open_id, text, token):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    httpx.post(url, headers=headers, json={
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
        "receive_id_type": "open_id"
    })


def ask_claude(user_message):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    resp = httpx.post(
        f"{API_BASE_URL}/messages",
        headers=headers,
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": user_message}]
        },
        timeout=60
    )
    return resp.json()["content"][0]["text"]


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.get_json(force=True) or {}
    except Exception:
        raw = {}

    if "encrypt" in raw:
        try:
            body = decrypt_feishu(raw["encrypt"], FEISHU_ENCRYPT_KEY)
        except Exception as e:
            print(f"Decrypt error: {e}")
            return jsonify({"code": 0})
    else:
        body = raw

    if body.get("type") == "url_verification":
        return jsonify({"challenge": body.get("challenge")})
    if body.get("challenge"):
        return jsonify({"challenge": body.get("challenge")})

    event = body.get("event", {})
    message = event.get("message", {})
    msg_id = message.get("message_id")

    if not msg_id or msg_id in processed_messages:
        return jsonify({"code": 0})
    processed_messages.add(msg_id)

    if message.get("message_type") != "text":
        return jsonify({"code": 0})

    content = json.loads(message.get("content", "{}"))
    user_text = content.get("text", "").strip()
    if not user_text:
        return jsonify({"code": 0})

    sender = event.get("sender", {})
    open_id = sender.get("sender_id", {}).get("open_id")
    if not open_id:
        return jsonify({"code": 0})

    try:
        token = get_feishu_token()
        reply = ask_claude(user_text)
        send_feishu_message(open_id, reply, token)
    except Exception as e:
        print(f"Error: {e}")
        try:
            token = get_feishu_token()
            send_feishu_message(open_id, "抱歉，处理出错了，请稍后再试。", token)
        except:
            pass

    return jsonify({"code": 0})


@app.route("/", methods=["GET"])
def index():
    return "飞书 Claude 机器人运行中 ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
