# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from logging import Handler, LogRecord, NOTSET
from traceback import format_exception
from typing import Iterator, List

import filters as f


class LogLevelHandler(Handler):
    """
    A log handler whose only job is to keep track of the max log level
    emitted.
    """
    def __init__(self, level=NOTSET):
        # type: (int) -> None
        """
        :param level:
            The minimum level that logs need to have in order to be
            emitted by this handler.
        """
        super(LogLevelHandler, self).__init__(level)

        self.max_level_emitted = NOTSET

    def clear(self):
        """
        Resets the handler's state.
        """
        self.max_level_emitted = NOTSET

    def emit(self, record):
        # type: (LogRecord) -> None
        """
        Records the log message.
        """
        self.max_level_emitted = max(self.max_level_emitted, record.levelno)


class MemoryHandler(LogLevelHandler):
    """
    A log handler that retains all of its records in a list in memory.

    This class is similar in function (though not in purpose) to
    :py:class:`logging.handlers.BufferingHandler`.
    """
    def __init__(self, level=NOTSET):
        # type: (int) -> None
        """
        :param level:
            The minimum level that logs need to have in order to be
            emitted by this handler.
        """
        super(MemoryHandler, self).__init__(level)

        self._records = []

    def __getitem__(self, index):
        # type: (int) -> LogRecord
        """
        Returns the log message at the specified index.
        """
        return self._records[index]

    def __iter__(self):
        # type: () -> Iterator[LogRecord]
        """
        Creates an iterator for the collected records.
        """
        return iter(self._records)

    def __len__(self):
        # type: () -> int
        """
        Returns the number of log records collected.
        """
        return len(self._records)

    @property
    def records(self):
        # type: () -> List[LogRecord]
        """
        Returns all log messages that the handler has collected.
        """
        return self._records[:]

    def clear(self):
        """
        Removes all log messages that this handler has collected.
        """
        super(MemoryHandler, self).clear()
        del self._records[:]

    def emit(self, record):
        # type: (LogRecord) -> None
        """
        Records the log message.
        """
        super(MemoryHandler, self).emit(record)

        # Remove ``exc_info`` to reclaim memory.
        if record.exc_info:
            if not record.exc_text:
                try:
                    record.exc_text =\
                        ''.join(
                            f.FilterRepeater(f.Unicode).apply(
                                format_exception(*record.exc_info),
                            ),
                        )
                except f.FilterError:
                    # If one of the files in the traceback uses a
                    # different character encoding, we might not be
                    # able to decode it.
                    #
                    # Reducing ``exc_info`` into a string is only a
                    # memory optimization, so we'll just ignore the
                    # error in this case.
                    pass
                else:
                    record.exc_info = None

        self._records.append(record)
