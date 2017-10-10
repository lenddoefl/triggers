# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from contextlib import closing, contextmanager as context_manager
from distutils.version import LooseVersion
from functools import wraps
from logging import NOTSET
from traceback import format_exc
from typing import Dict, Mapping, Optional, Text, Union

import filters as f
from celery import current_app
from celery.exceptions import MaxRetriesExceededError
from django import get_version
from django.db import connections
from six import iteritems

from triggers.exceptions import with_context
from triggers.logging.handlers import LogLevelHandler
from triggers.logging.loggers import LocalLogger, LoggerAdapter
from triggers.manager import TriggerManager, trigger_managers
from triggers.storage_backends.base import storage_backends
from triggers.types import TaskInstance

__all__ = [
    'MaxRetriesExceeded',
    'Retry',
    'StatusChange',
    'TaskContext',
    'TriggerTask',
    'task_body',
]


class TaskContext(object):
    """
    Aggregates execution parameters for a trigger task.
    """
    def __init__(
            self,
            instance_name,  # type: Text
            manager_type,   # type: Text
            storage_type,   # type: Text
            storage_uid,    # type: Text
            trigger_kwargs, # type: dict
            extra_args,     # type: tuple
            extra_kwargs    # type: dict
    ):
        self.instance_name  = instance_name
        self.manager_type   = manager_type
        self.storage_type   = storage_type
        self.storage_uid    = storage_uid
        self.trigger_kwargs = trigger_kwargs

        self.extra_args     = extra_args
        self.extra_kwargs   = extra_kwargs

        self.log_level = NOTSET
        """
        Tracks the max level of logs emitted in a logger context.

        References:
          - :py:meth:`get_logger_context`
        """

        self._manager = None # type: TriggerManager

    @property
    def manager(self):
        # type: () -> TriggerManager
        """
        Returns the correct manager instance for this task.
        """
        if self._manager is None:
            self._manager = trigger_managers.get(
                key = self.manager_type,

                storage =
                    storage_backends.get(
                        key = self.storage_type,
                        uid = self.storage_uid,
                    ),
            ) # type: TriggerManager

        # noinspection PyTypeChecker
        return self._manager

    @property
    def task_instance(self):
        # type: () -> TaskInstance
        """
        Returns the correct TaskInstance object for this task.
        """
        return self.manager.storage.instances[self.instance_name]

    @context_manager
    def get_logger_context(self, logger=None, context=None):
        """
        Returns a configured logger instance, for use as a context
        manager.

        Example usage::

           with context.get_logger_context() as logger:
             ... do stuff ...

        :param logger:
            The logger instance to use.
            If not provided, a :py:class:`LocalLogger` instance will be
            returned.

        :param context:
            Additional context vars to add to the logger.
        """
        logger =\
            LoggerAdapter(logger or LocalLogger(), {'context': context or {}}) # type: Union[LoggerAdapter, LocalLogger]

        # Track the severity of emitted logs.
        logs = LogLevelHandler()
        logger.addHandler(logs)

        with closing(logger):
            try:
                yield logger
            except Exception as e:
                # Ensure exceptions get logged, but do not prevent them
                # from propagating.
                logger.exception(
                    msg     = f.Unicode().apply(e),
                    extra   = {'context': getattr(e, 'context', {})}
                )
                raise
            finally:
                logger.removeHandler(logs)
                self.log_level =\
                    max(self.log_level, logs.max_level_emitted)

    def filter_kwargs(self, filters):
        # type: (Dict[Text, Dict[Text, f.FilterCompatible]]) -> Dict[Text, dict]
        """
        Extracts and filters values from the trigger kwargs.

        :param filters:
            Keys are the names of triggers to extract params from.
            Values are dicts used to configure FilterMapper instances.

            Note: The FilterMapper instances are configured with:
            - ``allow_missing_keys = True``
            - ``allow_extra_keys = True``

        Example::

           task_params = context.filter_kwargs({
             't_createApplicant': {
               'eflId':
                    f.Required
                 |  f.ext.Model(SubjectAssessment, field='externalId'),
             },

             'skynet': {
                'scoreVersionId'; f.Required | f.ext.Model(ScoreVersion),
             },
           })

        :raise:
          - ``ValueError`` if the trigger kwargs fail validation.
        """
        # Configure the inner filters, used to process each value
        # inside ``trigger_kwargs``.
        map_ = {
            item_key: f.Optional(default={}) | f.FilterMapper(filter_map)
                for item_key, filter_map in iteritems(filters)
        }

        filter_ =\
            f.FilterRunner(
                # Configure the outer filter, used to apply the inner
                # filters to the ``trigger_kwargs`` dict.
                starting_filter =
                    f.FilterMapper(
                        filter_map          = map_,
                        allow_missing_keys  = True,
                        allow_extra_keys    = True,
                    ),

                incoming_data = self.trigger_kwargs or {},
            )

        if not filter_.is_valid():
            raise with_context(
                exc =
                    ValueError(
                        'Invalid trigger kwargs: {errors}'.format(
                            errors = filter_.errors,
                        ),
                    ),

                context = {
                    'filter_errors': filter_.get_errors(with_context=True),
                },
            )

        return filter_.cleaned_data


