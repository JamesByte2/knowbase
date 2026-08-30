import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.api.kbs import _owned_kb
from app.config import get_settings
from app.db import get_db
from app.models import Conversation, Message, User
from app.services.retrieval import search

router = APIRouter(prefix="/api", tags=["chat"])


class ChatIn(BaseModel):
    question: str
    conversation_id: int | None = None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


SYSTEM_PROMPT = (
    "你是一个企业知识库问答助手。请仅依据下面编号的资料片段回答用户问题，"
    "并在回答中用 [n] 标注引用了哪条资料。如果资料不足以回答，直接说明"
    "知识库中没有相关内容，不要编造。"
)


def _build_context(hits) -> str:
    parts = []
    for i, h in enumerate(hits, start=1):
        page = f"第{h.page}页" if h.page else "无页码"
        parts.append(f"[{i}] 来源：{h.filename}（{page}）\n{h.content}")
    return "\n\n".join(parts)


@router.post("/kbs/{kb_id}/chat")
def chat(kb_id: int, body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _owned_kb(kb_id, user, db)
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")

    if body.conversation_id:
        conv = db.get(Conversation, body.conversation_id)
        if conv is None or conv.kb_id != kb_id or conv.user_id != user.id:
            raise HTTPException(404, "会话不存在")
    else:
        conv = Conversation(kb_id=kb_id, user_id=user.id, title=question[:50])
        db.add(conv)
        db.commit()

    conversation_id = conv.id
    db.add(Message(conversation_id=conversation_id, role="user", content=question))
    db.commit()

    # 检索在流式开始前同步完成，保证 citations 先于生成发送
    from app.services.pipeline import get_qdrant

    client = get_qdrant()
    try:
        hits = search(db, client, kb_id, question)
    finally:
        client.close()

    citations = [
        {"n": i, "document_id": h.document_id, "filename": h.filename, "page": h.page, "content": h.content}
        for i, h in enumerate(hits, start=1)
    ]
    context = _build_context(hits) if hits else "（知识库中没有检索到相关资料）"

    def stream():
        s = get_settings()
        llm = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key)
        accumulated = ""
        try:
            yield _sse({"type": "meta", "conversation_id": conversation_id})
            stream_resp = llm.chat.completions.create(
                model=s.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"},
                ],
                stream=True,
                temperature=0.3,
            )
            for chunk in stream_resp:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    accumulated += delta
                    yield _sse({"type": "token", "content": delta})
            yield _sse({"type": "citations", "citations": citations})
            yield _sse({"type": "done"})
        except Exception as exc:  # noqa: BLE001 - 错误必须以 SSE 事件形式送达前端
            yield _sse({"type": "error", "message": str(exc)[:300]})
        finally:
            if accumulated:
                db.add(
                    Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=accumulated,
                        citations_json=json.dumps(citations, ensure_ascii=False),
                    )
                )
                db.commit()

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/kbs/{kb_id}/conversations")
def list_conversations(kb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _owned_kb(kb_id, user, db)
    convs = db.scalars(
        select(Conversation).where(Conversation.kb_id == kb_id, Conversation.user_id == user.id).order_by(Conversation.id.desc())
    ).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at} for c in convs]


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "会话不存在")
    msgs = db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)).all()
    return [
        {"role": m.role, "content": m.content, "citations": json.loads(m.citations_json) if m.citations_json else []}
        for m in msgs
        if m.role != "system"
    ]
