# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from logging import CRITICAL, INFO, NOTSET, WARNING
from unittest import TestCase

from triggers.logging.handlers import LogLevelHandler, MemoryHandler
from triggers.logging.loggers import LocalLogger


class LogLevelHandlerTestCase(TestCase):
    def setUp(self):
        super(LogLevelHandlerTestCase, self).setUp()

        self.logs   = LogLevelHandler()
        self.logger = LocalLogger().addHandler(self.logs)

    def test_max_level_emitted(self):
        """
        The handler remembers the max level of all the log messages
        that it's emitted.
        """
        # At first, we don't have a max level.
        self.assertEqual(self.logs.max_level_emitted, NOTSET)

        self.logger.info('Hello, world!')
        self.assertEqual(self.logs.max_level_emitted, INFO)

        # Adding a log message with higher level raises the max level
        # emitted for the handler.
        self.logger.critical('Frog blast the vent core!')
        self.assertEqual(self.logs.max_level_emitted, CRITICAL)

        # Adding a log message with a lower level does not affect the
        # max emitted level.
        self.logger.warning("The ranger's not going to like this Yogi...")
        self.assertEqual(self.logs.max_level_emitted, CRITICAL)

    def test_level_filter(self):
        """
        The handler is configured to emit only logs with a minimum
        level.
        """
        self.logs.level = WARNING

        self.logger.info('Repositioning antenna.')

        # The log message didn't pass the level filter, so it did not
        # get emitted.
        self.assertEqual(self.logs.max_level_emitted, NOTSET)

        self.logger.warning('Antenna malfunction.')

        # Now the log message is emitted.
        self.assertEqual(self.logs.max_level_emitted, WARNING)


class MemoryHandlerTestCase(TestCase):
    def setUp(self):
        super(MemoryHandlerTestCase, self).setUp()

        self.logs    = MemoryHandler()
        self.logger  = LocalLogger().addHandler(self.logs)

    def test_attach_logger(self):
        """
        The handler captures all log messages by default.
        """
        message = 'Hello, world!'
        level   = INFO

        self.logger.log(level, message)

        self.assertEqual(len(self.logs), 1)
        self.assertEqual(self.logs[0].getMessage(), message)
        self.assertEqual(self.logs[0].levelno, level)

    def test_level_filter(self):
        """
        The handler is configured to emit only logs with a minimum
        level.
        """
        self.logs.level = WARNING

        self.logger.info('Repositioning antenna.')

        # The log message didn't pass the level filter, so it did not
        # get emitted.
        self.assertEqual(self.logs.records, [])

        self.logger.warning('Antenna malfunction.')

        # Now the log message is emitted.
        self.assertEqual(len(self.logs.records), 1)