class StatusChange(Exception):
    """
    Special exception class that allows a :py:class:`TriggerTask` to
    change its status to something other than "finished" or "failed".

    References:
      - :py:func:`task_body`
    """
    def __init__(self, status, metadata=None):
        # type: (Text, Optional[dict]) -> None
        """
        :param status:
            Replacement status value for the task instance.

        :param metadata:
            Metadata values to apply to the task instance.
        """
        super(StatusChange, self).__init__(status)

        self.status = status
        self.metadata = metadata


class Retry(StatusChange):
    """
    Special exception class that allows a :py:class:`TriggerTask` to
    retry itself.

    References:
      - :py:func:`task_body`
    """
    def __init__(self, metadata=None, replacement_kwargs=None, cooldown=None):
        # type: (Optional[dict], Optional[dict], Optional[int]) -> None
        """
        :param metadata:
            Metadata attributes to apply to the task instance before
            replaying it.

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

        :param cooldown:
            If set, number of seconds to wait before retrying the task.

            Note: not all task runners respect this argument!
        """
        if metadata is None:
            metadata = {}

        metadata.setdefault(TaskInstance.META_COOLDOWN, cooldown)

        # Status is changed to "failed" so that it can be replayed.
        super(Retry, self).__init__(TaskInstance.STATUS_FAILED, metadata)

        self.cooldown           = cooldown
        self.replacement_kwargs = replacement_kwargs


class MaxRetriesExceeded(MaxRetriesExceededError):
    """
    Indicates that a task tried to retry itself too many times.
    """
    pass


def task_body(target):
    """
    Decorator for trigger tasks that ensures proper cleanup, etc.
    """
    @wraps(target)
    def decorated_task(
            instance_name,  # type: Text
            manager_type,   # type: Text
            storage_type,   # type: Text
            storage_uid,    # type: Text
            trigger_kwargs, # type: dict
            *args,
            **kwargs
    ):
        # type: (...) -> Mapping
        context =\
            TaskContext(
                instance_name,
                manager_type,
                storage_type,
                storage_uid,
                trigger_kwargs,
                args,
                kwargs,
            )

        context.manager.update_task_status(
            instance_name   = context.instance_name,
            status          = TaskInstance.STATUS_RUNNING,

            metadata = {
                # Include the actual kwargs passed to the task,
                # in case the task configuration was modified at
                # runtime.
                TaskInstance.META_ACTUAL_KWARGS: context.trigger_kwargs,
            },
        )

        try:
            # Here's what you've been waiting for!
            result = target(context) or {}

            #
            # If ``result`` is not a mapping (dict), the call to
            # ``manager.update_task_status`` will blow up anyway,
            # but the error message will be a tad vague, so we'll
            # do an explicit type check so that we can provide a
            # more helpful error message.
            #
            if not isinstance(result, Mapping):
                raise with_context(
                    exc = ValueError(
                        '{task!r} must return a Mapping, '
                        'so that it can be used as kwargs '
                        'for cascading triggers.'.format(
                            task = target,
                        ),
                    ),

                    context = {
                        'actual_result': result,
                    },
                )

            # noinspection PyArgumentList
            context.manager.update_task_status(
                instance_name   = context.instance_name,
                status          = TaskInstance.STATUS_FINISHED,

                metadata = {
                    TaskInstance.META_RESULT:       result,
                    TaskInstance.META_LOG_LEVEL:    context.log_level,
                },

                # Task succeeded, so cascade and pass along
                # resulting kwargs.
                cascade = True,
                cascade_kwargs = result,
            )

            return result
        except StatusChange as e:
            # Task halted prematurely, but this was done
            # deliberately, so that the task instance can set its
            # own status.
            context.manager.update_task_status(
                instance_name   = context.instance_name,
                status          = e.status,
                metadata        = e.metadata,
            )

            if isinstance(e, Retry):
                context.manager.replay_failed_task(
                    instance_name       = context.instance_name,
                    replacement_kwargs  = e.replacement_kwargs,
                )
        except Exception as e:
            # Ensure the exception updates the task status, but
            # do not prevent it from propagating.
            context.manager.update_task_status(
                instance_name   = context.instance_name,
                status          = TaskInstance.STATUS_FAILED,

                metadata = {
                    TaskInstance.META_EXCEPTION_CONTEXT:
                        getattr(e, 'context', {}),

                    TaskInstance.META_EXCEPTION_INFO: format_exc(),

                    TaskInstance.META_EXCEPTION_TYPE:
                        '{module}.{name}'.format(
                            module  = type(e).__module__,
                            name    = type(e).__name__,
                        ),

                    TaskInstance.META_LOG_LEVEL: context.log_level,
                },
            )

            # Re-raise the exception so that failure handlers are
            # invoked.
            raise

    return decorated_task


