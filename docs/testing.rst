=====================
Testing Trigger Tasks
=====================
Writing and running unit tests for trigger tasks can be a bit tricky because
they are designed to be executed by Celery.

Fortunately, the Triggers framework comes with a unit testing toolbox that makes
it super easy to write tests for your trigger tasks!


----------
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


-----
Tests
-----
When writing individual tests, they should conform to the following structure:

#. Configure trigger tasks.
#. Fire triggers.
#. Wait for tasks to complete.
#. Perform assertions.

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


.. todo subsections for each bullet point from above
