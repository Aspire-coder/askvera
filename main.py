"""ASK Vera FastAPI application entry point."""

import signal
import time
from collections.abc import Generator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import RateLimitMiddleware
from api.routes import router
from app.audit import audit_dispatcher, audit_lifecycle
from app.audit.sinks.firehose import initialize_firehose_sink
from app.middleware.audit import AuditMiddleware
from app.middleware.correlation import CorrelationIdMiddleware
from config import settings
from scripts.validate_config import validate
from services.aws_clients import init_aws_clients
from services.cache import close_cache, init_cache
from services.db import close_db, init_db
from services.legal_service import load_legal_documents
from services.market_config import load_market_config
from utils.exceptions import ConfigurationError
from utils.logging import configure_logging, get_logger

configure_logging()
LOGGER = get_logger("main")
shutdown_requested = False


def _init_optional_cache(max_attempts: int = 3) -> None:
    """Initialise Redis if available, but keep the API online without cache."""
    for attempt in range(max_attempts):
        try:
            init_cache()
            return
        except Exception:
            if attempt == max_attempts - 1:
                LOGGER.exception("redis_cache_unavailable_continuing_without_cache")
                return
            delay_seconds = 2**attempt
            LOGGER.warning(
                "redis_cache_init_retry",
                attempt=attempt + 1,
                max_attempts=max_attempts,
                delay_seconds=delay_seconds,
            )
            time.sleep(delay_seconds)


def _handle_sigterm(signum: int, _frame: object) -> None:
    """Record a graceful shutdown request for EC2 Auto Scaling scale-in."""
    global shutdown_requested
    shutdown_requested = True
    LOGGER.info("shutdown_signal_received", signal=signum)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Generator[None, None, None]:
    """Validate config, initialise clients, and close cleanly on shutdown."""
    loaded_config = settings.load_ssm_config()
    LOGGER.info(
        "ssm_config_loaded",
        parameter_count=len(loaded_config),
        parameter_path=settings.SSM_PARAMETER_PATH,
        rds_secret_arn=settings.RDS_SECRET_ARN,
    )
    missing = validate()
    if missing:
        raise ConfigurationError(f"Missing required config values: {', '.join(missing)}")
    market_config = load_market_config()
    LOGGER.info("market_config_loaded", market_count=len(market_config["markets"]))
    signal.signal(signal.SIGTERM, _handle_sigterm)
    init_aws_clients()
    legal_documents = load_legal_documents()
    LOGGER.info("legal_documents_ready", document_count=len(legal_documents["documents"]))
    init_db()
    _init_optional_cache()
    audit_dispatcher.add_sink(initialize_firehose_sink())
    await audit_lifecycle.start()
    LOGGER.info("startup_complete")
    yield
    await audit_lifecycle.stop()
    close_cache()
    close_db()
    LOGGER.info("shutdown_complete")


app = FastAPI(title="ASK Vera", version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.include_router(router)
