from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import settings
from app.api.v1.router import router as v1_router


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Chatbot API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.get("/")
    def root():
        return {"status": "ok"}
    app.include_router(v1_router, prefix="/api/v1")
    return app
