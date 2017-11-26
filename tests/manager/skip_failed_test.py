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

__all__ = [
    'TriggerManagerSkipFailedTestCase',
]


class TriggerManagerSkipFailedTestCase(TriggerManagerTestCaseMixin, TestCase):
    """
    Defines tests that focus on skipping failed task instances.
    """
    def setUp(self):
        super(TriggerManagerSkipFailedTestCase, self).setUp()

        storage = storage_backends.get('cache', uid=self._testMethodName) # type: CacheStorageBackend
        storage.cache.clear()

        self.manager = trigger_managers.get('default', storage=storage) # type: TriggerManager

    def test_skip_failed_instance(self):
        """
        Marking a failed task instance as skipped.
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

        self.assertUnresolvedTasks(['t_alpha', 't_bravo'])

        # Failed tasks are considered unresolved.
        self.assertUnresolvedInstances(['t_alpha#0'])

        self.manager.skip_failed_instance('t_alpha#0')
        self.assertInstanceSkipped('t_alpha#0')

        # Skipping a task prevents it from cascading.
        self.assertInstanceMissing('t_bravo#0')

        # The skipped instance is considered resolved.
        # However, ``t_bravo`` is still unresolved, since it hasn't
        # run yet.
        self.assertUnresolvedTasks(['t_bravo'])
        self.assertUnresolvedInstances([])

    def test_skip_failed_instance_with_cascade(self):
        """
        Marking a failed task instance as skipped and forcing a
        cascade.
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

        self.assertUnresolvedTasks(['t_alpha', 't_bravo'])
        self.assertUnresolvedInstances(['t_alpha#0'])

        self.manager.skip_failed_instance(
            failed_instance = 't_alpha#0',

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

        self.assertUnresolvedTasks([])
        self.assertUnresolvedInstances([])

    def test_cannot_skip_non_failed_instance(self):
        """
        Attempting to skip a task instance that didn't fail.
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
            self.manager.skip_failed_instance('t_alpha#0')