class TriggerTask(current_app.Task):
    """
    Base functionality for a task invoked by the trigger framework.
    """
    abstract = True

    def _run(self, context):
        # type: (TaskContext) -> Optional[Mapping]
        """
        Task-specific implementation.

        :param context:
            :py:class:`TaskContext` object containing the execution
            parameters.

        :return:
            Keyword args to pass along when this task cascades.
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )

    def run(
            self,
            instance_name,  # type: Text
            manager_type,   # type: Text
            storage_type,   # type: Text
            storage_uid,    # type: Text
            trigger_kwargs, # type: dict
            *args,
            **kwargs
    ):
        # type: (...) -> Optional[Mapping]
        """
        Main task body.

        Important:  You should not invoke this method directly:
            - For synchronous operation, use ``__call__`` or ``apply``.
            - For asynchronous operation, use ``delay`` or
              ``apply_async``.

        :param instance_name:
            The name of the task instance (used by the manager to look
            up and modify task status).

        :param manager_type:
            Name of the TriggerManager type to use.

        :param storage_type:
            Name of the storage backend to load.

        :param storage_uid:
            UID to use when looking up the stored config/status values.

        :param trigger_kwargs:
            Trigger-specific kwargs, provided when each trigger was
            fired.
        """
        return task_body(self._run)(
            instance_name,
            manager_type,
            storage_type,
            storage_uid,
            trigger_kwargs,
            *args,
            **kwargs
        )

    @staticmethod
    def skip(metadata=None):
        # type: (Optional[dict]) -> StatusChange
        """
        Generates an exception that, when raised, will cause the
        trigger manager to mark the task instance as skipped.

        Important: This method returns an exception object that must be
        raised in order for the status change to be applied!

        Example usage::

           raise self.skip({'skippedBecause': 'Needs more cowbell.'})

        :param metadata:
            Metadata attributes to apply to the task instance.
        """
        return StatusChange(TaskInstance.STATUS_SKIPPED, metadata)

    def retry(
            self,
            exc                 = None,
            metadata            = None,
            replacement_kwargs  = None,
            cooldown            = None,
    ):
        # type: (Optional[Exception], Optional[dict], Optional[dict], Optional[int]) -> Retry
        """
        Generates an exception that, when raised, will cause the
        trigger manager to mark the task instance as failed and replay
        it.

        Important: This method returns an exception object that must be
        raised in order for the status change to be applied!

        Example usage::

           raise self.retry({'replayedBecause': 'I gotta have more cowbell!'})

        :param exc:
            The exception that caused the task to retry, if applicable.

            This is logged in the task instance's metadata, for
            informational purposes.

        :param metadata:
            Metadata attributes to apply to the task instance before
            replaying it.

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

        :param cooldown:
            If set, number of seconds to wait before retrying the task.

            Note: not all task runners respect this argument!
        """
        if metadata is None:
            metadata = {}

        if exc:
            metadata.update({
                TaskInstance.META_EXCEPTION_CONTEXT:
                    getattr(exc, 'context', {}),

                TaskInstance.META_EXCEPTION_INFO: format_exc(),

                TaskInstance.META_EXCEPTION_TYPE:
                    '{module}.{name}'.format(
                        module  = type(exc).__module__,
                        name    = type(exc).__name__,
                    ),
            })

        if self.request.retries >= self.max_retries:
            raise with_context(
                exc =
                    MaxRetriesExceeded(
                        'Attempting retry #{i}, '
                        'but `self.max_retries` = {max_retries}.'.format(
                            i           = self.request.retries + 1,
                            max_retries = self.max_retries,
                        ),
                    ),

                context = {
                    'replay_metadata': metadata,
                },
            )

        return Retry(metadata, replacement_kwargs, cooldown)

    # noinspection PyMethodMayBeStatic
    def cleanup_thread(self):
        """
        Cleans up after the task finishes.

        This is used primarily to prevent strange behavior during unit
        tests due to the way ThreadingTaskRunner works.

        Note:  This method is NOT invoked when the task is run by a
        Celery worker.
        """
        django_version = LooseVersion(get_version())

        if django_version.version[0:2] < [1, 8]:
            for alias in connections:
                try:
                    # noinspection PyProtectedMember
                    connection = getattr(connections._connections, alias)
                except AttributeError:
                    continue
                connection.close()
        else:
            connections.close_all()
