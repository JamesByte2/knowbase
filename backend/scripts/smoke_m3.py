"""M3 冒烟测试：RAG 检索问答全链路。

用法：
    cd backend
    ../.venv/Scripts/python scripts/smoke_m3.py [base_url]

真实调用硅基流动（embedding + chat 免费模型），验证：
上传 -> ready -> 提问 -> SSE 流式回答 -> 引用与资料一致 -> 消息持久化。
"""
import io
import json
import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EMAIL = f"smoke3-{uuid.uuid4().hex[:8]}@test.com"
PASSWORD = "test12345"

client = httpx.Client(base_url=BASE, timeout=120)


def step(name: str, ok: bool, detail: str = ""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        sys.exit(1)


# 准备：注册 + 建库 + 上传一份含明确事实的文档
token = client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).json()["token"]
client.headers["Authorization"] = f"Bearer {token}"
kb_id = client.post("/api/kbs", json={"name": "M3 测试库"}).json()["id"]

faq = """# 星辰咖啡机产品手册

## 保修政策
星辰咖啡机整机保修 2 年，加热核心部件保修 5 年。保修期内非人为损坏免费维修。

## 清洁方法
每月使用柠檬酸除垢一次：将 20 克柠檬酸溶于 500 毫升温水，倒入水箱执行除垢程序，完成后用清水冲洗水箱两遍。

## 故障处理
咖啡出液变慢时，优先检查滤网是否堵塞；指示灯红色闪烁表示水箱缺水，加满水后长按启动键 3 秒复位。
"""
r = client.post(f"/api/kbs/{kb_id}/documents", files={"file": ("manual.md", io.BytesIO(faq.encode()), "text/markdown")})
doc_id = r.json()["id"]
deadline = time.time() + 90
while time.time() < deadline:
    docs = client.get(f"/api/kbs/{kb_id}/documents").json()
    if docs and docs[0]["status"] in ("ready", "failed"):
        break
    time.sleep(3)
step("document ready", docs[0]["status"] == "ready", f"status={docs[0]['status']}")

# 提问并解析 SSE 流
question = "咖啡机保修几年？出液变慢怎么办？"
events: list[dict] = []
with client.stream("POST", f"/api/kbs/{kb_id}/chat", json={"question": question}) as resp:
    step("sse status", resp.status_code == 200, f"http={resp.status_code}")
    buffer = ""
    for chunk in resp.iter_text():
        buffer += chunk
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))

tokens = "".join(e["content"] for e in events if e["type"] == "token")
meta = next((e for e in events if e["type"] == "meta"), {})
cits = next((e for e in events if e["type"] == "citations"), {})
done = any(e["type"] == "done" for e in events)
errs = [e for e in events if e["type"] == "error"]

step("stream completed", done and not errs, f"error={errs[:1]}")
step("answer grounded", "2 年" in tokens and "滤网" in tokens, f"answer={tokens[:120]}...")
step("citations sent", bool(cits.get("citations")), f"n={len(cits.get('citations', []))} first={cits.get('citations', [{}])[0].get('filename')}")
step("conversation id", isinstance(meta.get("conversation_id"), int))

# 消息持久化验证
msgs = client.get(f"/api/conversations/{meta['conversation_id']}/messages").json()
step("messages persisted", [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["citations"], f"roles={[m['role'] for m in msgs]}")

# 无关问题应明确说不知道（防编造）
events2: list[dict] = []
with client.stream("POST", f"/api/kbs/{kb_id}/chat", json={"question": "量子力学的波函数坍缩是什么？", "conversation_id": meta["conversation_id"]}) as resp:
    buffer = ""
    for chunk in resp.iter_text():
        buffer += chunk
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            if raw.startswith("data: "):
                events2.append(json.loads(raw[6:]))
answer2 = "".join(e["content"] for e in events2 if e["type"] == "token")
step("refuses out-of-scope", done is True and ("没有" in answer2 or "无法" in answer2 or "找不到" in answer2 or "相关内容" in answer2), f"answer={answer2[:100]}...")

# 清理
client.delete(f"/api/documents/{doc_id}")
client.delete(f"/api/kbs/{kb_id}")
print("\nM3 RAG 问答全链路通过")
