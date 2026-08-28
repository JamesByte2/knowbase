import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.db import get_db
from app.models import Conversation, User

router = APIRouter(prefix="/api", tags=["chat"])


class ChatIn(BaseModel):
    question: str
    conversation_id: int | None = None


@router.post("/kbs/{kb_id}/chat")
def chat(kb_id: int, body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    def stream():
        # TODO(M3): embedding -> Qdrant 检索 top_k -> 组装带编号来源的 prompt -> LLM 流式生成
        #           消息与引用写入 message 表，SSE 事件依次推送 tokens / citations / done
        events = ["正在检索知识库（骨架演示，M3 实现真实链路）……"]
        for text in events:
            yield f"data: {json.dumps({'type': 'token', 'content': text}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/kbs/{kb_id}/conversations")
def create_conversation(kb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = Conversation(kb_id=kb_id, user_id=user.id)
    db.add(conv)
    db.commit()
    return {"id": conv.id}
