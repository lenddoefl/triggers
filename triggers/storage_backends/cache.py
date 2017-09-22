# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from typing import Text, Tuple

from django.core.cache import DEFAULT_CACHE_ALIAS

from triggers.locking import resolve_cache
from triggers.storage_backends.base import TriggerStorageBackend

__all__ = [
    'CacheStorageBackend',
]


class CacheStorageBackend(TriggerStorageBackend):
    """
    Uses the Django cache as a storage backend for TriggerManager.
    """
    def __init__(self, uid):
        super(CacheStorageBackend, self).__init__(uid)

        self.cache = resolve_cache(DEFAULT_CACHE_ALIAS)

    def close(self, **kwargs):
        """
        Closes the active connection to the storage backend.
        """
        try:
            self.cache.close(**kwargs)
        except AttributeError:
            pass

    def _load_from_backend(self):
        # type: () -> Tuple[dict, dict, dict]
        """
        Loads configuration and status values from the backend.

        :return:
            (task config, task status, meta status)
        """
        return (
            self.cache.get(self.task_config_cache_key),
            self.cache.get(self.task_status_cache_key),
            self.cache.get(self.meta_status_cache_key),
        )

    def _save(self):
        """
        Persists changes to the backend.

        You can assume that the instance owns the active lock for the
        UID, and that the data have already been loaded (i.e.,
        there is already something to be persisted).
        """
        self.cache.set(
            self.task_config_cache_key,
            self._serialize(self._configs),
        )

        self.cache.set(
            self.task_status_cache_key,
            self._serialize(self._instances),
        )

        # Meta-status is a dict of primitives and does not need extra
        # serialization.
        self.cache.set(self.meta_status_cache_key, self._metas)

    @property
    def task_config_cache_key(self):
        # type: () -> Text
        """
        Returns the key used to look up config values in the cache.
        """
        return __name__ + ':' + self.uid + ':config'

    @property
    def task_status_cache_key(self):
        # type: () -> Text
        """
        Returns the key used to look up task status values in the
        cache.
        """
        return __name__ + ':' + self.uid + ':task_status'

    @property
    def meta_status_cache_key(self):
        # type: () -> Text
        """
        Returns the key used to look up meta status values in the
        cache.
        """
        return __name__ + ':' + self.uid + ':meta_status'
