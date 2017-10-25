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

------------
Task Context
------------
:todo:

---------
Cascading
---------
:todo:

-------
Logging
-------
:todo: ``get_logger_context`` (include link to logs.rst)

--------
Retrying
--------
:todo:
