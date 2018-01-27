================
How to Configure
================
To configure a trigger manager instance, call its ``update_configuration``
method and provide a dict with the following items:

- Each key is the name of a trigger task.  These can be anything you want, but
  the convention is to start each name with a ``t_`` prefix.
- Each value is a dict containing that task's configuration.

Here is an example showing how to add 3 tasks to the trigger manager's
configuration.

.. code-block:: python

   trigger_manager.update_configuration({
     't_importSubject':         {...},
     't_importResponses':       {...},
     't_importDeviceMetadata':  {...},
   })

------------------
Task Configuration
------------------
There are many directives you can specify to customize the behavior of each
trigger task.

The directives are named and structured in such a way that you should be able to
"read" a trigger task configuration like an English sentence.

As an example, consider the following trigger task configuration:

.. code-block:: python

   trigger_manager.update_configuration({
     't_importResponses': {
       'after': ['t_importSubject'],
       'andEvery': 'pageReceived',
       'run': 'app.tasks.ImportResponses',
     },
   })

You can "read" the configuration for the ``t_importResponses`` task as:

**After** ``t_importSubject`` fires, **and every** time ``pageReceived`` fires,
**run** the ``app.tasks.ImportResponses`` Celery task.

~~~~~~~~~~~~~~~~~~~
Required Directives
~~~~~~~~~~~~~~~~~~~
The following directives must be provided in each task's configuration.

^^^^^^^^^
``after``
^^^^^^^^^
``after`` is a list of strings that indicates which triggers must fire in order
for the task to be run.

.. tip::

   Recall from :doc:`getting_started` that triggers are fired by your
   application logic, so you get to decide how triggers are named and what
   events they represent.

As an example, suppose we want a task to process data from the first page of a
questionnaire, but we don't want it to run until the user has completed the
questionnaire.  We might configure the trigger task like this:

.. code-block:: python

   trigger_manager.update_configuration({
     't_importSubject': {
       'after': ['firstPageReceived', 'questionnaireComplete'],
       ...
     },
   })

You can also use task names as triggers.  These will fire each time the
corresponding task finishes successfully.

Here's an example of a task that processes data from a single page of
questionnaire responses, but only after the ``t_importSubject`` task has
finished successfully.

.. code-block:: python

   trigger_manager.update_configuration({
     't_importDeviceMetadata': {
       'after': ['pageReceived', 't_importSubject'],
       ...
     },
   })

.. tip::

   The order of values in ``after`` do not matter.

   For compatibility with serialization formats like JSON, ``after`` is
   usually expressed as a ``list`` in Python code, but you can use a ``set`` if
   you prefer.

^^^^^^^
``run``
^^^^^^^
``run`` tells the trigger manager which Celery task to run once the trigger
task's ``after`` condition is satisfied.

The value should match the ``name`` of a Celery task, exactly the same as if
you were configuring ``CELERYBEAT_SCHEDULE``.

As an example, to configure a trigger task to run the
``my_app.tasks.ImportSubject`` task, the configuration might look like this:

.. code-block:: python

   from my_app.tasks import ImportSubject

   trigger_manager.update_configuration({
     't_importSubject': {
       ...
       'run': ImportSubject.name,
     },
   })

.. important::

   The trigger manager can only execute Celery tasks that extend the
   :py:class:`triggers.task.TriggerTask` class.

   See :doc:`tasks` for more information.

~~~~~~~~~~~~~~~~~~~
Optional Directives
~~~~~~~~~~~~~~~~~~~
The following optional directives allow you to further customize the behavior of
your trigger tasks.


.. _configuration-and-every:

^^^^^^^^^^^^
``andEvery``
^^^^^^^^^^^^
By default, every trigger task is "one shot".  That is, it will only run once,
even if the triggers in its ``after`` directive are fired multiple times.

If you would like a trigger task to run multiple times, you can add the
``andEvery`` directive to the trigger configuration.

``andEvery`` accepts a **single** trigger.  Whenever this trigger fires, the
trigger manager will create a new "instance" of the trigger task.

For example, suppose we want to configure a trigger task to process data from
each page in a questionnaire, but it can only run once the ``t_importSubject``
trigger task has finished successfully.

