import logging
from pathlib import Path

LOG_SIMPLE_FORMAT = "%(asctime)s | %(name)-s | %(levelname)-s | %(message)s"
LOG_DETAILED_FORMAT = "%(asctime)s | %(name)-s | %(levelname)-s | %(message)s | %(filename)s/%(funcName)s [%(lineno)d]"
CURRENT_DIR = Path('/code/app') #Path(__file__).resolve().parent
LOG_FILE_NAME = CURRENT_DIR / "logs" / "transformer.log"

LOG_DIR = Path(CURRENT_DIR / "logs")
LOG_DIR.mkdir(exist_ok=True)

class InfoFilter(logging.Filter):
    """Filter events above INFO level"""

    def filter(self, record):
        return record.levelname == "INFO"


LOGGING_CONFIG = dict(
    version=1,
    disable_existing_loggers=False,
    formatters={
        "file": {"format": LOG_DETAILED_FORMAT},
        "detailed_console": {
            "()": "coloredlogs.ColoredFormatter",
            "format": LOG_DETAILED_FORMAT,
        },
        "simple_console": {
            "()": "coloredlogs.ColoredFormatter",
            "format": LOG_SIMPLE_FORMAT,
        },
    },
    filters={
        "info_filter": {
            "()": InfoFilter,
        }
    },
    handlers={
        "simple_console": {
            "level": logging.INFO,
            "class": "logging.StreamHandler",
            "formatter": "simple_console",
            "filters": ["info_filter"],
        },
        "detailed_console": {
            "level": logging.WARNING,
            "class": "logging.StreamHandler",
            "formatter": "detailed_console",
        },
        "file": {
            "level": logging.INFO,
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "file",
            "filename": LOG_FILE_NAME,
            "maxBytes": 1024 * 1024 * 50,  # 50 MB
            "backupCount": 5,  # keep at most 5 log files
            "mode": "a",
        },
    },
    root={
        "level": logging.INFO,
        "handlers": ["simple_console", "detailed_console", "file"],
    },
)
