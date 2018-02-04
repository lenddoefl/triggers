# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from datetime import datetime
from typing import Dict, List, Mapping, Optional, Text, Union

from class_registry import EntryPointClassRegistry
from six import itervalues

from triggers.storages.base import BaseTriggerStorage
from triggers.types import TaskConfig, TaskInstance

__all__ = [
    'TriggerManager',
    'trigger_managers',
]


class TriggerManager(object):
    """
    Fires triggers, runs tasks, also makes julienne fries.
    """
    triggers__registry_key = None # type: Text
    """
    Reverse lookup for the trigger manager's key in the
    :py:data:`trigger_managers` registry.

    .. important::

       This value is set automatically at runtime!

    References:

       - :py:data:`trigger_managers`
       - :py:meth:`EntryPointClassRegistry.__init__`
    """

    def __init__(self, storage):
        # type: (BaseTriggerStorage) -> None
        """
        :param storage:
            Storage backend for configuration, status, etc.
        """
        super(TriggerManager, self).__init__()

        self.storage = storage

    @property
    def default_task_runner_name(self):
        # type: () -> Text
        """
        Returns the name of the default task runner that will be used to
        execute task instances.

        .. note::
            This property only determines the *default* task runner
            type; if the task configuration contains a ``using`` clause,
            then that will be used instead.

        .. important::
            To change the default task runner, you must create a
            subclass and override this method.

            When the task instance runs, it will create a new trigger
            manager instance, with the same type as the one that
            scheduled the instance for execution.

            This is super important if you want cascades to use the
            correct runner!

            The following example is incorrect; the task instance will
            use the wrong task runner to handle cascades:

            .. code-block:: python

                trigger_manager = TriggerManager(...)
                trigger_manager.default_task_runner_name = 'custom'

                trigger_manager.fire(...)

            This is the correct way to customize the default task
            runner:

            .. code-block:: python

                class CustomTriggerManager(TriggerManager):
                    default_task_runner_name = 'custom'

                trigger_manager = CustomTriggerManager(...)
                trigger_manager.fire(...)

            .. note::
                Don't forget to register your custom trigger manager in
                your project's ``trigger.managers`` entry points!
        """
        from triggers.runners import DEFAULT_TASK_RUNNER
        return DEFAULT_TASK_RUNNER.name

    def update_configuration(self, configuration):
        # type: (Mapping[Text, Mapping]) -> None
        """
        Updates and persists the trigger configuration.

        This is generally used at the start of a session to initialize
        the trigger configuration, but it could also be used to update
        the configuration of a session already in progress.

        .. warning::

           The trigger manager will NOT apply previously-fired triggers
           to the new configuration!

           Additionally, bad things can happen if you replace trigger
           tasks that has unresolved task instances.  Try really hard
           not to do that.

           I guess what I'm trying to say here is, only call this
           method at the start of the session, unless you are 110% sure
           that you know exactly what you are doing!

        :param configuration:
            Dict containing new trigger task definitions.

            In the event of a conflict, the trigger tasks in this dict
            will replace the existing ones with the same name(s).
        """
        with self.storage.acquire_lock() as writable_storage: # type: BaseTriggerStorage
            # Note that we only update the configuration; we do not
            # attempt to apply previously-fired triggers, create
            # instances, etc.
            #
            # This is extremely difficult to do properly, and in some
            # cases it may even be impossible.  Examples of some really
            # nasty edge cases:
            #
            # - Adding a new task after all of the triggers in both its
            #   ``after`` and ``unless`` clauses have fired - should
            #   the new instance be scheduled or abandoned?
            #
            # - Adding a new task with ``andEvery`` - how to determine
            #   how many task instances to create?
            #
            # - Changing the configuration for a task that already has
            #   unstarted instance(s).  Lots of potential for weird
            #   things to happen there!
            #
            # And so on.
            writable_storage.update_configuration(configuration)
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
        with self.storage.acquire_lock() as writable_storage: # type: BaseTriggerStorage
            # Keep track of kwargs for each fired trigger.  In
            # particular, this allows us to correctly populate
            # ``kwargs`` when creating new instances for tasks that
            # have ``andEvery``.
            latest_kwargs = writable_storage.latest_kwargs

            for task_config in itervalues(writable_storage.tasks): # type: TaskConfig
                if not task_config.uses_trigger(trigger_name):
                    continue

                # Ensure we have a list (Python 3 compat).
                task_instances =\
                    list(itervalues(
                        writable_storage.instances_of_task(task_config)
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
                    new_instance = writable_storage.create_instance(
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
                        self.update_instance_status(
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
            writable_storage.save()

            for task_instance in tasks_ready:
                self._schedule_task(task_instance)

        self._post_fire(trigger_name, tasks_ready)

    def skip_failed_instance(self, failed_instance, cascade=False, result=None):
        # type: (Optional[Text, TaskInstance], bool, Optional[Mapping]) -> None
        """
        Marks a failed task instance as skipped.

        Note: This change is persisted immediately!

        :param failed_instance:
            The name of, or reference to, the task instance to update.

        :param cascade:
            Whether to simulate a cascade (fire the skipped task's name
            as a trigger).

        :param result:
            Simulated result from the skipped task.
            Only used when ``cascade=True``.

        :raise:
            - ValueError if the corresponding task is not failed.
        """
        if not isinstance(failed_instance, TaskInstance):
            failed_instance = self.storage[failed_instance]

        if not failed_instance.can_skip:
            raise ValueError(
                'Instance "{instance}" in {status} state '
                'cannot be skipped!'.format(
                    instance    = failed_instance,
                    status      = failed_instance.status,
                ),
            )

        if result is None:
            result = {}

        self.update_instance_status(
            cascade         = cascade,
            cascade_kwargs  = result,
            status          = TaskInstance.STATUS_SKIPPED,
            task_instance   = failed_instance,

            metadata = {
                'cascade':  cascade,
                'result':   result,
            },
        )

        self._post_skip(failed_instance, cascade)

    def replay_failed_instance(self, failed_instance, replacement_kwargs=None):
        # type: (Optional[Text, TaskInstance], Optional[Mapping]) -> None
        """
        Replays a failed task instance, optionally with different
        kwargs.

        :param failed_instance:
            The name of, or reference to, the task instance to replay.

        :param replacement_kwargs:
            Optional replacement value for the replayed instance's
            ``trigger_kwargs``.

            Note: This will replace the trigger kwargs completely, so
            be sure to include *all* the relevant kwargs, even the ones
            that do not need to be changed!

            Important: If you do not want to modify the kwargs, set
            ``replacement_kwargs = None``; if you set
            ``replacement_kwargs = {}``, the replayed instance will be
            invoked without any kwargs!

        :raise:
            - :py:class:`ValueError` if the corresponding instance is
              not replayable.
        """
        with self.storage.acquire_lock() as writable_storage: # type: BaseTriggerStorage
            if not isinstance(failed_instance, TaskInstance):
                failed_instance = writable_storage[failed_instance]

            if not failed_instance.can_replay:
                raise ValueError(
                    'Instance "{instance}" in {status} state '
                    'cannot be replayed!'.format(
                        instance    = failed_instance,
                        status      = failed_instance.status,
                ),
            )

            # Keep the failed task; just mark it as replayed.
            failed_instance.status = TaskInstance.STATUS_REPLAYED

            # Create a new task instance for the replay, so that we can
            # keep track of the result.
            replay_task = writable_storage.clone_instance(failed_instance)

            if replacement_kwargs is not None:
                replay_task.kwargs = replacement_kwargs

            # Ensure status changes are persisted before we continue.
            writable_storage.save()

            self._schedule_task(replay_task)

        self._post_replay(failed_instance)

    def update_instance_metadata(self, task_instance, metadata):
        # type: (Union[Text, TaskInstance], Mapping) -> None
        """
        Updates a task instance's metadata.

        This method does not change the instance's status; use
        :py:meth:`update_instance_status` for that.
        """
        with self.storage.acquire_lock() as writable_storage: # type: BaseTriggerStorage
            if not isinstance(task_instance, TaskInstance):
                task_instance = writable_storage[task_instance]

            task_instance.metadata.update(metadata or {})

            self._update_timestamps(task_instance)

            writable_storage.save()

    def update_instance_status(
            self,
            task_instance,              # type: Union[Text, TaskInstance]
            status,                     # type: Text
            metadata        = None,     # type: Optional[Mapping]
            cascade         = False,    # type: bool
            cascade_kwargs  = None,     # type: Optional[Mapping]
    ):
        # type: (...) -> TaskInstance
        """
        Updates the status of a task instance.

        :param task_instance:
            The name of, or reference to, the task instance to update.

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

        :return:
            The updated TaskInstance object.

            Note that in some cases this may be a different object than
            the ``task_instance`` that was passed in (due to the way
            acquiring lock works).
        """
        with self.storage.acquire_lock() as writable_storage: # type: BaseTriggerStorage
            # Acquiring lock purges the local cache, so we need to
            # reload the instance, to ensure we aren't working with a
            # stale object.
            if isinstance(task_instance, TaskInstance):
                task_instance = task_instance.name
            task_instance = writable_storage[task_instance]

            task_instance.status = status
            task_instance.metadata.update(metadata or {})

            self._update_timestamps(task_instance, status)

            writable_storage.save()

        if cascade:
            # Cascade, triggering any tasks that depend on this one.
            self.fire(task_instance.config.name, cascade_kwargs)

        return task_instance

    def mark_instance_logs_resolved(self, task_instance):
        # type: (Union[TaskInstance, Text]) -> None
        """
        Marks the logs for the specified task instance as resolved.
        """
        self.update_instance_metadata(
            task_instance   = task_instance,
            metadata        = {TaskInstance.META_LOGS_RESOLVED: True},
        )

    def _schedule_task(self, task_instance):
        # type: (TaskInstance) -> None
        """
        Schedules a single task instance for execution.
        """
        from triggers.runners import task_runners
        runner =\
            task_runners.get(
                task_instance.config.using or self.default_task_runner_name,
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
        # but :py:meth:`_schedule_task` shouldn't have to know about
        # that!
        #
        with self.storage.acquire_lock():
            runner.run(self, task_instance)

            self.update_instance_status(
                task_instance   = task_instance.name,
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


trigger_managers =\
    EntryPointClassRegistry(
        attr_name   = 'triggers__registry_key',
        group       = 'triggers.managers',
    ) # type: Union[EntryPointClassRegistry, Dict[Text, TriggerManager]]
"""
Registry of available TriggerManager classes.

Register new trigger managers by adding ``triggers.managers`` entry
points to your project's ``setup.py``.
"""
