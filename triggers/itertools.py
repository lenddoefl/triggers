# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from typing import Mapping

from six import iteritems


def merge_dict(*dicts):
    # type: (*Mapping) -> dict
    """
    Merges two or more dicts non-recursively (inner dicts will be
    replaced).

    :return:
        Always returns ``dict``, regardless of the types of the inputs.
    """
    res = {}

    for d in dicts:
        res.update(d)

    return res


def merge_dict_recursive(*dicts):
    # type: (*Mapping) -> dict
    """
    Merges two or more dicts together recursively (inner dicts will
    also be merged).

    Note that sequences (e.g., lists) will still be replaced.

    :return:
        Always returns ``dict``, regardless of the types of the inputs.
    """
    res = {}

    for d in dicts:
        for key, value in iteritems(d):
            if (
                        isinstance(value, Mapping)
                    and isinstance(res.get(key), Mapping)
            ):
                res[key] = merge_dict_recursive(res[key], value)
            else:
                res[key] = value

    return res
