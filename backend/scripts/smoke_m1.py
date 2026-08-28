"""M1 冒烟测试：对运行中的后端做一次完整链路验证。

用法：
    cd backend
    ../.venv/Scripts/python scripts/smoke_m1.py [base_url]

覆盖：注册 / 登录 / 鉴权拦截 / 知识库 CRUD / 文档上传 / 切片查询。
"""
import io
import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EMAIL = f"smoke-{uuid.uuid4().hex[:8]}@test.com"
PASSWORD = "test12345"

client = httpx.Client(base_url=BASE, timeout=15)
passed: list[str] = []


def step(name: str, ok: bool, detail: str = ""):
    passed.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        sys.exit(1)


step("health", client.get("/health").status_code == 200)

r = client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD})
step("register", r.status_code == 200 and "token" in r.json(), r.text[:80])

r = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
step("login", r.status_code == 200 and "token" in r.json())
token = r.json()["token"]

step(
    "auth guard rejects anonymous",
    client.get("/api/kbs").status_code == 401,
)
client.headers["Authorization"] = f"Bearer {token}"

r = client.post("/api/kbs", json={"name": "产品手册知识库", "description": "M1 冒烟测试"})
step("create kb", r.status_code == 200 and "id" in r.json(), r.text[:80])
kb_id = r.json()["id"]

r = client.get("/api/kbs")
items = r.json()
step(
    "list kbs",
    r.status_code == 200 and any(kb["id"] == kb_id and kb["name"] == "产品手册知识库" for kb in items),
)

content = f"# 测试文档 {time.time()}\n\nKnowBase 是一个 AI 知识库问答系统。\n".encode("utf-8")
r = client.post(
    f"/api/kbs/{kb_id}/documents",
    files={"file": ("test.md", io.BytesIO(content), "text/markdown")},
)
step("upload document", r.status_code == 200 and r.json().get("status") == "pending", r.text[:80])
doc_id = r.json()["id"]

r = client.get(f"/api/documents/{doc_id}/chunks")
step("list chunks (empty until M2 pipeline)", r.status_code == 200 and r.json() == [])

r = client.delete(f"/api/kbs/{kb_id}")
step("delete kb", r.status_code == 200)

print(f"\n{len(passed)}/{len(passed)} steps passed — M1 链路完整可用")
