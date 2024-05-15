import logging
import sys
from typing import Text, Union


def get_logger(
    name: Text = __name__, log_level: Union[Text, int] = logging.DEBUG
) -> logging.Logger:
    """Get custom logger for module and its logging

    Args:
        name (Text, optional): module name. Defaults to __name__.
        log_level (Union[Text, int], optional): selected log level. Defaults to logging.DEBUG.

    Returns:
        logging.Logger: returns logging.logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # clear out all previous handler
    if logger.hasHandlers():
        logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s — %(name)s — %(levelname)s — %(message)s"
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.propagate = False

    return logger
