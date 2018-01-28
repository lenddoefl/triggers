========
Triggers
========
The Triggers framework is an implementation of the observer pattern, designed
for distributed stacks.

It allows you to configure and execute asynchronous tasks based on events that
are triggered by your application.

For example, suppose you have a survey application, and you want an asynchronous
task to run after the user completes steps 1 and 4.

However, you can't guarantee...

- ... that the same server will process both steps.
- ... that both steps will arrive in the correct order.
- ... whether both steps will arrive separately, or at the same time.

The Triggers framework provides a flexible solution that empowers you to
schedule an asynchronous task in such a way that you can guarantee it will be
executed after steps 1 and 4 are completed.

But, it doesn't stop there!  You can also:

- Configure tasks to wait until other asynchronous tasks have finished.
- Define conditions that will cause a task to run multiple times.
- Define conditions that will prevent a task from running.
- Write functional tests to verify that an entire workflow runs as expected.
- And more!

=============
Prerequisites
=============
The Triggers framework requires:

- Python 2.7, 3.5 or 3.6
- Django (any version, but >= 1.11 preferred)
- Celery (>= 3, but >= 4 preferred)
- django-redis-cache
- python-redis-lock==2.3.0

Currently, the Triggers framework requires Redis in order to function properly,
but we are working on removing this requirement in a future version of the
framework.

Note that you do not have to use Redis for your primary application cache; you
can continue to use your preferred cache backend for your ``default`` cache in
Django.  You'll just need to configure a separate cache connection for the
Triggers framework.

At the moment, ``python-redis-lock`` must be at v2.3.0; versions later than this
cause deadlocks.  We are looking into why this is happening and will remove the
version requirement once the issue is resolved.

============
Installation
============
Install the Triggers framework using pip::

   pip install triggers


You can also install from source using the following commands::

   pip install -e git+https://github.com/eflglobal/triggers


Running Unit Tests
------------------
To run unit tests after installing from source, you will need to do a little
bit of one-time prep::

  pip install -e '.[test-runner]'
  cp tests/settings.py.dist tests/settings.py

.. tip::
  By default, the unit tests expect a Redis server listening on
  ``localhost:6379``.  If necessary, you can change this by editing
  ``tests/settings.py``.

Once you've set up the test environment, you can run the unit tests with the
following command::

  python manage.py test

This project is also compatible with `tox`_, which will run the unit tests in
different virtual environments (one for each supported version of Python).

To run the unit tests, it is recommended that you use the `detox`_ library.
detox speeds up the tests by running them in parallel.

Install the package with the ``test-runner`` extra to set up the necessary
dependencies, and then you can run the tests with the ``detox`` command::

  pip install -e '.[test-runner]'
  detox -v

.. important::
  Currently, ``tox.ini`` uses ``tests/settings.py.dist`` for the test settings.
  In particular, this means that all of the unit tests run by tox depend on
  having a Redis server listening on ``localhost:6379``, and there is currently
  no way to change this (without voiding the warranty, that is).

  This will be fixed in a future version of the library.


=============
Documentation
=============
The Triggers framework documentation is available on `ReadTheDocs`_.

If you are installing from source (see above), you
can also build the documentation locally:

#. Install extra dependencies (you only have to do this once)::

      pip install '.[docs-builder]'

#. Switch to the ``docs`` directory::

      cd docs

#. Build the documentation::

      make html


.. _ReadTheDocs: http://triggers.readthedocs.io/
.. _detox: https://pypi.python.org/pypi/detox
.. _tox: https://tox.readthedocs.io/
