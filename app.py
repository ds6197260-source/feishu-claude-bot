import os
import hashlib
import hmac
import json
import httpx
from flask import Flask, request, jsonify

app = Flask(__name__)

# 配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a95ecf9f4c68dbb5")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "MvX4Jrucmje9WLm6pe3TMbQAEevidICs")
API_KEY = os.environ.get("API_KEY", "")  # 302.ai 的 Key
API_BASE_URL = "https://api.302.ai/v1"

# 避免重复处理同一条消息
processed_messages = set()


def get_feishu_token():
    """获取飞书访问令牌"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = httpx.post(url, json={
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET
    })
    return resp.json().get("tenant_access_token")


def send_feishu_message(open_id, text, token):
    """发送消息给飞书用户"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    httpx.post(url, headers=headers, json={
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
        "receive_id_type": "open_id"
    })


def ask_claude(user_message):
    """调用 302.ai 的 Claude API"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
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
    data = resp.json()
    return data["content"][0]["text"]


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()

    # 飞书验证 URL 有效性
    if body.get("type") == "url_verification":
        return jsonify({"challenge": body.get("challenge")})

    # 处理消息事件
    event = body.get("event", {})
    message = event.get("message", {})
    msg_id = message.get("message_id")

    # 防重复处理
    if not msg_id or msg_id in processed_messages:
        return jsonify({"code": 0})
    processed_messages.add(msg_id)

    # 只处理文本消息
    if message.get("message_type") != "text":
        return jsonify({"code": 0})

    # 获取用户消息
    content = json.loads(message.get("content", "{}"))
    user_text = content.get("text", "").strip()
    if not user_text:
        return jsonify({"code": 0})

    # 获取发送者
    sender = event.get("sender", {})
    open_id = sender.get("sender_id", {}).get("open_id")
    if not open_id:
        return jsonify({"code": 0})

    # 调用 Claude 并回复
    try:
        token = get_feishu_token()
        reply = ask_claude(user_text)
        send_feishu_message(open_id, reply, token)
    except Exception as e:
        print(f"Error: {e}")
        token = get_feishu_token()
        send_feishu_message(open_id, "抱歉，处理出错了，请稍后再试。", token)

    return jsonify({"code": 0})


@app.route("/", methods=["GET"])
def index():
    return "飞书 Claude 机器人运行中 ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
