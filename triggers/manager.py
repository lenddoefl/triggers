# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from datetime import datetime
from typing import Dict, Iterable, List, Mapping, Optional, Text, Union

from class_registry import EntryPointClassRegistry
from six import itervalues

from triggers.storage_backends.base import TriggerStorageBackend
from triggers.types import TaskConfig, TaskInstance

__all__ = [
    'TriggerManager',
    'trigger_managers',
]


trigger_managers =\
    EntryPointClassRegistry(
        attr_name   = 'triggers__registry_key',
        group       = 'triggers.managers',
    ) # type: Union[EntryPointClassRegistry, Dict[Text, TriggerManager]]
"""
Registry of available TriggerManager classes.
"""


class TriggerManager(object):
    """
    Fires triggers, runs tasks, also makes julienne fries.
    """
    def __init__(self, storage):
        # type: (TriggerStorageBackend) -> None
        """
        :param storage:
            Storage backend for configuration, status, etc.
        """
        super(TriggerManager, self).__init__()

        self.storage = storage

    def update_configuration(self, config):
        # type: (Mapping[Text, Mapping]) -> None
        """
        Updates and persists the trigger configuration.

        This is generally used at the start of a session to initialize
        the trigger configuration, but it could also be used to update
        the configuration of a session already in progress.

        Important: the trigger manager will NOT apply previously-fired
        triggers to the new configuration!

        :param config:
            Object containing trigger task definitions.
        """
        with self.storage.acquire_lock() as writable_storage: # type: TriggerStorageBackend
            writable_storage.update_config(config)
            writable_storage.save()

    def fire(self, trigger_name, trigger_kwargs=None):
        # type: (Text, Optional[Mapping]) -> None
        """
        Fires a trigger.

        :param trigger_name:
            Name of trigger to fire.

        :param trigger_kwargs:
            Keyword arguments to pass to invoked task(s).
        """
        if trigger_kwargs is None:
            trigger_kwargs = {}

        tasks_ready = []

        # Apply kwargs and identify tasks that are ready to fire.
        # Do this with the storage backend locked to avoid shenanigans
        # when multiple processes are operating on the same UID.
        with self.storage.acquire_lock():
            # Keep track of kwargs for each fired trigger.  In
            # particular, this allows us to correctly populate
            # ``kwargs`` when creating new instances for tasks that
            # have ``andEvery``.
            latest_kwargs = self.storage.latest_kwargs

            for task_config in itervalues(self.storage.tasks): # type: TaskConfig
                if not task_config.uses_trigger(trigger_name):
                    continue

                # Ensure we have a list (Python 3 compat).
                task_instances =\
                    list(itervalues(
                        self.storage.instances_of_task(task_config)
                    )) # type: List[TaskInstance]

                if task_instances:
                    #
                    # If the incoming trigger matches the task's
                    # ``andEvery``, then we will create a new
                    # instance only if we were unable to apply the
                    # trigger to any existing instances.
                    #
                    # This ensures we only create ONE new instance each
                    # time the trigger fires.
                    #
                    create_instance =\
                        trigger_name == task_config.and_every

                    for task_instance in task_instances:
                        if task_instance.apply_trigger(trigger_name, trigger_kwargs):
                            create_instance = False
                else:
                    # We don't have any instances yet, so create one.
                    # Note that we do this regardless of the task's
                    # ``andEvery`` setting.
                    create_instance = True

                if create_instance:
                    new_instance = self.storage.create_instance(
                        task_config = task_config,

                        #
                        # Copy ``kwargs`` from ``latest_kwargs``, but
                        # ONLY for triggers that have already fired.
                        #
                        # :py:meth:`TaskInstance.can_run` uses the
                        # instance's ``kwargs`` attribute, so we need
                        # to make sure it ONLY contains triggers that
                        # have fired so far.
                        #
                        kwargs = {
                            trigger: latest_kwargs[trigger]
                                for trigger in task_config.after
                                if (
                                        (trigger != trigger_name)
                                    and (trigger in latest_kwargs)
                                )
                        },

                        abandonState = {
                            trigger
                                for trigger in task_config.unless
                                if (
                                        (trigger != trigger_name)
                                    and (trigger in latest_kwargs)
                                )
                        },
                    )

                    new_instance.apply_trigger(trigger_name, trigger_kwargs)

                    task_instances.append(new_instance)

                for ti in task_instances:
                    if ti.can_abandon:
                        self.update_task_status(
                            ti.name,
                            TaskInstance.STATUS_ABANDONED,
                        )
                    elif ti.can_run:
                        tasks_ready.append(ti)

            latest_kwargs[trigger_name] = trigger_kwargs

            #
            # Ensure the storage backend is updated before scheduling
            # tasks.  This will prevent a task from inadvertently
            # loading stale data when it starts running.
            #
            # Note that acquiring lock does not prevent other processes
            # from loading stale data; it only prevents them from
            # writing stale data!
            #
            self.storage.save()

            for task_instance in tasks_ready:
                self._schedule_task(task_instance)

        self._post_fire(trigger_name, tasks_ready)

    def skip_failed_task(self, instance_name, cascade=False, result=None):
        # type: (Text, bool, Optional[Mapping]) -> None
        """
        Marks a failed task as skipped.

        Note: This change is persisted immediately!

        :param instance_name:
            The name of the task instance to update.

        :param cascade:
            Whether to fire the skipped task's trigger.

        :param result:
            Simulated result from the skipped task.
            Only used when ``cascade=True``.

        :raise:
            - ValueError if the corresponding task is not failed.
        """
        task_instance = self.storage[instance_name]

        if not task_instance.can_skip:
            raise ValueError(
                'Task "{task}" in {status} state cannot be skipped!'.format(
                    task    = instance_name,
                    status  = self.storage[instance_name].status,
                ),
            )

        if result is None:
            result = {}

        # Acquire lock to prevent shenanigans as we insert new metadata
        # into the existing values.
        with self.storage.acquire_lock():
            self.update_task_status(
                instance_name   = instance_name,
                status          = TaskInstance.STATUS_SKIPPED,

                metadata = {
                    'cascade':  cascade,
                    'result':   result,
                },

                # Do not use the cascade feature here, to prevent
                # deadlocks during unit tests; instead, we have to
                # wait until we release the lock.
                # cascade = cascade,
                # cascade_kwargs = result,
            )

        if cascade:
            # noinspection PyArgumentList
            self.fire(self.storage[instance_name].config.name, result)

        self._post_skip(task_instance, cascade)

    def replay_failed_task(self, instance_name, replacement_kwargs=None):
        # type: (Text, Optional[Mapping]) -> None
        """
        Replays a failed task, optionally with different kwargs.

        :param instance_name:
            The name of the task instance to update.

        :param replacement_kwargs:
            Replacement value for the replayed task's
            ``trigger_kwargs``.

            Note: This will replace the trigger kwargs completely, so
            be sure to include all the relevant kwargs, even the ones
            that do not need to be changed!

            Important: If you do not want to modify the kwargs, set
            ``replacement_kwargs = None``; if you set
            ``replacement_kwargs = {}``, the replayed task will be
            invoked without any kwargs!

        :raise:
            - ValueError if the corresponding task is not failed.
        """
        with self.storage.acquire_lock():
            failed_task = self.storage[instance_name]

            if not failed_task.can_replay:
                raise ValueError(
                'Task "{task}" in {status} state cannot be replayed!'.format(
                    task    = instance_name,
                    status  = self.storage[instance_name].status,
                ),
            )

            # Keep the failed task; just mark it as replayed.
            failed_task.status = TaskInstance.STATUS_REPLAYED

            # Create a new task instance for the replay, so that we can
            # keep track of the result.
            replay_task = self.storage.clone_instance(failed_task)

            if replacement_kwargs is not None:
                replay_task.kwargs = replacement_kwargs

            # Ensure status changes are persisted before we continue.
            self.storage.save()

            self._schedule_task(replay_task)

        self._post_replay(failed_task)

    def update_task_metadata(self, instance_name, metadata):
        # type: (Text, Mapping) -> None
        """
        Updates a task instance's metadata.

        This method does not change the instance's status; use
        :py:meth:`update_task_status` for that.
        """
        with self.storage.acquire_lock():
            task_instance = self.storage[instance_name]

            task_instance.metadata.update(metadata or {})

            self._update_timestamps(task_instance)

            self.storage.save()

    def update_task_status(
            self,
            instance_name,
            status,
            metadata = None,
            cascade = False,
            cascade_kwargs = None,
    ):
        # type: (Text, Text, Optional[Mapping], bool, Optional[Mapping]) -> None
        """
        Updates the status of a task instance.

        :param instance_name:
            The name of the task instance to update.

        :param status:
            The new status to set.
            See :py:class:`TaskInstance` for available status values.

        :param metadata:
            Metadata attributes to set.

            These can be anything, but certain keys have special
            meaning; see :py:class:`TaskInstance` for more info.

        :param cascade:
            Whether to fire this task's name as a trigger, potentially
            causing additional tasks to run.

            Note:  This should only be set to ``True`` if
            ``status="finished"``!

        :param cascade_kwargs:
            Keyword arguments to pass to :py:meth:`fire` when
            cascading.
        """
        with self.storage.acquire_lock():
            task_instance = self.storage[instance_name]

            task_instance.status = status
            task_instance.metadata.update(metadata or {})

            self._update_timestamps(task_instance, status)

            self.storage.save()

        if cascade:
            # Cascade, triggering any tasks that depend on this one.
            self.fire(task_instance.config.name, cascade_kwargs)

    def iter_instances(self):
        # type: () -> Iterable[TaskInstance]
        """
        Returns a generator for iterating over all task instances.
        """
        return itervalues(self.storage.instances)

    def get_unresolved_instances(self):
        # type: () -> List[TaskInstance]
        """
        Returns all task instances that are currently in unresolved
        state.
        """
        return [
            instance
                for instance in self.iter_instances()
                if not instance.is_resolved
        ]

    def get_instances_with_unresolved_logs(self):
        # type: () -> List[TaskInstance]
        """
        Returns all task instances that have unresolved log messages.
        """
        return [
            instance
                for instance in self.iter_instances()
                if not instance.logs_resolved
        ]

    def debug_repr(self):
        # type: () -> dict
        """
        Returns a dict representation of the trigger data, useful
        for debugging.
        """
        return self.storage.debug_repr()

    def _schedule_task(self, task_instance):
        # type: (TaskInstance) -> None
        """
        Schedules a single task instance for execution.
        """
        from triggers.runners import task_runners, DEFAULT_TASK_RUNNER
        runner =\
            task_runners.get(
                task_instance.config.using or DEFAULT_TASK_RUNNER.name,
            )

        #
        # We need to set the task instance's status to 'scheduled', but
        # just to be safe, we should wait to do this until after the
        # task is successfully scheduled.
        #
        # In order to do this without creating a race condition, we
        # must first acquire lock.
        #
        # Technically this shouldn't be necessary, since the manager
        # should already have the lock when it invokes this method,
        # but ``_schedule_task`` shouldn't have to know about that!
        #
        with self.storage.acquire_lock():
            runner.run(self, task_instance)

            self.update_task_status(
                instance_name   = task_instance.name,
                status          = TaskInstance.STATUS_SCHEDULED,
            )

    @staticmethod
    def _update_timestamps(task_instance, status=None):
        # type: (TaskInstance, Optional[Text]) -> None
        """
        Updates timestamps for a task instance.

        This method does *not* persist changes to the backend.

        :param task_instance:
            The task instance to be modified.

        :param status:
            If provided, an additional timestamp will be set that
            corresponds to this status.
        """
        # Ensure the datetime object is naive.
        # Refer to "[#dt2]" in docstring for
        # :py:class:`bson.son.SON`
        now = datetime.utcnow()

        timestamps =\
            task_instance.metadata.setdefault(
                TaskInstance.META_TIMESTAMPS,
                {},
            )

        timestamps.setdefault(TaskInstance.TIMESTAMP_CREATED, now)
        timestamps[TaskInstance.TIMESTAMP_LAST_MODIFIED] = now

        if status:
            timestamps[status] = now

    # noinspection PyMethodMayBeStatic
    def _post_fire(self, trigger_name, tasks_scheduled):
        # type: (Text, List[TaskInstance]) -> None
        """
        Post-fire hook, useful for customizing behavior when
        subclassing TriggerManager.

        Note:  The storage backend's lock has been released by the time
        this method runs.

        :param trigger_name:
            The trigger that was fired.

        :param tasks_scheduled:
            Task instances that were scheduled for execution.
        """
        pass

    # noinspection PyMethodMayBeStatic
    def _post_replay(self, task_instance):
        # type: (TaskInstance) -> None
        """
        Post-replay hook, useful for customizing behavior when
        subclassing TriggerManager.

        Note: The storage backend's lock has been released by the time
        this method runs.

        :param task_instance:
            The task instance that was replayed.
        """
        pass

    # noinspection PyMethodMayBeStatic
    def _post_skip(self, task_instance, cascade):
        # type: (TaskInstance, bool) -> None
        """
        Post-skip hook, useful for customizing behavior when
        subclassing TriggerManager.

        Note: The storage backend's lock has been released by the time
        this method runs.

        :param task_instance:
            The task instance that was marked as skipped.

        :param cascade:
            Whether the task instance cascaded.

            IMPORTANT: This method gets invoked *after* the cascade
            happens!
        """
        pass
