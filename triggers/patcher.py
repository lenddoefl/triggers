# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from abc import ABCMeta, abstractmethod as abstract_method

from six import iteritems, with_metaclass

__all__ = [
    'AttrPatcher',
    'BasePatcher',
]


class BasePatcher(with_metaclass(ABCMeta)):
    """
    Creates a context in which attributes and/or properties of an
    object are temporarily modified.
    """
    class DoesNotExist(object):
        """
        Used to identify a value that did not exist before we started.
        """
        pass

    def __init__(self, target, **kwargs):
        super(BasePatcher, self).__init__()

        self._target = target

        self._new_values  = kwargs
        self._prev_values = {}

    def __enter__(self):
        self.apply()

    # noinspection PyUnusedLocal
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.restore()

    def apply(self):
        """
        Applies the new values.
        """
        # Back up previous values.
        self._prev_values = {
            key: self._get_value(key, self.DoesNotExist)
                for key in self._new_values
        }

        # Patch values.
        for key, value in iteritems(self._new_values):
            if value is self.DoesNotExist:
                self._del_value(key)
            else:
                self._set_value(key, value)

    def restore(self):
        """
        Restores previous settings.
        """
        # Restore previous settings.
        for key, value in iteritems(self._prev_values):
            if value is self.DoesNotExist:
                self._del_value(key)
            else:
                self._set_value(key, value)

    @abstract_method
    def _get_value(self, key, default=None):
        """
        Extracts a value from the target.
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )

    @abstract_method
    def _set_value(self, key, value):
        """
        Applies a value to the target.
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )

    @abstract_method
    def _del_value(self, key):
        """
        Removes a value from the target.
        """
        raise NotImplementedError(
            'Not implemented in {cls}.'.format(cls=type(self).__name__),
        )


class AttrPatcher(BasePatcher):
    """
    Patches attributes on an object.
    """
    def _get_value(self, key, default=None):
        return getattr(self._target, key, default)

    def _set_value(self, key, value):
        return setattr(self._target, key, value)

    def _del_value(self, key):
        return delattr(self._target, key)
