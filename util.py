import os
import logging
import warnings
import pikaconfig

try:
    from cloghandler import ConcurrentRotatingFileHandler as RotatingFileHandler
except ImportError:
    warnings.warn("cloghandler not available, will use NON-concurrent log handler")
    from logging.handlers import RotatingFileHandler as OrigRotatingFileHandler

    def RotatingFileHandler(*args, **kwargs):
        # Function for conforming with ConcurrentRotatingFileHandler
        # which accepts a debug parameter.
        kwargs.pop('debug', None)
        return OrigRotatingFileHandler(*args, **kwargs)

USE_GELF = getattr(pikaconfig, 'USE_GELF', False)


def setupLogHandlers(fname, formatter=None, **kwargs):
    """
    Create a RotatingFileHandler to be used by a logger, and possibly a
    GELFHandler.

    By default the RotatingFileHandler stores 100 MB before starting a new
    log file and the last 10 log files are kept. The default formatter shows
    the logging level, current time, the function that created the log entry,
    and the specified message.

    :param str fname: path to the filename where logs will be written to
    :param logging.Formatter formatter: a custom formatter for this logger
    :param kwargs: custom parameters for the RotatingFileHandler
    :rtype: tuple
    """
    if formatter is None:
        formatter = logging.Formatter('%(levelname)s [%(asctime)s] %(funcName)s: %(message)s')

    opts = {'maxBytes': 100 * 1024 * 1024, 'backupCount': 10, 'debug': False}
    opts.update(kwargs)
    handler = RotatingFileHandler(os.path.join(pikaconfig.LOG_DIR, fname), **opts)
    handler.setFormatter(formatter)

    handlers = (handler, )
    if USE_GELF:
        gelf_handler = GELFHandler(**USE_GELF)
        gelf_handler.setLevel(logging.INFO)  # Ignore DEBUG messages.
        handlers += (gelf_handler, )

    return handlers

