"""M2 冒烟测试：文档入库流水线全链路（上传 -> 解析 -> 切片 -> 向量化 -> ready）。

用法：
    cd backend
    ../.venv/Scripts/python scripts/smoke_m2.py [base_url]

依赖硅基流动 key（.env 中 EMBEDDING_API_KEY），会真实调用 embedding API。
"""
import io
import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EMAIL = f"smoke2-{uuid.uuid4().hex[:8]}@test.com"
PASSWORD = "test12345"

client = httpx.Client(base_url=BASE, timeout=30)


def step(name: str, ok: bool, detail: str = ""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        sys.exit(1)


# 准备：注册 + 建知识库
token = client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).json()["token"]
client.headers["Authorization"] = f"Bearer {token}"
kb_id = client.post("/api/kbs", json={"name": "M2 测试库"}).json()["id"]

# 上传一份足够切片的 Markdown（约 3000 字）
body = "\n\n".join(
    f"## 章节标题 {i}\n\n这是第 {i} 章的正文内容。KnowBase 系统支持文档解析、切片与向量化。"
    f"第 {i} 章介绍了检索增强生成的工作原理，包括向量召回、重排序与引用溯源等关键步骤。"
    for i in range(1, 31)
)
r = client.post(
    f"/api/kbs/{kb_id}/documents",
    files={"file": ("guide.md", io.BytesIO(body.encode("utf-8")), "text/markdown")},
)
step("upload", r.status_code == 200 and r.json()["status"] == "pending", r.text[:80])
doc_id = r.json()["id"]

# 轮询等待流水线完成（最长 90 秒）
deadline = time.time() + 90
status = "pending"
while time.time() < deadline:
    docs = client.get(f"/api/kbs/{kb_id}/documents").json()
    status = next(d["status"] for d in docs if d["id"] == doc_id)
    if status in ("ready", "failed"):
        break
    time.sleep(3)

info = next(d for d in client.get(f"/api/kbs/{kb_id}/documents").json() if d["id"] == doc_id)
step("pipeline ready", status == "ready", f"status={status} error={info['error'][:120]} chunk_count={info['chunk_count']}")
step("chunks persisted", info["chunk_count"] > 1, f"chunk_count={info['chunk_count']}")

chunks = client.get(f"/api/documents/{doc_id}/chunks").json()
step("chunk preview", len(chunks) == info["chunk_count"] and all(c["content"] for c in chunks))

# 上传一个空内容的坏文档，验证状态机落到 failed 而不是挂死
r = client.post(
    f"/api/kbs/{kb_id}/documents",
    files={"file": ("empty.md", io.BytesIO(b"\n\n"), "text/markdown")},
)
bad_id = r.json()["id"]
deadline = time.time() + 30
while time.time() < deadline:
    docs = client.get(f"/api/kbs/{kb_id}/documents").json()
    bad = next(d for d in docs if d["id"] == bad_id)
    if bad["status"] in ("ready", "failed"):
        break
    time.sleep(2)
step("empty doc -> failed", bad["status"] == "failed", f"error={bad['error'][:80]}")

# 删除文档与知识库（同时验证向量清理不报错）
step("delete document", client.delete(f"/api/documents/{doc_id}").status_code == 200)
step("delete kb", client.delete(f"/api/kbs/{kb_id}").status_code == 200)

print("\nM2 流水线全链路通过")
