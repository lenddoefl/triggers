# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from unittest import TestCase

from triggers.manager import TriggerManager, trigger_managers
from triggers.runners import ThreadingTaskRunner
from triggers.storage_backends.base import storage_backends
from triggers.storage_backends.cache import CacheStorageBackend
from triggers.testing import FailingTask, PassThruTask, \
    TriggerManagerTestCaseMixin


class TriggerManagerSkipFailedTestCase(TriggerManagerTestCaseMixin, TestCase):
    """
    Defines tests that focus on skipping failed task instances.
    """
    def setUp(self):
        super(TriggerManagerSkipFailedTestCase, self).setUp()

        storage = storage_backends.get('cache', uid=self._testMethodName) # type: CacheStorageBackend
        storage.cache.clear()

        self.manager = trigger_managers.get('default', storage=storage) # type: TriggerManager

    def test_skip_failed_task(self):
        """
        Marking a failed task as skipped.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['dataReceived'],
                'run':      FailingTask.name,
            },

            't_bravo': {
                'after':    ['t_alpha'],
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFailed('t_alpha#0', RuntimeError)

        self.manager.skip_failed_task('t_alpha#0')
        self.assertInstanceSkipped('t_alpha#0')

        # Skipping a task prevents it from cascading.
        self.assertInstanceMissing('t_bravo#0')

    def test_skip_failed_task_with_cascade(self):
        """
        Marking a failed task as skipped and firing the corresponding
        trigger.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['dataReceived'],
                'run':      FailingTask.name,
            },

            't_bravo': {
                'after':    ['t_alpha'],
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFailed('t_alpha#0', RuntimeError)

        self.manager.skip_failed_task(
            instance_name = 't_alpha#0',

            # Tell the manager to cause a cascade, as if the task had
            # completed successfully.
            cascade = True,

            # Simulate the result to pass along to ``t_bravo``.
            result = {
                'rating':       '4.5',
                'popularity':   '0.7',
            },
        )
        ThreadingTaskRunner.join_all()

        # ``t_alpha`` is still marked as skipped.
        self.assertInstanceSkipped('t_alpha#0')

        # ``t_bravo`` gets run with the simulated result.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'rating':       '4.5',
                    'popularity':   '0.7',
                },
            },
        })

    def test_cannot_skip_non_failed_task(self):
        """
        Attempting to skip a task that didn't fail.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['dataReceived'],
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        with self.assertRaises(ValueError):
            self.manager.skip_failed_task('t_alpha#0')
