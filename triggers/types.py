# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from datetime import datetime
from logging import ERROR, NOTSET, getLevelName
from typing import Iterable, List, Optional, Set, Text

from six import iterkeys, python_2_unicode_compatible

from triggers.itertools import merge_dict

__all__ = [
    'TaskConfig',
    'TaskInstance',
]


@python_2_unicode_compatible
class TaskConfig(object):
    """
    Container for task configuration, so that the TriggerManager knows
    what to do when a trigger fires.
    """
    def __init__(
            self,
            name,
            after,
            run,
            unless      = None,
            using       = None,
            withParams  = None,
            andEvery    = None,
            **extra
    ):
        # type: (Text, Iterable[Text], Text, Optional[Iterable[Text]], Optional[Text], Optional[dict], Optional[Text], dict) -> None
        super(TaskConfig, self).__init__()

        self.name = name # type: Text

        # These directives define what to do, and how to do it.
        self.run            = run # type: Text
        self.with_params    = withParams or {} # type: dict
        self.using          = using # type: Text

        # These directives define the conditions under which the
        # task will (or will not) run.
        self.after      = set(after) # type: Set[Text]
        self.and_every  = andEvery # type: Optional[Text]
        self.unless     = set(unless or set()) # type: Set[Text]

        # ``andEvery`` is also required for the task to run.
        if self.and_every:
            self.after.add(self.and_every)

        # Application-specific metadata.
        self.extra = extra # type: dict

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<{type} {name!r}>'.format(
            name    = self.name,
            type    = type(self).__name__,
        )

    @property
    def after_sorted(self):
        # type: () -> List[Text]
        """
        Returns :py:attr:`after` in sorted order (convenience property
        for Django templates).
        """
        return list(sorted(self.after))

    @property
    def unless_sorted(self):
        # type: () -> List[Text]
        """
        Returns :py:attr:`unless` in sorted order (convenience property
        for Django templates).
        """
        return list(sorted(self.unless))

    def uses_trigger(self, trigger_name):
        # type: (Text) -> bool
        """
        Returns whether the specified trigger is relevant to this task.
        """
        return (
                (trigger_name in self.after)
            or  (trigger_name in self.unless)
        )

    def serialize(self):
        # type: () -> dict
        """
        Returns a serialized version of the config object so that it
        can be persisted to the backend.
        """
        return merge_dict(
            self.extra,

            {
                # Not all storage backends are compatible with sets.
                'after':    list(self.after),
                'unless':   list(self.unless),

                'andEvery':     self.and_every,
                'run':          self.run,
                'using':        self.using,
                'withParams':   self.with_params,
            },
        )


