# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from unittest import TestCase

from triggers.itertools import merge_dict, merge_dict_recursive


class MergeDictTestCase(TestCase):
    def test_no_interior_dicts(self):
        """
        Merging multiple dicts that do not have any dicts themselves.
        """
        self.assertDictEqual(
            merge_dict(
                {'foo': True,   'bar': ['baz', 'luhrmann']                              },
                {'foo': False,                              'foobie': True              },
                {               'bar': [None],                              'bletch': 42},
            ),

                {'foo': False,  'bar': [None],              'foobie': True, 'bletch': 42},
        )

    def test_interior_dicts(self):
        """
        Merging multiple dicts that contain one or more dicts.
        """
        self.assertDictEqual(
            merge_dict(
                {'a': {'foo': False, 'bar': 'baz'}                            },
                {'a': {'foo': True, 'baz': 'luhrmann'}, 'b': {'answer': '6x9'}},
                {                                       'b': {'answer': 42}   },
            ),
                {'a': {'foo': True, 'baz': 'luhrmann'}, 'b': {'answer': 42}},
        )

    def test_dict_replaces_non_dict(self):
        """
        A dict can replace a non-dict value.
        """
        self.assertDictEqual(
            merge_dict(
                {'a': 'foo'},
                {'a': {'bar': 'baz'}},
            ),

                {'a': {'bar': 'baz'}},
        )

    def test_non_dict_replaces_dict(self):
        """
        A non-dict can replace a dict value.
        """
        self.assertDictEqual(
            merge_dict(
                {'a': {'bar': 'baz'}},
                {'a': 'foo'},
            ),

                {'a': 'foo'},
        )


class MergeDictRecursiveTestCase(TestCase):
    def test_no_interior_dicts(self):
        """
        Merging multiple dicts that do not have any dicts themselves.
        """
        self.assertDictEqual(
            merge_dict_recursive(
                {'foo': True,   'bar': ['baz', 'luhrmann']                              },
                {'foo': False,                              'foobie': True              },
                {               'bar': [None],                              'bletch': 42},
            ),

                {'foo': False,  'bar': [None],              'foobie': True, 'bletch': 42},
        )

    def test_interior_dicts(self):
        """
        Merging multiple dicts that contain one or more dicts.
        """
        self.assertDictEqual(
            merge_dict_recursive(
                {'a': {'foo': False,    'bar': 'baz',                       }},
                {'a': {'foo': True,                     'baz': 'luhrmann'   },  'b': {'answer': '6x9'}},
                {                                                               'b': {'answer': 42}},
            ),

                {'a': {'foo': True,     'bar': 'baz',   'baz': 'luhrmann'   },  'b': {'answer': 42}},
        )

    def test_dict_replaces_non_dict(self):
        """
        A dict can replace a non-dict value.
        """
        self.assertDictEqual(
            merge_dict_recursive(
                {'a': 'foo'},
                {'a': {'bar': 'baz'}},
            ),

                {'a': {'bar': 'baz'}},
        )

    def test_non_dict_replaces_dict(self):
        """
        A non-dict can replace a dict value.
        """
        self.assertDictEqual(
            merge_dict_recursive(
                {'a': {'bar': 'baz'}},
                {'a': 'foo'},
            ),

                {'a': 'foo'},
        )
