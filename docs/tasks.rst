====================
Writing Celery Tasks
====================
The primary function of the Triggers framework is to execute Celery tasks.

For the most part, these look the same as any other Celery tasks, with two
notable differences:

- The tasks must extend :py:class:`triggers.task.TriggerTask`.
- Override the ``_run`` method instead of ``run`` (note the leading underscore).

As an example, consider the following trigger task:

.. code-block:: python

   trigger_manager.update_configuration({
     't_importSubject': {
       'after': ['firstPageReceived', 'questionnaireComplete'],
       'run': 'app.tasks.ImportSubject',
     },
     ...
   })

The idea here is that the ``ImportSubject`` Celery task takes data from the
first page of response data and creates a ``Subject`` record in the database.

The application will help the Celery task by attaching the response data to the
``firstPageReceived`` trigger when it fires:

.. code-block:: python

   def first_page_responses(request):
     """
     Django view that processes the first page of response data
     from the client.
     """
     responses_form = QuestionnaireResponsesForm(request.POST)
     if responses.is_valid():
       ...

       trigger_manager.fire(
         trigger_name   = 'firstPageReceived',
         trigger_kwargs = {'responses': responses.cleaned_data},
       )

       ...

Note that when the ``firstpageReceived`` trigger is fired, the response data are
attached via ``trigger_kwargs``.

Here's what the ``ImportSubject`` Celery task might look like:

.. code-block:: python

   from my_app.models import Subject
   from triggers.task import TaskContext, TriggerTask

   class ImportSubject(TriggerTask):
     def _run(self, context):
       # type: (TaskContext) -> dict

       # Load kwargs provided when the ``firstPageReceived``
       # trigger was fired by the application.
       page_data =\
         context.trigger_kwargs['firstPageReceived']['responses']

       # Create a new ``subject`` record.
       new_subject =\
         Subject.objects.create(
           birthday = page_data['birthday'],
           name     = page_data['name'],
         )

       # Make the PK value accessible to tasks that are
       # waiting for a cascade.
       return {
         'subjectId': new_subject.pk,
       }

The ``ImportSubject`` task's ``_run`` method (note the leading underscore) does
3 things:

1. Load the response data from the ``firstPageReceived`` trigger kwargs.
2. Import the data into a new ``Subject`` record.
3. Return the resulting ID value so that when the task cascades, other tasks
   will be able to use it (more on this later).


.. _task_context:

Task Context
------------
The only argument passed to the ``_run`` method is a
:py:class:`triggers.task.TaskContext` object.

The :py:class:`TaskContext` provides everything that your task will need to
interact with the Triggers framework infrastructure:


Trigger Manager
^^^^^^^^^^^^^^^
``context.manager`` is a trigger manager instance that you can leverage in your
task to interact with the Triggers framework.  For example, you can use
``context.manager`` to fire additional triggers as your task runs.


Trigger Kwargs
^^^^^^^^^^^^^^
As noted above, whenever the application fires a trigger, it can attach optional
kwargs to that trigger.

These kwargs are then made available to your task in two ways:

- ``context.trigger_kwargs`` returns the raw kwargs for each trigger that caused
  your task to run.
- ``context.filter_kwargs()`` uses the `Filters library`_ to validate and
  transform the ``trigger_kwargs``.

The above example shows how to use ``context.trigger_kwargs``.  Here is an
alternate approach that uses ``context.filter_kwargs()`` instead:

.. code-block:: python

  import filters as f

   class ImportSubject(TriggerTask):
     def _run(self, context):
       # type: (TaskContext) -> dict

       filtered_kwargs =\
         context.filter_kwargs({
           'firstPageReceived': {
             'responses':
                 f.Required
               | f.Type(dict)
               | f.FilterMapper({
                   'birthday':  f.Required | f.Date,
                   'name':      f.Required | f.Unicode,
                 }),
           },
         })

       page_data = filtered_kwargs['firstPageReceived']['responses']

       ...

.. note::

   If you have worked with `FilterMappers`_ in the past, the above structure
   should look very familiar.


.. _tasks-cascading:

Cascading
---------
When the Celery task finishes successfully, the trigger manager will cause a
"cascade" by firing the corresponding trigger task's name as a trigger.

For example, consider the trigger task from earlier:

.. code-block:: python

   trigger_manager.update_configuration({
     't_importSubject': {
       'after': ['firstPageReceived', 'questionnaireComplete'],
       'run': 'app.tasks.ImportSubject',
     },
     ...
   })

The trigger task is named ``t_importSubject``, so when the ``ImportSubject``
Celery task finishes, the trigger manager will automatically fire a trigger
named ``t_importSubject``.

But, what kwargs are attached to this trigger?

If the Celery task returns a mapping (e.g., dict), then that will be used as the
kwargs for the cascading trigger.

Going back to the ``ImportSubject`` example:

.. code-block:: python

   class ImportSubject(TriggerTask):
     def _run(self, context):
       ...

       # Make the PK value accessible to tasks that are
       # waiting for a cascade.
       return {
         'subjectId': new_subject.pk,
       }

When this task finishes, the trigger manager will cascade like this:

.. code-block:: python

   trigger_manager.fire(
     trigger_name   = 't_importSubject',
     trigger_kwargs = {'subjectId': new_subject.pk},
   )


Logging
-------
If your Celery task needs to use a logger, consider using
``context.get_logger_context()``.

The logger instance returned by this method includes a few features that
integrate closely with the trigger manager.

See :doc:`logs` for more information.


Retrying
--------
To retry a Celery task mid-execution, the method looks similar to a regular
Celery task:

.. code-block:: python

   class ImportBrowserMetadata(TriggerTask):
     # Specify the max number of retries allowed.
     max_retries = 3

     def _run(self, context):
       # type: (TaskContext) -> dict
       ...

       try:
         # Try to load data from 3rd-party API...
         metadata = api_client.post(...)
       except HttpError as e:
         # ... but if we are unable to connect,
         # retry after a delay.
         raise self.retry(exc=e, cooldown=10)

Note that this retry mechanism works a little differently from Celery's retry:

- You must ``raise self.retry()``; it won't raise the exception for you.
- Use ``cooldown`` instead of ``countdown``.  ``eta`` is not supported.
- If desired, you can also specify replacement trigger kwargs to use when
  retrying the task.

If the Celery task exceeds its ``max_retries``, then it will raise a
:py:class:`triggers.task.MaxRetriesExceeded`.


.. _Filters library: https://filters.readthedocs.io/
.. _FilterMappers: https://filters.readthedocs.io/en/latest/complex_filters.html#working-with-mappings
