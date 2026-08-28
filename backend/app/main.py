from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, kbs
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="KnowBase API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(kbs.router)
    app.include_router(chat.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "llm_configured": bool(get_settings().llm_api_key)}

    return app


app = create_app()
