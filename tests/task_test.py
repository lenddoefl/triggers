# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from unittest import TestCase

from triggers.manager import TriggerManager
from triggers.patcher import AttrPatcher
from triggers.runners import ThreadingTaskRunner
from triggers.storages.cache import CacheStorageBackend
from triggers.task import MaxRetriesExceeded
from triggers.testing import SelfRetryingTask, SelfSkippingTask, \
    TriggerManagerTestCaseMixin
from triggers.types import TaskInstance


class TriggerTaskTestCase(TriggerManagerTestCaseMixin, TestCase):
    """
    Unit tests for functionality that is specific to trigger tasks.

    Note that trigger tasks are tightly coupled to the
    :py:class:`TriggerManager` implementation, but the actual code
    under test lives in the trigger task classes, not the trigger
    manager.
    """
    def setUp(self):
        super(TriggerTaskTestCase, self).setUp()

        self.manager =\
            TriggerManager(CacheStorageBackend(self._testMethodName))

    def test_skip_self(self):
        """
        A task marks itself as skipped at runtime.
        """
        self.manager.update_configuration({
            't_skipper': {
                'after':    ['integrity'],
                'run':      SelfSkippingTask.name,
            },
        })

        self.manager.fire('integrity')
        ThreadingTaskRunner.join_all()

        self.assertInstanceSkipped('t_skipper#0')

        # :py:class:`SelfSkippingTask` copies trigger kwargs to the
        # instance metadata when it marks itself as skipped.
        # This will make more sense in the next test.
        task_instance = self.manager.storage.instances['t_skipper#0'] # type: TaskInstance
        self.assertEqual(task_instance.metadata['kwargs'], {'integrity': {}})

    def test_skip_self_with_metadata(self):
        """
        A task marks itself as skipped and updates its metadata at
        runtime.
        """
        self.manager.update_configuration({
            't_skipper': {
                'after':    ['integrity'],
                'run':      SelfSkippingTask.name,
            },
        })

        # :py:class:`SelfSkippingTask` copies trigger kwargs to the
        # instance metadata when it marks itself as skipped.
        kwargs = {'foo': 'bar', 'baz': 'luhrmann'}

        self.manager.fire('integrity', kwargs)
        ThreadingTaskRunner.join_all()

        self.assertInstanceSkipped('t_skipper#0')

        task_instance = self.manager.storage.instances['t_skipper#0'] # type: TaskInstance
        self.assertDictEqual(
            task_instance.metadata['kwargs'],
            {'integrity': kwargs},
        )

    def test_retry_self(self):
        """
        A task retries itself at runtime.
        """
        with AttrPatcher(SelfRetryingTask, max_retries=2):
            self.manager.update_configuration({
                't_replay': {
                    'after':        ['start'],
                    'run':          SelfRetryingTask.name,
                    'withParams':   {'retries': {'max': 2}},
                },
            })

            self.manager.fire('start')
            ThreadingTaskRunner.join_all()

        # Note that each retry creates a new task instance.
        self.assertInstanceReplayed('t_replay#0')
        self.assertInstanceReplayed('t_replay#1')
        self.assertInstanceFinished('t_replay#2', {'count': 2})

    def test_retry_self_error_too_many_retries(self):
        """
        A task retries itself too many times.
        """
        with AttrPatcher(SelfRetryingTask, max_retries=2):
            self.manager.update_configuration({
                't_replay': {
                    'after':        ['start'],
                    'run':          SelfRetryingTask.name,
                    'withParams':   {'retries': {'max': 3}},
                },
            })

            self.manager.fire('start')
            ThreadingTaskRunner.join_all()

        self.assertInstanceReplayed('t_replay#0')
        self.assertInstanceReplayed('t_replay#1')

        # After 2 replays (``SelfRetryingTask.max_retries``), the
        # task will refuse to retry itself again.
        self.assertInstanceFailed('t_replay#2', MaxRetriesExceeded)
