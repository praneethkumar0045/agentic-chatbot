from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import make_url

try:
    from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency for local dev/test envs
    PostgresSaver = None

from app.core import settings
from app.api.v1.router import router as v1_router
from app.services import chat_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be configured to start the API.")
    if PostgresSaver is None:
        raise RuntimeError(
            "The optional dependency 'langgraph-checkpoint-postgres' is required "
            "to start the API."
        )
    saver_url = make_url(settings.DATABASE_URL).set(drivername="postgresql")
    with PostgresSaver.from_conn_string(
        saver_url.render_as_string(hide_password=False)
    ) as checkpointer:
        checkpointer.setup()
        app.state.chatbot = chat_service.build_chatbot(checkpointer)
        yield


def create_app(*, lifespan_context=lifespan) -> FastAPI:
    app = FastAPI(
        title="Agentic Chatbot API",
        version="1.0.0",
        lifespan=lifespan_context,
    )
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
