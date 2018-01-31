=====================
Testing Trigger Tasks
=====================
Writing and running unit tests for trigger tasks can be a bit tricky because
they are designed to be executed by Celery.

Fortunately, the Triggers framework comes with a unit testing toolbox that makes
it super easy to write tests for your trigger tasks!


Test Cases
----------
When writing a test case for a trigger task, ensure that it:

#. Derives from :py:class:`triggers.testing.TriggerManagerTestCaseMixin`, and
#. Initializes ``self.manager`` in its :py:meth:`setUp` method.

.. code-block:: python

   from triggers.testing import TriggerManagerTestCaseMixin
   from unittest import TestCase

   class ImportSubjectTestCase(TriggerManagerTestCaseMixin, TestCase):
     def setUp(self):
       super(TriggerTaskTestCase, self).setUp()

       self.manager =\
         TriggerManager(CacheStorageBackend(self._testMethodName))


.. tip::
   If you are using a persistent storage backend, make sure to clear it before
   each test.


Tests
-----
When writing individual tests, they should conform to the following structure:

1. Configure trigger tasks.
2. Fire triggers.
3. Wait for tasks to complete.
4. Perform assertions.

Here's an example:

.. code-block:: python

   from my_app.models import Subject
   from triggers.runners import ThreadingTaskRunner
   from triggers.testing import TriggerManagerTestCaseMixin
   from unittest import TestCase

   class ImportSubjectTestCase(TriggerManagerTestCaseMixin, TestCase):
     def setUp(self):
       super(TriggerTaskTestCase, self).setUp()

       self.manager =\
         TriggerManager(CacheStorageBackend(self._testMethodName))

   def test_successful_import(self):
     """
     Successfully importing a new subject record.
     """
     # Configure trigger tasks.
     self.manager.update_configuration({
       't_importSubject': {
         'after': ['firstPageReceived', 'questionnaireComplete'],
         'run': 'app.tasks.ImportSubject',
       },
     })

     responses = {
       'firstName': 'Marcus',
       # etc.
     }

     # Fire triggers (in this case, simulating successful
     # questionnaire completion).
     self.manager.fire(
       trigger_name   = 'firstPageReceived',
       trigger_kwargs = {'responses': responses},
     )

     self.manager.fire('questionnaireComplete')

     # Wait for tasks to complete.
     ThreadingTaskRunner.join_all()

     # Perform assertions.
     subject = Subject.objects.latest()

     self.assertInstanceFinished(
       't_importSubject#0',
       {'subjectId': subject.pk},
     )

     self.assertEqual(subject.firstName, responses['firstName'])
     # etc.


