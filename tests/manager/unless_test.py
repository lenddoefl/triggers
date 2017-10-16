# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from unittest import TestCase

from triggers.manager import TriggerManager, trigger_managers
from triggers.runners import ThreadingTaskRunner
from triggers.storage_backends.base import storage_backends
from triggers.storage_backends.cache import CacheStorageBackend
from triggers.testing import DevNullTask, TriggerManagerTestCaseMixin


class TriggerManagerUnlessTestCase(TriggerManagerTestCaseMixin, TestCase):
    """
    Defines tests that focus on tasks that can be abandoned once
    certain triggers fire.
    """
    def setUp(self):
        super(TriggerManagerUnlessTestCase, self).setUp()

        storage = storage_backends.get('cache', uid=self._testMethodName) # type: CacheStorageBackend
        storage.cache.clear()

        self.manager = trigger_managers.get('default', storage=storage) # type: TriggerManager

    def test_abandoned_task(self):
        """
        Configuring a task so that it won't run if a certain trigger
        fires.
        """
        self.manager.update_configuration({
            't_alpha': {
                'run':      DevNullTask.name,
                'after':    ['__sessionFinalized'],
                'unless':   ['__finalizedWithoutSteps'],
            },
        })

        self.manager.fire('__finalizedWithoutSteps')
        ThreadingTaskRunner.join_all()
        self.assertInstanceAbandoned('t_alpha#0')

        self.manager.fire('__sessionFinalized')
        ThreadingTaskRunner.join_all()
        self.assertInstanceAbandoned('t_alpha#0')

    def test_abandoned_task_complex(self):
        """
        Configuring a task so that it won't run if a set of triggers
        fire.
        """
        self.manager.update_configuration({
            't_alpha': {
                'run':      DevNullTask.name,
                'after':    ['dataReceived', '__sessionFinalized'],
                'unless':   ['e_bureauCheck', '__finalizedWithoutSteps'],
            },
        })

        self.manager.fire('__finalizedWithoutSteps')
        ThreadingTaskRunner.join_all()
        # Abandonment criteria not satisfied yet; instance is not
        # abandoned.
        self.assertInstanceUnstarted('t_alpha#0')

        self.manager.fire('__sessionFinalized')
        ThreadingTaskRunner.join_all()
        self.assertInstanceUnstarted('t_alpha#0')

        self.manager.fire('e_bureauCheck')
        ThreadingTaskRunner.join_all()
        # Instance is now abandoned.
        self.assertInstanceAbandoned('t_alpha#0')

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()
        self.assertInstanceAbandoned('t_alpha#0')

    def test_abandoned_task_allowing_multiple(self):
        """
        Configuring abandonment criteria for a task that can run
        multiple times.
        """
        self.manager.update_configuration({
            't_alpha': {
                'run':      DevNullTask.name,
                'after':    ['creditsDepleted'],
                'andEvery': '_finishStep',
                'unless':   ['__deviceDisabled'],
            },
        })

        self.manager.fire('_finishStep')
        self.manager.fire('_finishStep')
        self.manager.fire('_finishStep')
        self.manager.fire('__deviceDisabled')
        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        # Because `__deviceDisabled` fired before any of the task
        # instances could start, they are all marked as abandoned.
        self.assertInstanceAbandoned('t_alpha#0')
        self.assertInstanceAbandoned('t_alpha#1')
        self.assertInstanceAbandoned('t_alpha#2')

    def test_abandoned_task_after_starting(self):
        """
        A task instance's abandonment criteria are satisfied after the
        instance started running.
        """
        self.manager.update_configuration({
            't_alpha': {
                'run':      DevNullTask.name,
                'after':    ['creditsDepleted'],
                'andEvery': '_finishStep',
                'unless':   ['__deviceDisabled'],
            },
        })

        self.manager.fire('creditsDepleted')
        self.manager.fire('_finishStep')
        self.manager.fire('__deviceDisabled')
        self.manager.fire('_finishStep')
        ThreadingTaskRunner.join_all()

        # The first instance ran before `__deviceDisabled` fired, so it
        # is not marked as abandoned.
        self.assertInstanceFinished('t_alpha#0', {})
        self.assertInstanceAbandoned('t_alpha#1')

    def test_abandoned_clone(self):
        """
        Creating a copy of an existing task instance should also copy
        its abandon state.
        """
        self.manager.update_configuration({
            't_alpha': {
                'run':      DevNullTask.name,
                'after':    ['dataReceived'],
                'unless':   ['e_bureauCheck', '__finalizedWithoutSteps'],
            },
        })

        self.manager.fire('__finalizedWithoutSteps')
        ThreadingTaskRunner.join_all()
        # Abandonment criteria not satisfied yet; instance is not
        # abandoned.
        self.assertInstanceUnstarted('t_alpha#0')

        # Create a copy of the instance.
        with self.manager.storage.acquire_lock() as writable_storage: # type: CacheBackend
            writable_storage.clone_instance(writable_storage['t_alpha#0'])
            writable_storage.save()

        # Quick sanity check.
        self.assertInstanceUnstarted('t_alpha#1')

        self.manager.fire('e_bureauCheck')
        ThreadingTaskRunner.join_all()

        # The cloned instance inherited its parent's abandon state.
        self.assertInstanceAbandoned('t_alpha#0')
        self.assertInstanceAbandoned('t_alpha#1')
