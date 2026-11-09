import logging.config


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"},
            },
            "root": {"handlers": ["console"], "level": level.upper()},
            "loggers": {
                # Request lines are emitted by our own middleware.
                "uvicorn.access": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )
