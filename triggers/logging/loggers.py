# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from logging import Handler, Logger, LoggerAdapter as BaseLoggerAdapter, NOTSET
from typing import Optional, Text

from triggers.itertools import merge_dict_recursive


class LocalLogger(Logger):
    """
    Logger that is disconnected from the global logging config.

    Note that this class starts off without any handlers.
    """
    def __init__(self, name=None, level=NOTSET):
        # type: (Optional[Text], int) -> None
        if name is None:
            # Create a unique name for the logger.
            name = '_{cls}_{id}'.format(
                cls = type(self).__name__,
                id  = id(self),
            )

        super(LocalLogger, self).__init__(name, level)

    def addHandler(self, handler):
        # type: (Handler) -> LocalLogger
        """
        Add the specified handler to this logger.
        """
        super(LocalLogger, self).addHandler(handler)
        return self

    def close(self):
        """
        Flushes and closes all handlers for this logger.

        It's really, really important to call this method if you add
        buffered handlers to the logger, since they probably won't get
        flushed when the global ``shutdown`` function gets invoked.

        References:
          - :py:func:`logging.shutdown`
        """
        for handler in self.handlers:
            handler.acquire()
            try:
                handler.flush()
                handler.close()
            finally:
                handler.release()

    def isEnabledFor(self, level):
        # type: (int) -> bool
        """
        Returns whether this logger should store records with the
        specified level.
        """
        #
        # Loggers typically defer to their manager to determine their
        # filtering settings.  However, because this logger doesn't
        # interact with any other systems (and because we often use it
        # in unit tests where logging is disabled globally), we will
        # ignore the manager setting.
        #
        # References:
        #   - :py:func:`logging.disable`
        #
        return level >= self.getEffectiveLevel()


class LoggerAdapter(BaseLoggerAdapter):
    """
    A wrapper that allows you to add extra variables to any log
    messages created by a logger.

    References:
      - :py:class:`logging.LoggerAdapter`
    """
    def __getattr__(self, attr):
        return getattr(self.logger, attr)

    def process(self, msg, kwargs):
        kwargs['extra'] =\
            merge_dict_recursive(self.extra, kwargs.get('extra', {}))
        return msg, kwargs

    @property
    def context(self):
        # type: () -> dict
        """
        Accessor for the logger context dict.
        """
        return self.extra.setdefault('context', {})


