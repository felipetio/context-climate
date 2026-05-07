import logging
from contextlib import asynccontextmanager

from chainlit.utils import mount_chainlit
from fastapi import FastAPI

import app.data  # noqa: F401  # registers Chainlit data layer
from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application-level resources (asyncpg pool for RAG when enabled)."""
    if settings.rag_enabled:
        import asyncpg  # noqa: PLC0415 — lazy import, keeps startup fast when RAG is off

        import app.db as _app_db  # noqa: PLC0415

        logger.info("RAG enabled — creating asyncpg pool for upload processing")
        _app_db.pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
        logger.info("asyncpg pool created")

    yield

    if settings.rag_enabled:
        import app.db as _app_db  # noqa: PLC0415

        if _app_db.pool is not None:
            await _app_db.pool.close()
            _app_db.pool = None
            logger.info("asyncpg pool closed")


app = FastAPI(title="Context Climate", lifespan=lifespan)
mount_chainlit(app=app, target="app/chat.py", path="/")
