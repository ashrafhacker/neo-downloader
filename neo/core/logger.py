import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler


def setup_logger(name='neo', log_file='neo.log', level=logging.INFO):
    """Sets up a rotating file logger.

    Degrades gracefully: on read-only filesystems (e.g. Vercel) the file
    handler is skipped and logging falls back to stderr only, so importing
    this module never crashes the serverless function.
    """
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    # Try to use a writable log location; fall back to /tmp, then skip file logging.
    candidates = ['logs', os.path.join(tempfile.gettempdir(), 'logs')]
    handler = None
    for base in candidates:
        try:
            os.makedirs(base, exist_ok=True)
            handler = RotatingFileHandler(
                os.path.join(base, log_file), maxBytes=10 * 1024 * 1024, backupCount=5
            )
            break
        except OSError:
            continue

    if handler is not None:
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Always log to console (captured by serverless platforms).
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()