1. Configure trigger tasks.
~~~~~~~~~~~~~~~~~~~~~~~~~~~
At the start of each test (or in your test case's :py:meth:`setUp` method),
configure the trigger task(s) that you want to execute during the test.

This is done using the trigger manager's :py:meth:`update_configuration` method.
For example:

.. code-block:: python

   self.manager.update_configuration({
     't_importSubject': {
       'after': ['firstPageReceived', 'questionnaireComplete'],
       'run': 'app.tasks.ImportSubject',
     },
   })

Note that this is the same code that your application uses to
:ref:`initialize a triggers session <getting-started-initialize-configuration>`.

.. tip::
   You can configure multiple trigger tasks in a single test.

   This can be used to test entire workflows, not just individual trigger tasks.


2. Fire triggers.
~~~~~~~~~~~~~~~~~
Once the trigger manager has been configured, the next step is to fire triggers
that cause your trigger tasks to get run, exactly the same as the application
would under normal (or – depending on the test – abnormal) conditions.

For example:

.. code-block:: python

   self.manager.fire(
     trigger_name   = 'firstPageReceived',
     trigger_kwargs = {'responses': responses},
   )

   self.manager.fire('questionnaireComplete')


3. Wait for tasks to complete.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
During unit tests, the trigger manager will automatically use
:py:class:`ThreadingTaskRunner` to execute unit tests.  This means that your
trigger tasks will be run in separate threads instead of using Celery workers.

This process is still asynchronous, however, so it is very important that your
test waits until all of the tasks have finished running (including any tasks
that may have been executed as a result of :ref:`cascading <tasks-cascading>`)
before it begins performing assertions.

To accomplish this, include a call to :py:meth:`ThreadingTaskRunner.join_all`
immediately after firing triggers:

.. code-block:: python

   from triggers.runners import ThreadingTaskRunner

   ...

   self.manager.fire(...)
   self.manager.fire(...)
   self.manager.fire(...)
   ThreadingTaskRunner.join_all()


.. tip::
   You can call :py:meth:`ThreadingTaskRunner.join_all` multiple times in the
   same test, if necessary.


4. Perform assertions.
~~~~~~~~~~~~~~~~~~~~~~
Finally, once all of the trigger tasks have finished, you can begin adding
assertions to the test.

There are two things in particular that your test should check:

a. Trigger task instance state.
...............................
Because trigger tasks run asynchronously, it is important to first verify that
each task instance has the expected status.

For example, if a trigger task fails with an exception or if it didn't get run,
it will be easiest to determine this by checking the task instance's status.

To facilitate this, :py:class:`TriggerManagerTestCaseMixin` provides several
custom assertions:


:py:meth:`assertInstanceAbandoned`
   Given an instance name, checks that the corresponding instance was abandoned
   (i.e., its ``unless`` clause was satisfied before it could be run).

:py:meth:`assertInstanceFailed`
   Given an instance name and exception type, checks that the corresponding
   instance failed with the specified exception type.

:py:meth:`assertInstanceFinished`
   Given an instance name and (optional) result dict, checks that the
   corresponding instance finished successfully and returned the specified
   result.

:py:meth:`assertInstanceMissing`
   Given an instance name, checks that the corresponding instance hasn't been
   created yet (i.e., none of its triggers have fired yet).

:py:meth:`assertInstanceReplayed`
   Given an instance name, checks that the corresponding instance was replayed.

:py:meth:`assertInstanceSkipped`
   Given an instance name, checks that the corresponding instance was skipped.

:py:meth:`assertInstanceUnstarted`
   Given an instance name, checks that the corresponding instance is in
   unstarted state (i.e., not all of its triggers have fired yet).

:py:meth:`assertUnresolvedTasks`
   Given a list of trigger task (not instance!) names, asserts that the
   corresponding tasks are unresolved:

   - Have one or more instances in an unresolved state (e.g., unstarted, failed,
     etc.), or
   - None of its triggers have fired yet.

:py:meth:`assertUnresolvedInstances`
   Given a list of instance names, asserts that the corresponding instances are
   unresolved.

   .. note::
      This method only checks instances where at least one of their triggers
      have fired.

      :py:meth:`assertUnresolvedTasks` is better at detecting tasks that are
      unresolved because none of their triggers have fired yet.


.. tip::
   If an instance has the wrong status, the test failure message will include
   additional information that will make it easier to figure out what went wrong
   (e.g., traceback from the exception, etc.).


Some examples:

.. code-block:: python

   # Check that the task instance finished successfully.
   # Note that we provide the name of the *instance*, not the *task*
   # (hence the ``#0`` suffix):
   self.assertInstanceFinished(
     instance_name   = 't_importSubject#0',
     expected_result = {'subjectId': 42},
   )

   # Check that the task instance failed with the expected error:
   from requests.exceptions import Timeout
   self.assertInstanceFailed(
      instance_name  = 't_importBrowserMetadata#0',
      exc_type       = Timeout,
   )

   # Check that an instance retried automatically on error (until it hit
   # ``max_retries``):
   self.assertInstanceReplayed('t_importBrowserMetadata#0')
   self.assertInstanceReplayed('t_importBrowserMetadata#1')
   self.assertInstanceFailed('t_importBrowserMetadata#2', Timeout)


b. Effects from the trigger tasks.
..................................
After checking that all of the trigger tasks finished (or failed) as expected,
then add assertions verifying the tasks' effects.

These assertions include tasks such as checking for the presence of database
records, checking whether emails were sent, etc.
