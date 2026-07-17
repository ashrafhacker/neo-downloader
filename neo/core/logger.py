import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name='neo', log_file='neo.log', level=logging.INFO):
    """Sets up a rotating file logger."""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    handler = RotatingFileHandler(f'logs/{log_file}', maxBytes=10*1024*1024, backupCount=5)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(handler)
        
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

logger = setup_logger()
