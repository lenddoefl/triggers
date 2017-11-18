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


class TriggerManagerReplayFailedTestCase(TriggerManagerTestCaseMixin, TestCase):
    """
    Defines tests that focus on replaying failed task instances.
    """
    def setUp(self):
        super(TriggerManagerReplayFailedTestCase, self).setUp()

        storage = storage_backends.get('cache', uid=self._testMethodName) # type: CacheStorageBackend
        storage.cache.clear()

        self.manager = trigger_managers.get('default', storage=storage) # type: TriggerManager

    def test_replay_failed_task(self):
        """
        Replaying a failed task (e.g., after fixing a problem with the
        stored data that caused the failure).
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

        # Quick sanity check.
        self.assertInstanceFailed('t_alpha#0', RuntimeError)
        self.assertInstanceMissing('t_bravo#0')

        self.assertUnresolvedTasks(['t_alpha', 't_bravo'])

        # Failed instances are considered unresolved.
        self.assertUnresolvedInstances(['t_alpha#0'])

        # Simulate changing conditions that will cause the task to run
        # successfully when it is replayed.
        self.manager.update_configuration({
            't_alpha': {
                'after': ['dataReceived'],
                'run':   PassThruTask.name,
            },
        })

        self.manager.replay_failed_task('t_alpha#0')
        ThreadingTaskRunner.join_all()

        # The original instance is marked as replayed.
        self.assertInstanceReplayed('t_alpha#0')

        # A new task instance was created for the replay.
        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                'dataReceived': {},
            },
        })

        # Once the replayed task finishes successfully, it cascades
        # like nothing unusual happened whatsoever.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {},
                    },
                },
            },
        })

        self.assertUnresolvedTasks([])
        # The replayed instance is considered resolved.
        self.assertUnresolvedInstances([])

    def test_replay_failed_task_with_different_kwargs(self):
        """
        Replaying a failed task with different kwargs.
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

        # Note that we pass along some trigger kwargs; this will
        # be important later.
        self.manager.fire('dataReceived', {'random': 'filbert'})
        ThreadingTaskRunner.join_all()

        # Quick sanity check.
        self.assertInstanceFailed('t_alpha#0', RuntimeError)
        self.assertInstanceMissing('t_bravo#0')

        self.assertUnresolvedTasks(['t_alpha', 't_bravo'])
        self.assertUnresolvedInstances(['t_alpha#0'])

        # Simulate changing conditions that will cause the task to run
        # successfully when it is replayed.
        self.manager.update_configuration({
            't_alpha': {
                'after': ['dataReceived'],
                'run':   PassThruTask.name,
            },
        })

        # When replaying a failed task, you have to specify which
        # triggers you want to change kwargs for!
        self.manager.replay_failed_task(
            instance_name = 't_alpha#0',

            replacement_kwargs = {
                # I think that's the last of them.
                # Or at least, that's the last one I'm using in this
                # test case.
                'dataReceived': {
                    'name': 'Princess Luna',
                },

                # You can put whatever you want here.
                # Just be careful not to cause another task failure!
                'extra': {
                    'unused': True,
                },
            },
        )
        ThreadingTaskRunner.join_all()

        # The original instance is marked as replayed.
        self.assertInstanceReplayed('t_alpha#0')

        # A new task instance was created for the replay.
        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                # Note that the ``replacement_kwargs``
                # completely replace the trigger kwargs!
                'dataReceived': {
                    'name': 'Princess Luna',
                    # 'random': 'filbert',
                },

                'extra': {
                    'unused': True,
                },
            },
        })

        # Once the replayed task finishes successfully, it cascades
        # like nothing unusual happened whatsoever.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {
                            'name': 'Princess Luna',
                        },

                        'extra': {
                            'unused': True,
                        },
                    },
                },
            },
        })

        self.assertUnresolvedTasks([])
        self.assertUnresolvedInstances([])

    def test_cannot_replay_non_failed_task(self):
        """
        Attempting to replay a task that didn't fail.
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
            self.manager.replay_failed_task('t_alpha#0')
