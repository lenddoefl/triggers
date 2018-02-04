# coding=utf-8
# Not importing unicode_literals because in Python 2 distutils,
# some values are expected to be byte strings.
from __future__ import absolute_import, division, print_function

from codecs import StreamReader, open
from distutils.version import LooseVersion
from os.path import dirname, join, realpath

from setuptools import find_packages, setup
from setuptools.version import __version__

##
# Because of the way we declare dependencies here, we need a more recent
# version of setuptools.
# https://www.python.org/dev/peps/pep-0508/#environment-markers
if LooseVersion(__version__) < LooseVersion('20.5'):
    raise EnvironmentError('Triggers requires setuptools 20.5 or later.')


##
# Load long description for PyPi.
readme = join(dirname(realpath(__file__)), 'README.rst')
with open(readme, 'r', 'utf-8') as f: # type: StreamReader
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
        'class-registry >= 2.1.2',
        'django-redis',
        'filters',

        # Django 2.0 does not support Python 3.
        # Good on them, but we have legacy project to support over here in
        # triggers land (:
        'Django; python_version >= "3.0"',
        'Django < 2.0; python_version < "3.0"',

        # Newer versions of python-redis-lock cause deadlocks.
        # Still investigating why this happens.
        'python-redis-lock == 2.3.0',

        'typing; python_version < "3.5"',
    ],

    extras_require = {
        'docs-builder': ['sphinx', 'sphinx_rtd_theme'],
        'test-runner': ['detox', 'django-nose'],
    },

    entry_points = {
        'triggers.managers': [
            'default=triggers.manager:TriggerManager',
        ],

        'triggers.runners': [
            'celery=triggers.runners:CeleryTaskRunner',
            'threading=triggers.runners:ThreadingTaskRunner',
        ],

        'triggers.storages': [
            'cache=triggers.storages.cache:CacheStorageBackend',
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

    author        = 'Phoenix Zerin',
    author_email  = 'phx@phx.ph',
)
