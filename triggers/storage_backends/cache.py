# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from typing import Optional, Text, Tuple, Union

from django.core.cache import BaseCache, DEFAULT_CACHE_ALIAS
from django.core.cache.backends.base import DEFAULT_TIMEOUT

from triggers.locking import resolve_cache
from triggers.storage_backends.base import TriggerStorageBackend

__all__ = [
    'CacheStorageBackend',
]


class CacheStorageBackend(TriggerStorageBackend):
    """
    Uses the Django cache as a storage backend for TriggerManager.
    """
    def __init__(self, uid, cache=DEFAULT_CACHE_ALIAS, timeout=DEFAULT_TIMEOUT):
        # type: (Text, Union[BaseCache, Text], Optional[int]) -> None
        """
        :param uid:
            Session UID

        :param cache:
            The cache backend (or name thereof) to use.

        :param timeout:
            Timeout value to use when storing data to the cache.
        """
        super(CacheStorageBackend, self).__init__(uid)

        self.cache = resolve_cache(cache)
        self.timeout = timeout

    def close(self, **kwargs):
        try:
            self.cache.close(**kwargs)
        except AttributeError:
            pass

    def _load_from_backend(self):
        # type: () -> Tuple[dict, dict, dict]
        cached = self.cache.get(self.cache_key) or {}

        return (
            cached.get('tasks') or {},
            cached.get('instances') or {},
            cached.get('metas') or {},
        )

    def _save(self):
        self.cache.set(
            self.cache_key,

            {
                'tasks':        self._serialize(self._configs, True),
                'instances':    self._serialize(self._instances, True),
                'metas':        self._metas,
            },

            self.timeout,
        )

    @property
    def cache_key(self):
        # type: () -> Text
        """
        Returns the key used to look up state info from the cache.
        """
        return __name__ + ':' + self.uid
