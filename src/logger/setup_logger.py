from logging.config import dictConfig

from config.logging_config import LOGGING_CONFIG


def setup_logging()-> None:
    try:
        dictConfig(LOGGING_CONFIG)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise
