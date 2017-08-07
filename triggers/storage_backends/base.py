# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from abc import ABCMeta, abstractmethod as abstract_method
from collections import defaultdict
from contextlib import contextmanager as context_manager
from typing import Dict, Iterable, Optional, Text, Tuple, Union

from class_registry import EntryPointClassRegistry
from six import iteritems, itervalues, with_metaclass

from triggers.locking import Lockable
from triggers.types import TaskConfig, TaskInstance

storage_backends =\
    EntryPointClassRegistry(
        attr_name   = 'triggers__registry_key',
        group       = 'triggers.storage_backends',
    ) # type: Union[EntryPointClassRegistry, Dict[Text, TriggerStorageBackend]]
"""
Registry of storage backends available to the triggers framework.
"""


class TriggerStorageBackend(with_metaclass(ABCMeta, Lockable)):
    """
    Base functionality for trigger storage backends.
    """
    name = None # type: Text
    """
    Unique identifier used to look up this storage backend type, e.g.,
    when running celery tasks.

    References:
      - :py:data:`storage_backends`
    """

    def __init__(self, uid):
        # type: (Text) -> None
        """
        :param uid:
            Identifier that the backend can use to load the
            corresponding data.
        """
        super(TriggerStorageBackend, self).__init__()

        self.uid = uid # type: Text

        self._loaded = False # type: bool
        """
        Prevents loading data from the backend unnecessarily.
        """

        self._configs = None # type: Dict[Text, TaskConfig]
        """
        Locally-cached task configurations ("tasks").
        """

        self._instances = None # type: TaskInstanceCollection
        """
        Locally-cached task instances.
        """

        self._metas = None # type: dict
        """
        Locally-cached session metadata ("status").
        """

    def __getitem__(self, instance_name):
        # type: (Text) -> TaskInstance
        """
        Retrieves a task instance.

        Note: After being loaded from the backend, the instance caches
        the values locally.
        """
        return self.instances[instance_name]

    def __iter__(self):
        # type: () -> Iterable[TaskInstance]
        """
        Returns a generator for iterating over task instances.
        """
        self._load()
        return itervalues(self._instances)

    @abstract_method
    def _load_from_backend(self):
        # type: () -> Tuple[dict, dict, dict]
        """
        Loads configuration and status values from the backend.

        :return:
            (task config, task status, meta status)
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )

    @abstract_method
    def _save(self):
        """
        Persists changes to the backend.

        This method MAY assume that the instance owns the active lock
        for the current UID.

        References:
          - https://www.ietf.org/rfc/rfc2119.txt
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )

    @property
    def tasks(self):
        # type: () -> Dict[Text, TaskConfig]
        """
        Returns the task configurations stored in the backend.

        Note: After being loaded from the backend, the instance caches
        the values locally.
        """
        self._load()
        return self._configs

    @property
    def instances(self):
        # type: () -> TaskInstanceCollection
        """
        Returns the task instances stored in the backend.

        Note: After being loaded from the backend, the instance caches
        the values locally.
        """
        self._load()
        return self._instances

    @property
    def latest_kwargs(self):
        # type: () -> Dict[Text, dict]
        """
        Returns the most recent kwargs received for each trigger.
        """
        return self.metadata['latest_kwargs']

    def get_lock_name(self):
        # type: () -> Text
        """
        Returns the key used to lock the UID.

        References:
          - :py:class:`Lockable`
        """
        return 'triggers:{uid}:lock'.format(
            uid = self.uid,
        )

    @property
    def metadata(self):
        # type: () -> dict
        """
        Returns session metadata (status info not attached to
        individual tasks).
        """
        self._load()
        return self._metas

    @context_manager
    def acquire_lock(self, ttl=True, block=True):
        """
        Attempts to acquire a lock on the storage backend, forcing a
        reload of the locally-stored data and ensuring that no other
        tasks/processes for the same UID can write to the backend until
        the lock is released.

        It is important that you invoke this method before performing
        any actions that result in changes to the stored data.

        This helps eliminate race conditions when two or more tasks for
        the same UID are running in parallel.

        :param ttl:
            Number of seconds before the lock expires.

            If ``True`` (default), the cache's ``default_timeout``
            value is used.

        :param block:
            Determines what happens if the lock is not available:

            - ``True`` (Default): Wait until the lock is released,
              giving up after `ttl` seconds.
            - ``False``: Give up right away (by raising an exception).

        :raise:
            - :py:class:`common.cache.lock.LockAcquisitionFailed` if
              the lock is not available and ``block`` is ``False``.
        """
        if self.has_lock:
            yield self
        else:
            with super(TriggerStorageBackend, self).acquire_lock(ttl, block):
                # Ensure that we reload data from the backend, just in
                # case another process/thread made changes while we
                # weren't looking.
                if self._loaded:
                    self.invalidate_cache()

                yield self

    def clone_instance(self, task_instance):
        # type: (TaskInstance) -> TaskInstance
        """
        Installs a clone of an existing TaskInstance.

        :return:
            The cloned task instance.
        """
        return self.create_instance(
            kwargs      = task_instance.kwargs,
            task_config = task_instance.config,

            metadata = {
                TaskInstance.META_DEPTH:  task_instance.depth + 1,
                TaskInstance.META_PARENT: task_instance.name,
            },
        )

    def create_instance(self, task_config, **kwargs):
        # type: (TaskConfig, ...) -> TaskInstance
        """
        Installs a new :py:class:`TaskInstance`.

        :param kwargs:
            Additional kwargs to provide to the TaskInstance
            initializer.
        """
        self._load()

        return self._instances.create_instance(
            config  = task_config,
            status  = TaskInstance.STATUS_UNSTARTED,

            **kwargs
        )

    def instances_of_task(self, task_config):
        # type: (TaskConfig) -> Dict[Text, TaskInstance]
        """
        Returns all instances that have been created for the specified
        task.
        """
        self._load()

        return self._instances.get_from_task(task_config)

    def close(self, *args, **kwargs):
        """
        Closes the active connection to the storage backend.
        """
        pass

    def save(self):
        """
        Persists changes to the backend.
        """
        if not self.has_lock:
            raise RuntimeError('You must ``acquire_lock`` before saving!')

        # If we haven't loaded anything yet, then it's guaranteed that
        # we haven't modified anything yet, either.
        if self._loaded:
            self._save()

    def invalidate_cache(self):
        """
        Invalidates locally-cached values so that they are reloaded
        from the backend on next access.
        """
        self._loaded    = False
        self._configs   = None
        self._instances = None
        self._metas     = None

    def update_config(self, config_dict):
        # type: (dict) -> None
        """
        Updates the configuration from a dict.

        Note: Changes will NOT be persisted until you call
        :py:meth:`save`.
        """
        self._load()
        self._update_configs(config_dict, {})

    def debug_repr(self):
        # type: () -> dict
        """
        Returns a dict representation of the trigger storage data,
        useful for debugging.
        """
        self._load()

        return {
            'tasks':        self._serialize(self.tasks, False),
            'instances':    self._serialize(self.instances, False),
            'metas':        self._metas,
        }

    def _load(self, force=False):
        # type: (bool) -> None
        """
        Loads values from the backend.
        """
        if force or not self._loaded:
            raw_configs, raw_statuses, raw_metas = self._load_from_backend()

            self._configs   = {}
            self._instances = TaskInstanceCollection()

            if raw_configs:
                self._update_configs(raw_configs, raw_statuses)

            # Meta status is a bit easier to load.
            self._metas = raw_metas or {}

            # Ensure metas have the proper types.
            self._metas.setdefault('latest_kwargs', {})

            self._loaded = True

    def _update_configs(self, raw_configs, raw_statuses):
        # type: (dict, dict) -> None
        """
        Updates local task config cache.
        """
        for name, raw_config in iteritems(raw_configs):
            self._configs[name] = TaskConfig(name=name, **raw_config)

        for name, raw_status in iteritems(raw_statuses):
            self._instances.create_instance(
                name    = name,
                config  = self._configs[raw_status.pop('task')],

                **raw_status
            )

    def _serialize(self, dict_, optimize_for_backend=True):
        # type: (Union[Dict[Text, TaskConfig], TaskInstance], bool) -> dict
        """
        Serializes values in a config/status dict so they can
        be persisted to the backend.

        :param optimize_for_backend:
            Whether to optimize the result for backend storage.

            Depending on the backend, this parameter might have no
            effect.
        """
        return {
            name: obj.serialize()
                for name, obj in iteritems(dict_)
        }


class TaskInstanceCollection(dict):
    """
    Keeps track of collections of TaskInstances.
    """
    def __init__(self):
        super(TaskInstanceCollection, self).__init__()

        self._collections = defaultdict(dict) # type: Union[defaultdict, Dict[Text, Dict[Text, TaskInstance]]]
        """
        Indexes TaskInstances by task name so that we can apply numeric
        suffixes.
        """

    def get_from_task(self, task_config):
        # type: (TaskConfig) -> Dict[Text, TaskInstance]
        """
        Returns all instances matching the specified task.

        :return:
            Returns an empty dict if the task has no instances.
        """
        return self._collections.get(task_config.name, {})

    def create_instance(self, config, name=None, **kwargs):
        # type: (TaskConfig, Optional[Text], ...) -> TaskInstance
        """
        Creates a new TaskInstance.

        :param name:
            Instance name.  Will be auto-assigned if omitted.

        :param kwargs:
            Additional kwargs to pass to the TaskInstance
            initializer.
        """
        if name is None:
            name = '{task}#{i}'.format(
                task    = config.name,
                i       = len(self._collections[config.name]),
            )

        instance = TaskInstance(
            name    = name,
            config  = config,

            **kwargs
        )

        self[name] = instance
        self._collections[config.name][name] = instance

        return instance
