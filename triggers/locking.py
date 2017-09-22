# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from abc import ABCMeta, abstractmethod as abstract_method
from contextlib import contextmanager as context_manager
from distutils.version import LooseVersion
from threading import current_thread
from typing import Text, Union

from django import get_version
from django.core.cache import DEFAULT_CACHE_ALIAS
from django.core.cache.backends.base import BaseCache
from django_redis.cache import RedisCache
from redis_lock import Lock
from six import with_metaclass

from triggers.patcher import AttrPatcher

__all__ = [
    'LockAcquisitionFailed',
    'Lockable',
    'NotSupported',
    'acquire_lock',
]


class LockAcquisitionFailed(RuntimeError):
    """
    Indicates that we were unable to acquire a lock on the requested
    key.
    """
    pass


class NotSupported(TypeError):
    """
    Indicates that the cache backend does not support distributed
    locks.
    """
    pass


def resolve_cache(backend):
    # type: (Union[Text, BaseCache]) -> BaseCache
    """
    Gets the cache object with the specified name.
    """
    if isinstance(backend, BaseCache):
        return backend

    django_version = LooseVersion(get_version())
    if django_version.version[0:2] < [1, 7]:
        # noinspection PyUnresolvedReferences
        from django.core.cache import get_cache
        return get_cache(backend)
    else:
        from django.core.cache import caches
        return caches[backend]


@context_manager
def acquire_lock(key, ttl=True, cache=DEFAULT_CACHE_ALIAS, block=True):
    # type: (Text, int, Union[Text, BaseCache], bool) -> None
    """
    Acquires a lock on a specified cache key, if the backend supports
    it.

    :param key:
        Name of the protected cache key.

        Note:  The actual cache key that will be used will have a
        prefix applied, so you do not have to worry about overwriting
        the protected cache value.

    :param ttl:
        Number of seconds before the lock expires.

        If ``True`` (default), the cache's ``default_timeout`` value is
        used.

        If ``False``, then no lock is acquired.  This is useful for
        temporarily disabling/bypassing locking functionality.

        If ``None``, the lock will not expire; it has to be released
        explicitly.

    :param cache:
        Cache backend instance or name.

    :param block:
        Whether the thread should block until the lock is acquired.

        If ``False``, an exception will be raised if the lock cannot be
        acquired immediately.

    :raise:
        - :py:class:`LockAcquisitionFailed` if unable to acquire the
          lock.
        - :py:class:`NotSupported` if the cache backend does not
          support this feature.
    """
    cache = resolve_cache(cache)

    if isinstance(cache, RedisCache):
        # Wait until after we check for compatible backend before we
        # check if lock is disabled; that way disabling the lock
        # doesn't hide a more serious configuration problem.
        if ttl is False:
            yield
        else:
            if ttl is True:
                ttl = cache.default_timeout

            # noinspection PyUnresolvedReferences
            lock = Lock(
                redis_client    = cache.client.get_client(),
                name            = key,
                expire          = ttl,
            )

            if lock.acquire(blocking=block):
                try:
                    yield
                finally:
                    lock.release()
            else:
                raise LockAcquisitionFailed(
                    'Failed to acquire lock on {key!r} '
                    '(ttl={ttl!r}, block={blocking!r}).'.format(
                        key         = key,
                        ttl         = ttl,
                        blocking    = block,
                    ),
                )
    else:
        raise NotSupported(
            '{backend} is not compatible with distributed locks.'.format(
                backend = type(cache).__name__,
            ),
        )


class Lockable(with_metaclass(ABCMeta)):
    """
    Base functionality for an object that can acquire a distributed
    lock internally.

    This is useful when you want a class that behaves differently
    depending on whether or not it holds a lock.

    IMPORTANT: This method behaves similarly to RLock, so the lock is
    guaranteed to be thread-safe, but this guarantee does not extend to
    other attributes in your class!
    """
    @context_manager
    def acquire_lock(self, ttl=True, block=True):
        # type: (Union[None, int], bool) -> None
        """
        Attempts to acquire a lock.

        :param ttl:
            Number of seconds before the lock expires.

            If ``True`` (default), the cache's ``default_timeout``
            value is used.

            If ``None``, the lock will not expire; it has to be
            released explicitly.

        :param block:
            Whether the thread should block until the lock is acquired.

            If ``False``, an exception will be raised if the lock
            cannot be acquired immediately.

        :raise:
          - :py:class:`LockAcquisitionFailed` if unable to acquire the
            lock.
          - :py:class:`NotSupported` if the cache backend does not
            support this feature.
        """
        if self.has_lock:
            yield
        else:
            key     = self.get_lock_name()
            cache   = self.get_lock_backend()

            with acquire_lock(key, ttl, cache, block):
                with AttrPatcher(self, _has_lock=current_thread()):
                    yield

    @abstract_method
    def get_lock_name(self):
        # type: () -> Text
        """
        Returns the name of the lock for :py:meth:`acquire_lock`.
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )

    # noinspection PyMethodMayBeStatic
    def get_lock_backend(self):
        # type: () -> Union[Text, BaseCache]
        """
        Returns the cache backend to use for :py:meth:`acquire_lock`.
        """
        return DEFAULT_CACHE_ALIAS

    @property
    def has_lock(self):
        """
        Returns whether the instance currently holds a lock.
        """
        return getattr(self, '_has_lock', None) is current_thread()
