# src/logging_config.py
import logging
import sys
from pythonjsonlogger import jsonlogger
from logging import StreamHandler

def configure_logging(level=logging.INFO):
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove default handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)

    handler = StreamHandler(stream=sys.stdout)
    fmt = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s %(module)s %(pathname)s %(lineno)d %(request_id)s %(task_id)s'
    )
    handler.setFormatter(fmt)
    handler.setLevel(level)
    logger.addHandler(handler)

    # reduce verbosity for noisy libs
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
