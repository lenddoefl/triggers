# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from abc import ABCMeta
from pprint import pformat
from typing import List, Mapping, Optional, Text
from unittest import TestCase

import filters as f
from six import with_metaclass

from triggers import runners
from triggers.manager import TriggerManager
from triggers.patcher import AttrPatcher
from triggers.task import TaskContext, TriggerTask
from triggers.types import TaskInstance

__all__ = [
    'DevNullTask',
    'FailingTask',
    'PassThruTask',
    'SelfRetryingTask',
    'SelfSkippingTask',
    'TriggerManagerTestCaseMixin',
    'name_matches_classpath',
]


def name_matches_classpath(cls):
    """
    Decorates a class, ensuring that its ``name`` attribute matches its
    classpath.

    This is useful for providing a convenient way to configure
    :py:class:`TriggerTask` subclasses in trigger configurations during
    unit tests.
    """
    cls.name = '{cls.__module__}.{cls.__name__}'.format(cls=cls)
    return cls


@name_matches_classpath
class PassThruTask(TriggerTask):
    """
    A simple trigger task that returns its kwargs so that tests can
    verify that the correct values were passed in.
    """
    def _run(self, context):
        # type: (TaskContext) -> Optional[Mapping]
        return {'kwargs': context.trigger_kwargs}


@name_matches_classpath
class DevNullTask(TriggerTask):
    """
    A simple trigger task that returns an empty result, used to make
    sure we don't "cheat" during more complex unit tests.
    """
    def _run(self, context):
        # type: (TaskContext) -> Optional[Mapping]
        return {}


@name_matches_classpath
class FailingTask(TriggerTask):
    """
    A task that raises an exception when it runs.
    """
    def _run(self, context):
        # type: (TaskContext) -> Optional[Mapping]
        raise RuntimeError("You weren't supposed to see that.")


@name_matches_classpath
class SelfSkippingTask(TriggerTask):
    """
    A task that marks itself as skipped when it runs.
    """
    def _run(self, context):
        # type: (TaskContext) -> Optional[Mapping]
        raise self.skip({'kwargs': context.trigger_kwargs})


@name_matches_classpath
class SelfRetryingTask(TriggerTask):
    """
    A task that retries itself a certain number of times when it runs.
    """
    def _run(self, context):
        # type: (TaskContext) -> Optional[Mapping]
        params =\
            context.filter_kwargs({
                'retries': {
                    'max':
                            f.Type(int)
                        |   f.Optional(default=self.max_retries)
                        |   f.Min(1),
                },
            })

        if self.request.retries < params['retries']['max']:
            raise self.retry()

        return {'count': self.request.retries}


class TriggerManagerTestCaseMixin(with_metaclass(ABCMeta, TestCase)):
    """
    Extends the base TestCase with useful functions for testing trigger
    manager classes.
    """
    manager = None # type: TriggerManager

    def run(self, result=None):
        # Use ThreadingTaskRunner to execute trigger tasks; it's much
        # easier to wait for a thread to finish than to wait for a
        # Celery worker to (maybe) finish and publish to the results
        # backend.
        with AttrPatcher(
                runners,
                DEFAULT_TASK_RUNNER = runners.ThreadingTaskRunner,
        ):
            # Allow unit tests to configure tasks using Python path.
            # This will let us inject one-off tasks into the trigger
            # configuration, so that we can simulate edge cases.
            with AttrPatcher(
                    runners.ThreadingTaskRunner,
                    allow_python_path_target = True,
            ):
                super(TriggerManagerTestCaseMixin, self).run(result)

    def assertInstanceStatus(self, instance_name, expected_status):
        # type: (Text, Text) -> None
        """
        Asserts that the specified task instance has the correct
        status.
        """
        # Ensure that we aren't cheating by using a locally-stored
        # value.
        self.manager.storage.invalidate_cache()

        try:
            task_instance = self.manager.storage[instance_name]
        except KeyError:
            self.fail(
                'Expected "{instance}" instance to be {status}, '
                'but it has not been created yet.'.format(
                    instance    = instance_name,
                    status      = expected_status,
                ),
            )

        if task_instance.status != expected_status:
            self.fail(
                '{task} has incorrect status '
                '(expected: {expected}, actual: {actual}):\n\n'
                '{metadata}'.format(
                    actual      = task_instance.status,
                    expected    = expected_status,
                    metadata    = pformat(task_instance.metadata),
                    task        = instance_name,
                ),
            )

    def assertInstanceAbandoned(self, instance_name):
        # type: (Text) -> None
        """
        Asserts that the specified task instance was abandoned.
        """
        self.assertInstanceStatus(instance_name, TaskInstance.STATUS_ABANDONED)

    def assertInstanceFailed(self, instance_name, exc_type):
        # type: (Text, type) -> None
        """
        Asserts that the specified task failed with the correct
        exception.
        """
        self.assertInstanceStatus(instance_name, TaskInstance.STATUS_FAILED)

        self.assertEqual(
            self.manager.storage[instance_name]
                .metadata[TaskInstance.META_EXCEPTION_TYPE],

            '{module}.{name}'.format(
                module  = exc_type.__module__,
                name    = exc_type.__name__,
            ),
        )

    def assertInstanceFinished(self, instance_name, expected_result=None):
        # type: (Text, Optional[dict]) ->  None
        """
        Asserts that the specified task instance finished successfully,
        and (optionally) that it returned the correct result.
        """
        self.assertInstanceStatus(instance_name, TaskInstance.STATUS_FINISHED)

        if expected_result is not None:
            self.assertEqual(
                self.manager.storage[instance_name].metadata['result'],
                expected_result,
            )

    def assertInstanceReplayed(self, instance_name):
        # type: (Text) -> None
        """
        Asserts that the specified task instance has been marked as
        replayed.
        """
        self.assertInstanceStatus(instance_name, TaskInstance.STATUS_REPLAYED)

    def assertInstanceSkipped(self, instance_name):
        # type: (Text) -> None
        """
        Asserts that the specified task instance has been marked as
        skipped.
        """
        self.assertInstanceStatus(instance_name, TaskInstance.STATUS_SKIPPED)

    def assertInstanceMissing(self, instance_name):
        # type: (Text) -> None
        """
        Asserts that the specified task instance hasn't been created
        yet.
        """
        try:
            instance = self.manager.storage[instance_name]

            self.fail(
                'Expected "{instance}" instance not to exist, '
                'but it was created with status "{status}".'.format(
                    instance    = instance_name,
                    status      = instance.status,
                ),
            )
        except KeyError:
            pass

    def assertInstanceUnstarted(self, instance_name):
        # type: (Text) -> None
        """
        Asserts that the specified task instance has been created, but
        not started yet.
        """
        self.assertInstanceStatus(instance_name, TaskInstance.STATUS_UNSTARTED)

    def assertUnresolvedTasks(self, task_names):
        # type: (List[Text]) -> None
        """
        Asserts that the manager has the correct unresolved tasks.

        :param task_names:
            List of task names, sorted alphabetically.
        """
        self.assertListEqual(
            list(sorted(
                t.name for t in self.manager.storage.get_unresolved_tasks()
            )),

            task_names,
        )

    def assertUnresolvedInstances(self, instance_names):
        # type: (List[Text]) -> None
        """
        Asserts that the manager has the correct unresolved instances.

        :param instance_names:
            List of instance names, sorted alphabetically.
        """
        self.assertListEqual(
            list(sorted(
                i.name for i in self.manager.storage.get_unresolved_instances()
            )),

            instance_names,
        )
