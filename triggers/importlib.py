# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from importlib import import_module
from sys import getdefaultencoding as get_default_encoding, exc_info
from typing import Any

from six import PY2, binary_type, string_types, text_type, reraise

__all__ = [
    'dl',
]


def dl(classpath):
    # type: (string_types) -> Any
    """
    Given a fully-qualified path, attempts to import the corresponding
    module and return the referenced symbol.

    :raise:
      - :py:class:`ValueError` if ``classpath`` is not parseable.
      - :py:class:`ImportError` if the module can't be imported.
      - :py:class:`AttributeError` if the object isn't in the module.
    """
    if PY2:
        # In Python 2, symbol paths must be bytes.
        if isinstance(classpath, text_type):
            classpath = classpath.encode(get_default_encoding())

        separator = b'.'
    else:
        # In Python 3, symbol paths must be strings.
        if isinstance(classpath, binary_type):
            classpath = classpath.decode(get_default_encoding())

        separator = '.'

    try:
        module_name, object_name = classpath.rsplit(separator, 1)
    except ValueError:
        reraise(
            ValueError,
            ValueError(
                '{classpath!r} is not a valid classpath.'.format(
                    classpath = classpath,
                ),
            ),
            exc_info()[2],
        )
        return None

    the_module = import_module(module_name)

    try:
        the_object = getattr(the_module, object_name)
    except AttributeError:
        reraise(
            AttributeError,
            AttributeError(
                'No such symbol {classname} in module {module}.'.format(
                    classname   = object_name,
                    module      = module_name,
                ),
            ),
            exc_info()[2],
        )
        return None

    return the_object