@python_2_unicode_compatible
class TaskInstance(object):
    """
    An instance of a task.

    Most tasks have a single instance per UID, but for tasks that have
    ``andEvery`` and/or replayed tasks, there may be multiple
    instances.
    """
    LOG_LEVEL_THRESHOLD = ERROR
    """
    Minimum log level that needs to be marked resolved.

    Log messages and levels have very little meaning to the vanilla
    trigger manager, but custom trigger managers use them a lot, so we
    went ahead and made it part of the base framework.

    The alternative would have been to subclass TaskInstance, but that
    made things *way* too complicated.
    """

    # Possible status values for a task instance.
    STATUS_ABANDONED    = 'abandoned'
    STATUS_FAILED       = 'failed'
    STATUS_FINISHED     = 'finished'
    STATUS_REPLAYED     = 'replayed'
    STATUS_RUNNING      = 'running'
    STATUS_SCHEDULED    = 'scheduled'
    STATUS_SKIPPED      = 'skipped'
    STATUS_UNSTARTED    = 'unstarted'

    # Keys that appear in task instance metadata.
    META_ACTUAL_KWARGS      = 'actualKwargs'
    META_ACTUAL_SHARD       = 'actualShard'
    META_COOLDOWN           = 'cooldown'
    META_DEPTH              = 'depth'
    META_EXCEPTION_CONTEXT  = 'exceptionContext'
    META_EXCEPTION_INFO     = 'exceptionInfo'
    META_EXCEPTION_TYPE     = 'exceptionType'
    META_LOG_LEVEL          = 'logLevel'
    META_LOGS_RESOLVED      = 'logsResolved'
    META_PARENT             = 'parent'
    META_RESULT             = 'result'
    META_TIMESTAMPS         = 'timestamps'

    #
    # Special names inside ``metadata['timestamps']``.
    # Note that the trigger manager also records the timestamp of each
    # status change.
    #
    # References:
    #   - :py:meth:`common.triggers.manager.TriggerManager.update_instance_status`
    #
    TIMESTAMP_CREATED       = 'created'
    TIMESTAMP_LAST_MODIFIED = 'lastModified'

    def __init__(
            self,
            name,
            config,
            status          = None,
            metadata        = None,
            kwargs          = None,
            abandonState    = None,
    ):
        # type: (Text, TaskConfig, Optional[Text], Optional[dict], Optional[dict], Optional[Iterable[Text]]) -> None
        self.name           = name # type: Text
        self.config         = config # type: TaskConfig
        self.status         = status or self.STATUS_UNSTARTED # type: Text
        self.metadata       = metadata or {} # type: dict
        self.kwargs         = kwargs or {} # type: dict
        self.abandon_state  = set(abandonState or set()) # type: Set[Text]

    def __str__(self):
        return '{name} ({status})'.format(
            name    = self.name,
            status  = self.status,
        )

    def __repr__(self):
        return '<{type} {name!r}>'.format(
            name = self.name,
            type = type(self).__name__
        )

    @property
    def can_schedule(self):
        # type: () -> bool
        """
        Returns whether this task can be scheduled.
        """
        return self.status == self.STATUS_UNSTARTED

    @property
    def can_skip(self):
        # type: () -> bool
        """
        Returns whether this task can be skipped.
        """
        return self.status == self.STATUS_FAILED

    @property
    def can_replay(self):
        # type: () -> bool
        """
        Returns whether this task can be replayed.
        """
        return self.status == self.STATUS_FAILED

    @property
    def can_abandon(self):
        # type: () -> bool
        """
        Returns whether this instance can be abandoned.
        """
        return (
                self.can_schedule
            and self.config.unless
            and self.config.unless.issubset(self.abandon_state)
        )

    @property
    def can_run(self):
        # type: () -> bool
        """
        Returns whether this instance is ready to be run (all of its
        triggers have been applied).
        """
        return (
                self.can_schedule
            and self.config.after.issubset(set(iterkeys(self.kwargs)))
            and not self.can_abandon
        )

    @property
    def cooldown(self):
        # type: () -> int
        """
        Returns number of seconds before this instance can run.
        """
        return self.metadata.get(self.META_COOLDOWN, 0)

    @property
    def depth(self):
        # type: () -> int
        """
        Returns how many ancestors this instance has.
        """
        return self.metadata.get(self.META_DEPTH, 0)

    @property
    def is_resolved(self):
        # type: () -> bool
        """
        Returns whether this instance can no longer be acted upon.
        """
        return self.status in {
            self.STATUS_ABANDONED,
            self.STATUS_FINISHED,
            self.STATUS_SKIPPED,
            self.STATUS_REPLAYED,
        }

    @property
    def last_modified(self):
        # type: () -> Optional[datetime]
        """
        Returns the "last modified" timestamp for this instance.
        """
        return (
            (self.metadata.get(self.META_TIMESTAMPS) or {})
                .get(self.TIMESTAMP_LAST_MODIFIED)
        )

    @property
    def log_level(self):
        # type: () -> int
        """
        Returns the max level of all log messages generated during this
        task instance's execution.

        In some cases, this method returns :py:data:`logging.NOTSET`:

        - No log messages generated.
        - Task instance was skipped or replayed.
        - Task instance marked as "logs addressed".

        References:
          - :py:meth:`common.triggers.task.TaskContext.get_logger_context`
        """
        return self.metadata.get(self.META_LOG_LEVEL, NOTSET)

    @property
    def log_level_name(self):
        # type: () -> Text
        """
        Similar to :py:meth:`log_level`, except it returns the name of
        the max log level, instead of the int value.
        """
        return getLevelName(self.log_level)

    @property
    def logs_relevant(self):
        # type: () -> bool
        """
        Returns whether this instance's log level is still relevant.
        """
        return self.status not in {
            self.STATUS_ABANDONED,
            self.STATUS_REPLAYED,
            self.STATUS_SKIPPED,
        }

    @property
    def logs_resolved(self):
        # type: () -> bool
        """
        Returns whether this instance's log messages have been marked
        as resolved.

        Note that this attribute is stored in the task instance, not the
        log records.  This is done to make it easier for tasks and
        custom trigger managers to access at runtime.

        Note also that unresolved logs might or might not be relevant,
        depending on the instance's status.

        References:
          - :py:meth:`log_level`
          - :py:meth:`logs_relevant`
        """
        return (
                (not self.logs_relevant)
            or  (self.log_level < self.LOG_LEVEL_THRESHOLD)
            or  self.metadata.get(self.META_LOGS_RESOLVED, False)
        )

    def apply_trigger(self, trigger_name, kwargs):
        # type: (Text, dict) -> bool
        """
        Applies the specified trigger and kwargs to the task instance.

        :return:
            Whether the trigger was applied.
        """
        applied = False

        if self.can_schedule:
            if (
                        (trigger_name not in self.kwargs)
                    and (trigger_name in self.config.after)
            ):
                self.kwargs[trigger_name] = kwargs
                applied = True

            if (
                        (trigger_name not in self.abandon_state)
                    and (trigger_name in self.config.unless)
            ):
                self.abandon_state.add(trigger_name)
                applied = True

        return applied

    def serialize(self):
        # type: () -> dict
        """
        Returns a serialized version of the status object so that it
        can be persisted to the backend.
        """
        return {
            # Not all storage backends are compatible with sets.
            'abandonState': list(self.abandon_state),

            'kwargs':   self.kwargs,
            'metadata': self.metadata,
            'status':   self.status,
            'task':     self.config.name,
        }
