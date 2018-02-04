# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from unittest import TestCase

from triggers.manager import TriggerManager, trigger_managers
from triggers.runners import ThreadingTaskRunner
from triggers.storages.base import storage_backends
from triggers.storages.cache import CacheStorageBackend
from triggers.testing import DevNullTask, FailingTask, \
    TriggerManagerTestCaseMixin

__all__ = [
    'TriggerManagerHooksTestCase',
]


class TriggerManagerHooksTestCase(TriggerManagerTestCaseMixin, TestCase):
    """
    Defines tests that focus on how the trigger manager invokes hooks.
    """
    def run(self, result=None):
        self.post_fire_calls    = []
        self.post_replay_calls  = []
        self.post_skip_calls    = []

        # Create an alias to ``self`` so that we can use it in the
        # trigger manager hooks.
        test = self

        class PirateTriggerManager(TriggerManager):
            """
            A trigger manager that has been outfitted with stylish
            hooks (parrot and eye patch not included).
            """
            def _post_fire(self, trigger_name, tasks_scheduled):
                test.post_fire_calls.append((
                    trigger_name,

                    # Tracking instances is a bit tricky; to make
                    # things simpler, we'll log the instance name
                    # instead.
                    [instance.name for instance in tasks_scheduled],
                ))

            def _post_replay(self, task_instance):
                test.post_replay_calls.append(task_instance.name)

            def _post_skip(self, task_instance, cascade):
                test.post_skip_calls.append((task_instance.name, cascade))

        storage = storage_backends.get('cache', uid=self._testMethodName) # type: CacheStorageBackend
        storage.cache.clear()

        # Temporarily inject our custom trigger manager into the
        # registry.
        trigger_managers._get_cache()[self._testMethodName] =\
            PirateTriggerManager
        try:
            self.manager =\
                trigger_managers.get(self._testMethodName, storage=storage) # type: PirateTriggerManager

            super(TriggerManagerHooksTestCase, self).run(result)
        finally:
            trigger_managers.refresh()

    def test_hook_post_fire(self):
        """
        Subclassing the trigger manager with a post-fire hook.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['targetAcquired'],
                'run':      DevNullTask.name,
            },

            't_bravo': {
                'after':    ['targetAcquired', 't_alpha'],
                'run':      DevNullTask.name,
            },
        })

        ##
        # Easy one first.  This trigger won't cause anything to run.
        del self.post_fire_calls[:]
        self.manager.fire('foobar')

        self.assertListEqual(
            self.post_fire_calls,

            [
                ('foobar', []),
            ],
        )

        ##
        # Let's turn up the intensity a bit and trigger a task.
        # Note that the task instance will cascade when it finishes.
        del self.post_fire_calls[:]
        self.manager.fire('targetAcquired')
        ThreadingTaskRunner.join_all()

        self.assertListEqual(
            self.post_fire_calls,

            [
                ('targetAcquired', ['t_alpha#0']),
                ('t_alpha', ['t_bravo#0']),
                ('t_bravo', []),
            ],
        )

    def test_hook_post_fire_with_replay(self):
        """
        Replaying a failed task instance does not trigger the post-fire
        hook.
        """
        self.manager.update_configuration({
            't_failingTask': {
                'after':    ['fail'],
                'run':      FailingTask.name,
            },
        })

        ##
        # Set things up by running a task instance which will fail.
        del self.post_fire_calls[:]
        self.manager.fire('fail')
        ThreadingTaskRunner.join_all()

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#0', RuntimeError)

        # No surprises so far.
        self.assertListEqual(
            self.post_fire_calls,

            [
                ('fail', ['t_failingTask#0']),
            ],
        )

        ##
        # Replaying the failed task doesn't fire any triggers, so
        # the post-fire hook does not get called.
        del self.post_fire_calls[:]
        self.manager.replay_failed_instance('t_failingTask#0')
        ThreadingTaskRunner.join_all()

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#1', RuntimeError)

        self.assertListEqual(self.post_fire_calls, [])

    def test_hook_post_fire_with_skip(self):
        """
        Skipping a failed task instance may trigger the post-fire hook
        if the skipped task cascades.
        """
        self.manager.update_configuration({
            't_failingTask': {
                'after':    [],
                'andEvery': 'fail',
                'run':      FailingTask.name,
            },
        })

        ##
        # Set things up by running a task instance which will fail.
        del self.post_fire_calls[:]
        self.manager.fire('fail')
        ThreadingTaskRunner.join_all()

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#0', RuntimeError)

        # No surprises so far.
        self.assertListEqual(
            self.post_fire_calls,

            [
                ('fail', ['t_failingTask#0']),
            ],
        )

        ##
        # Skipping the task instance without cascade does not fire
        # any triggers, so the post-fire hook is not invoked.
        del self.post_fire_calls[:]
        self.manager.skip_failed_instance('t_failingTask#0', cascade=False)

        self.assertListEqual(self.post_fire_calls, [])

        ##
        # However, if we skip and cascade, this does fire a trigger.
        del self.post_fire_calls[:]
        self.manager.fire('fail')
        ThreadingTaskRunner.join_all()

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#1', RuntimeError)

        self.manager.skip_failed_instance('t_failingTask#1', cascade=True)

        self.assertListEqual(
            self.post_fire_calls,

            [
                ('fail', ['t_failingTask#1']),
                ('t_failingTask', []),
            ],
        )

    def test_hook_post_replay(self):
        """
        Subclassing the trigger manager with a post-replay hook.
        """
        self.manager.update_configuration({
            't_failingTask': {
                'after':    ['fail'],
                'run':      FailingTask.name,
            },
        })

        ##
        # Set things up by running a task instance which will fail.
        del self.post_replay_calls[:]
        self.manager.fire('fail')
        ThreadingTaskRunner.join_all()

        # The task instance failed, but we haven't replayed
        # anything yet.
        self.assertListEqual(self.post_replay_calls, [])

        ##
        # Replaying the failed task will, naturally, invoke the
        # post-replay hook.
        del self.post_replay_calls[:]
        self.manager.replay_failed_instance('t_failingTask#0')
        ThreadingTaskRunner.join_all()

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#1', RuntimeError)

        # The post-replay hook was invoked.
        self.assertListEqual(self.post_replay_calls, ['t_failingTask#0'])

        ##
        # Skipping a failed task does not invoke the post-replay
        # hook, even if it cascades.
        del self.post_replay_calls[:]
        self.manager.skip_failed_instance('t_failingTask#1', cascade=True)
        self.assertListEqual(self.post_replay_calls, [])

    def test_hook_post_skip(self):
        """
        Subclassing the trigger manager with a post-skip hook.
        """
        self.manager.update_configuration({
            't_failingTask': {
                'after':    [],
                'andEvery': 'fail',
                'run':      FailingTask.name,
            },
        })

        ##
        # Set things up by running a task instance which will fail.
        del self.post_skip_calls[:]
        self.manager.fire('fail')
        ThreadingTaskRunner.join_all()

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#0', RuntimeError)

        # The task instance failed, but we haven't skipped anything
        # yet.
        self.assertListEqual(self.post_skip_calls, [])

        ##
        # Replaying a failed task does not invoke the post-skip
        # hook.
        del self.post_skip_calls[:]
        self.manager.replay_failed_instance('t_failingTask#0')
        ThreadingTaskRunner.join_all()

        self.assertListEqual(self.post_skip_calls, [])

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#1', RuntimeError)

        ##
        # Skipping the failed instance will, naturally, invoke
        # the post-skip handler.
        self.manager.skip_failed_instance('t_failingTask#1', cascade=False)

        self.assertListEqual(
            self.post_skip_calls,
            [('t_failingTask#1', False)],
        )

        ##
        # Let's try it again, just to make sure that cascading is
        # handled correctly.
        del self.post_skip_calls[:]
        self.manager.fire('fail')
        ThreadingTaskRunner.join_all()

        # Quick sanity check (this also refreshes the task instance
        # metadata).
        self.assertInstanceFailed('t_failingTask#2', RuntimeError)

        self.manager.skip_failed_instance('t_failingTask#2', cascade=True)

        self.assertListEqual(
            self.post_skip_calls,
            [('t_failingTask#2', True)],
        )
