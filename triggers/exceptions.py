# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from typing import MutableMapping

__all__ = [
    'with_context',
]


def with_context(exc, context):
    # type: (Exception, dict) -> Exception
    """
    Attaches a context dict to an exception, so that it can be
    captured by loggers.

    This lets you keep the exception message fairly short/generic,
    while making useful troubleshooting information accessible to
    debuggers and loggers.

    Example::

       raise with_context(
         exc = ValueError('Failed validation.'),

         context = {
            'errors': filter_runner.get_context(True),
         },
       )

    If the exception already has a ``context`` attribute, it will be
    reassigned to ``exc.context['_original_context']``.
    """
    if not hasattr(exc, 'context'):
        exc.context = {}

    if not isinstance(exc.context, MutableMapping):
        exc.context = {'_original_context': exc.context}

    exc.context.update(context)

    return exc