The configuration might look like this:

.. code-block:: python

   trigger_manager.update_configuration({
     't_importResponses': {
       'after': ['t_importSubject'],
       'andEvery': 'pageReceived',
       ...
     },
   })

Using the above configuration, a new instance of ``t_importResponses`` will be
created, but **they will only run after the t_importSubject task finishes**.

^^^^^^^^^^
``unless``
^^^^^^^^^^
``unless`` is the opposite of ``after``.  It defines a condition that will
**prevent** the trigger task from running.

Once a task's ``unless`` condition is satisfied, the trigger manager will not
allow that task to run, even if its ``after`` condition is satisfied later.

.. important::

   This only prevents the trigger manager from scheduling Celery tasks.  It will
   not recall a Celery task that has already been added to a Celery queue, nor
   will it abort any task that is currently being executed by a Celery worker.

As an example, suppose you wanted to import metadata about the applicant's
browser during a questionnaire, but only if the user is completing the
questionnaire in a web browser.  If the backend detects that the questionnaire
is embedded in a mobile application, then this task should not run.

The configuration might look like this:

.. code-block:: python

   trigger_manager.update_configuration({
     't_importBrowserMetadata': {
       'after': ['t_importSubject', 'pageReceived'],
       'unless': ['isEmbeddedApplication'],
       ...
     },
   })

If ``isEmbeddedApplication`` fires before ``t_importSubject`` and/or
``pageReceived``, then the trigger manager will not allow the
``t_importBrowserMetadata`` task to run.

.. caution::

   Watch out for race conditions!

^^^^^^^^^^^^^^
``withParams``
^^^^^^^^^^^^^^
When the trigger manager executes a task, it will provide the kwargs that were
provided when each of that task's ``after`` triggers were fired (see
:doc:`tasks` for more information).

But, what if you need to inject your own static kwargs?

This is what the ``withParams`` directive is for.

As an example, suppose you have a generic trigger task that you use to generate
a psychometric credit score at the end of a questionnaire, but you have to tell
it which model to use.

Using the ``withParams`` directive, you can inject the name of the model like
this:

.. code-block:: python

   from my_app.tasks import ComputeScore

   trigger_manager.update_configuration({
     't_computePsychometricScore': {
       ...
       'run': ComputeScore.name,

       'withParams': {
         'scoring': {'model': 'Psych 01'},
       },
     },
   })

When the ``my_app.tasks.ComputeScore`` Celery task runs, it will be provided
with the model name ``'Psych 01'`` so that it knows which model to load.

.. important::

   ``withParams`` must be a dict of dicts, so that it matches the structure of
   trigger kwargs (see :doc:`tasks` for more information).

   For example, this configuration is **not** correct:

   .. code-block:: python

      trigger_manager.update_configuration({
        't_computePsychometricScore': {
          ...
          'withParams': {
            'model': 'Psych 01',
          },
        },
      })

^^^^^^^^^
``using``
^^^^^^^^^
By default, the trigger manager uses Celery to execute trigger tasks (except
during :doc:`unit tests <testing>`).

However, if you want to use a different :doc:`task runner <runners>`, you can
specify it via the ``using`` directive.

For example, suppose we created a custom task runner that executes tasks via
AWS Lambda.  To tell the trigger manager to execute a task using the custom
task runner, we might use the following configuration:

.. code-block:: python

   from my_app.tasks import ComputeScore
   from my_app.triggers.runners import AwsLambdaRunner

   trigger_manager.update_configuration({
     't_computePsychometricScore': {
       ...
       'run': ComputeScore.name,
       'using': AwsLambdaRunner.name,
     },
   })

.. tip::

   To change the default task runner globally, override
   :py:data:`triggers.runners.DEFAULT_TASK_RUNNER`.

~~~~~~~~~~~~~~~~~
Custom Directives
~~~~~~~~~~~~~~~~~
You can add any additional directives that you want; each will be added to the
corresponding task's ``extras`` attribute.

These aren't used for anything by default, but if you write a
:doc:`custom trigger manager <managers>`, you can take advantage of custom
directives to satisfy your application's requirements.

For an example of how to use custom directives, see the "Finalizing a Session"
recipe in the :doc:`cookbook`
