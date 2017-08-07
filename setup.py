# coding=utf-8
# Not importing unicode_literals because in Python 2 distutils,
# some values are expected to be byte strings.
from __future__ import absolute_import, division, print_function

from codecs import StreamReader, open
from os.path import dirname, join, realpath

from setuptools import find_packages, setup

cwd = dirname(realpath(__file__))

##
# Load long description for PyPi.
with open(join(cwd, 'README.rst'), 'r', 'utf-8') as f: # type: StreamReader
    long_description = f.read()

##
# Off we go!
# noinspection SpellCheckingInspection
setup(
    version = '2.0.0',

    name = 'Triggers',
    description = 'Distributed observer pattern for scheduling Celery tasks.',
    url = 'https://github.com/eflglobal/triggers',

    long_description = long_description,

    packages = find_packages('.', exclude=['tests', 'tests.*']),

    install_requires = [
        'celery >= 3.0',
        'class-registry',
        'Django',
        'django-redis',
        'filters',

        # Newer versions of python-redis-lock cause deadlocks.
        # Still investigating why this happens.
        'python-redis-lock == 2.3.0',

        'typing; python_version < "3.5"',
    ],

    entry_points = {
        'triggers.storage_backends': [
            'cache=triggers.storage_backends.cache:CacheBackend',
        ],

        'triggers.managers': [
            'default=triggers.manager:TriggerManager',
        ],

        'triggers.task_runners': [
            'celery=triggers.runners:CeleryTaskRunner',
            'threading=triggers.runners:ThreadingTaskRunner',
        ],
    },

    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],

    keywords =
        'observer pattern, celery, django, redis, asynchronous tasks, '
        'scheduling',
)
