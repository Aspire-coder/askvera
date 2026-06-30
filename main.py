"""ASK Vera FastAPI application entry point."""

import signal
from collections.abc import Generator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import CorrelationIdMiddleware, RateLimitMiddleware
from api.routes import router
from config import settings
from scripts.validate_config import validate
from services.aws_clients import init_aws_clients
from services.cache import init_cache
from services.db import close_db, init_db
from utils.exceptions import ConfigurationError
from utils.logging import configure_logging, get_logger

configure_logging()
LOGGER = get_logger("main")
shutdown_requested = False


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
    signal.signal(signal.SIGTERM, _handle_sigterm)
    init_aws_clients()
    init_db()
    init_cache()
    LOGGER.info("startup_complete")
    yield
    close_db()
    LOGGER.info("shutdown_complete")


app = FastAPI(title="ASK Vera", version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router)
