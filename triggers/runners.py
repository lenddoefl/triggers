# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from abc import ABCMeta, abstractmethod as abstract_method
from distutils.version import LooseVersion
from threading import Thread, current_thread
from typing import Any, Dict, List, NoReturn, Text, Union
from uuid import uuid4

from celery import current_app
from celery.app.trace import trace_task
from celery.result import AsyncResult, EagerResult
from celery.task import Task
from class_registry import EntryPointClassRegistry
from django import get_version
from six import string_types, text_type, with_metaclass

from triggers.importlib import dl
from triggers.itertools import merge_dict_recursive
from triggers.manager import TriggerManager, trigger_managers
from triggers.storages.base import storage_backends
from triggers.task import TriggerTask
from triggers.types import TaskInstance

__all__ = [
    'BaseTaskRunner',
    'CeleryTaskRunner',
    'DEFAULT_TASK_RUNNER',
    'ThreadingTaskRunner',
    'autodiscover_celery_tasks',
    'resolve_celery_task',
    'task_runners',
]


class BaseTaskRunner(with_metaclass(ABCMeta)):
    """
    A task runner is a class that accepts a task name and some kwargs
    and does something with them (e.g., call a Celery task, invoke an R
    function, etc.).
    """
    name = None # type: Text
    """
    Unique identifier for this task runner type.  This is the value
    that should be specified in the task's `using` attribute.

    E.g.::

       't_someTask': {
           'run':      '...',
           'using':    'celery', <-- This guy right here.
           'after':    [...],
       },
    """

    @abstract_method
    def run(self, manager, task_instance):
        # type: (TriggerManager, TaskInstance) -> NoReturn
        """
        Runs the specified task.

        Note:
            - The manager will acquire lock on the storage backend
              before invoking this method.
            - The manager will call the storage backend's ``save``
              method after this method returns.
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )

    def resolve(self, target):
        # type: (Any) -> Union[Task, TriggerTask]
        """
        Resolves a value into a runnable task.
        """
        # ``target`` usually comes from ``TaskInstance.config.run``
        # (i.e., it's the name of a Celery task).
        if isinstance(target, string_types):
            target = resolve_celery_task(target)

        if isinstance(target, type) and issubclass(target, TriggerTask):
            target = target()

        if not isinstance(target, TriggerTask):
            # In theory, we could convert any callable into a Celery
            # task, but it would cause side effects that are a bit
            # tricky to reverse (e.g., registering phantom tasks in
            # ``current_app``), so instead we will treat this as an
            # exceptional case.

            # But, just for future reference...
            # target = current_app.task(task_body(target))

            raise TypeError(
                '{runner} is not compatible with this task type '
                '(expected {expected}, actual {actual}).'.format(
                    actual      = type(target).__name__,
                    expected    = TriggerTask.__name__,
                    runner      = type(self).__name__,
                ),
            )

        # Ensure that the task is bound to the current app.  Normally
        # Celery would handle this for us, but since we're bypassing
        # Celery here....
        #
        # Note that we only do this if the task isn't already bound,
        # just in case the task's ``on_bound`` method isn't idempotent.
        if not target.__bound__:
            target.bind(current_app)

        return target

    @staticmethod
    def _prepare_task_kwargs(manager, task_instance):
        # type: (TriggerManager, TaskInstance) -> Dict
        """
        Prepares kwargs that will be passed to the task.
        """
        try:
            manager_key = getattr(manager, trigger_managers.attr_name)
        except AttributeError:
            raise RuntimeError(
                'Unable to find `{type}.{attr}`; try using '
                '`{mod}.trigger_managers` to load the trigger manager.'.format(
                    attr    = trigger_managers.attr_name,
                    mod     = trigger_managers.__module__,
                    type    = type(manager).__name__,
                ),
            )

        try:
            storage_key = getattr(manager.storage, storage_backends.attr_name)
        except AttributeError:
            raise RuntimeError(
                'Unable to find `{type}.{attr}`; try using '
                '`{mod}`.storages to load the storage backend.'.format(
                    attr    = storage_backends.attr_name,
                    mod     = storage_backends.__module__,
                    type    = type(manager.storage).__name__,
                ),
            )

        return {
            # Prepend some kwargs so that we can look up the
            # stored config/status later when Celery executes
            # the task.
            'instance_name': task_instance.name,

            # Include details that the task can use to create its own
            # manager instance (e.g., so that it can fire other
            # triggers, update the instance status, etc.).
            'manager_type': manager_key,
            'storage_type': storage_key,

            'storage_uid': manager.storage.uid,

            #
            # Merge the task kwargs recursively with the instance
            # kwargs.
            #
            # This could result in some unexpected stuff happening if
            # the task's kwargs get changed at runtime, which is why
            # one of the first things `task_body` does is store
            # the actual kwargs it received in the task instance
            # metadata.
            #
            # :py:func:`task_body`
            #
            'trigger_kwargs': merge_dict_recursive(
                task_instance.config.with_params,
                task_instance.kwargs,
            ),
        }


def autodiscover_celery_tasks():
    """
    Attempts to load celery tasks for Django applications.
    """
    django_version = LooseVersion(get_version())
    # App configs were introduced in Django 1.7.
    if django_version.version[0:2] < [1, 7]:
        from django.conf import settings
        from importlib import import_module

        packages =\
            (import_module(app).__name__ for app in settings.INSTALLED_APPS)
    else:
        from django.apps import apps
        packages = (m.module.__name__ for m in apps.get_app_configs())

    current_app.loader.autodiscover_tasks(packages)


def resolve_celery_task(target, autoload=True):
    # type: (Text, bool) -> Union[TriggerTask, Task]
    """
    Given the name of a Celery task, looks up the corresponding class.

    :param target:
        Task name.

    :param autoload:
        Whether to trigger the Celery app's task loader (if needed).
    """
    if autoload:
        # Ensure any pending decorators are resolved.
        current_app.finalize()

        try:
            return current_app.tasks[target]
        except KeyError:
            pass

        # Ensure that tasks are loaded before giving up.
        autodiscover_celery_tasks()

    try:
        return current_app.tasks[target]
    except KeyError:
        raise ValueError(
            '{task_name!r} is not a registered Celery task.'.format(
                task_name = target,
            ),
        )


class CeleryTaskRunner(BaseTaskRunner):
    """
    Runs trigger tasks by calling Celery tasks.
    """
    name = 'celery'

    def run(self, manager, task_instance):
        # type: (TriggerManager, TaskInstance) -> NoReturn
        # If Celery is operating in eager mode, a deadlock will occur
        # when the Celery task attempts to acquire lock on the
        # storage backend.
        if current_app.conf.CELERY_ALWAYS_EAGER:
            raise ValueError(
                'Cannot invoke Celery task in eager mode '
                '(task would compete with manager for storage backend lock).',
            )

        task = self.resolve(task_instance.config.run)

        result =\
            task.apply_async(
                countdown = task_instance.cooldown,
                kwargs = self._prepare_task_kwargs(manager, task_instance),
                retries = task_instance.depth,
            ) # type: AsyncResult

        # At this point, the celery task is (more or less)
        # irrevocably scheduled for execution.  Technically,
        # marking the task as scheduled in the storage
        # backend doesn't happen atomically, but this setup
        # should be good enough.

        # Quick sanity check; an uncaught exception is far easier to
        # debug than a bunch of task instances with incorrect status!
        if isinstance(result, EagerResult):
            raise ValueError(
                '{name} invoked Celery task {task} synchronously!'.format(
                    name = task_instance.name,
                    task = result.task_name,
                ),
            )

    def resolve(self, target):
        task = resolve_celery_task(target)

        # The task must have a supported type, or else it could
        # really screw things up.
        if not isinstance(task, TriggerTask):
            raise TypeError(
                '{actual_type} is not compatible with {runner} '
                '(expected TriggerType).'.format(
                    actual_type = type(task).__name__,
                    runner      = type(self).__name__,
                ),
            )

        return task


class ThreadingTaskRunner(BaseTaskRunner):
    """
    Executes trigger tasks asynchronously by invoking them in threads.

    IMPORTANT:  Each thread has its own database connection, which may
    cause weird things to happen during unit tests (by default, unit
    tests use transactions to optimize setup/teardown performance, but
    this prevents other connections from seeing changes made).

    With a few tweaks, you could also use this as a template for
    MultiprocessingTaskRunner:

    - Close all DB/cache connections before starting the child
      process.
    - Use shared state to keep track of all child processes.  This
      is particularly important if child processes fork their own
      processes (more common than you'd think, considering that tasks
      fire their own triggers when they finish successfully).

    References:
      - https://docs.python.org/2/library/multiprocessing.html#sharing-state-between-processes
    """
    name = 'threading'

    allow_python_path_target = False
    """
    Whether to allow :py:meth:`resolve` to try to interpret incoming
    values as Python paths.
    
    For security reasons, this should be set to ``False``, but it may be
    useful/safe to enable in some cases (e.g., during unit tests).
    """

    @classmethod
    def join_all(cls):
        """
        Wait for all active threads to finish.
        """
        #
        # Note that we do want to allow invoking this method on any
        # thread, just in case we need to call it from the context of
        # e.g., a Django webapp worker process.
        #
        # That said, you can't call :py:meth:`Thread.join_all` on the
        # current thread (you'll get a RuntimeError), so we still have
        # to impose a few limits.
        #
        # https://docs.python.org/2/library/threading.html#threading.Thread.join
        #
        if current_thread() in _threads:
            raise ValueError(
                'Cannot call `join_all` from child thread {thread!r}.'.format(
                    thread = current_thread(),
                ),
            )

        while _threads:
            _threads.pop(0).join()

        # Return statement not strictly necessary, but it's handy in
        # case you want to put a breakpoint at the end of this method.
        return

    def run(self, manager, task_instance):
        # type: (TriggerManager, TaskInstance) -> NoReturn
        task = self.resolve(task_instance.config.run)

        #
        # Wrap the task inside a function that simulates a real Celery
        # worker request as closely as possible.
        #
        # Each Celery worker instance spins up a TaskPool which
        # processes incoming task requests.  For performance reasons,
        # it's not practical to use a real TaskPool, but we can still
        # simulate its operation.
        #
        # :py:class:`celery.concurrency.prefork.TaskPool`
        #
        def wrapper(*args, **kwargs):
            # This must be a string, or else we'll get an
            # AttributeError.
            task_id = text_type(uuid4())

            # Based on a template found in Celery unit tests.
            # :py:func:`celery.tests.case.body_from_sig`
            request = {
                'id':       task_id,
                'retries':  task_instance.depth,
                'task':     task.name,

                # These will be set later.
                'args':     (),
                'kwargs':   {},

                #
                # :py:class:`ThreadingTaskRunner` does not respect
                # cooldown.
                #
                # At some point, we might change this, but for now, the
                # only time we use :py:class:`ThreadingTaskRunner` is
                # in unit tests where cooldown would be very annoying.
                #
                'eta': None,

                # These attributes should remain empty, to match the
                # behavior of CeleryTaskRunner.
                'callbacks':    [],
                'errbacks':     [],
                'utc':          None,
                'expires':      None,
            }

            try:
                # :py:func:`trace_task` ensures that handlers get
                # executed correctly.
                return trace_task(
                    task    = task,
                    uuid    = task_id,
                    args    = args,
                    kwargs  = kwargs,
                    request = request,
                    app     = current_app,
                )
            finally:
                task.cleanup_thread()

        thread = Thread(
            # :bc: Python 2 thread names must be ASCII-compatible.
            name = task_instance.name.encode('ascii', errors='replace'),

            target  = wrapper,
            kwargs  = self._prepare_task_kwargs(manager, task_instance),
        )

        # Add the thread to a list so that we can keep track of it.
        # This is particularly useful for unit tests and other contexts
        # where we need to wait for all threads to finish before
        # continuing.
        _threads.append(thread)

        #
        # We could have a race condition here if another thread invokes
        # :py:meth:`ThreadingTaskRunner.join_all` before we reach this
        # line.
        #
        # That's a really unusual (and preventable) case, though.  If
        # you get "cannot join thread before it is started" errors,
        # check to see if there's a way to consolidate functionality
        # onto a single thread.
        #
        # (yes, we could mitigate this issue by moving
        # ``thread.start()`` before ``_threads.append(thread)``, but
        # that just trades one set of potential problems for another)
        #
        thread.start()

    def resolve(self, target):
        # type: (Any) -> Union[Task, TriggerTask]
        # This is basically the same as the superclass method, except
        # that it will conditionally interpret ``target`` as a Python
        # path.
        if isinstance(target, string_types):
            try:
                target = resolve_celery_task(target)
            except ValueError:
                if self.allow_python_path_target:
                    target = dl(target)
                else:
                    raise

        return super(ThreadingTaskRunner, self).resolve(target)


_threads = [] # type: List[Thread]


DEFAULT_TASK_RUNNER = CeleryTaskRunner


task_runners =\
    EntryPointClassRegistry(
        attr_name   = 'triggers__registry_key',
        group       = 'triggers.runners',
    ) # type: Union[EntryPointClassRegistry, Dict[Text, BaseTaskRunner]]
"""
Registry of task runners available to the trigger manager.
"""
