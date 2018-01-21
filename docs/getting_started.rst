===============
Getting Started
===============
Getting started with the Triggers framework requires a bit of planning.

Step 1:  Define Session UIDs
----------------------------
Sessions limit the context in which the Triggers framework operates.  This
allows your application to maintain separate state for each user of your
application.

In order to integrate the Triggers framework into your application, you will
first need to decide what to use for session UIDs.

Depending on your application, you may want to maintain separate state per user
ID, or you might want to use the IDs of your application's web sessions, etc.

For example, if we want to integrate the Triggers framework into a questionnaire
application, we might opt to create a new session UID each time a user starts a
new questionnaire.


Step 2:  Design Your Workflows
------------------------------
Once you've defined the scope of each session, you'll need to think about what
workflows you want to support over the course of each session:

1. **What** tasks do you want to run?
    Figure out what Celery tasks you want to run when certain conditions are
    met.

    For example, our questionnaire application might have these Celery tasks:

      - ``app.tasks.ImportSubject`` imports details about the user into a SQL
        database.
      - ``app.tasks.ImportResponses`` imports the user's response data into a
        document database.
      - ``app.tasks.ImportBrowserMetadata`` sends a request to a 3rd-party web
        service to download metadata about the user's browser, based on their
        user agent string.

2. **When** do you want to run them?
    Decide what triggers have to fire in order for each of those tasks to run.
    Your application will decide when these happen, so they can correspond to
    any action or condition evaluated by your code.

    .. tip::

       You can also define triggers that will **prevent** certain tasks from
       running.

    Going back to the questionnaire application above, we might define our
    triggers like this:

      - We only want to import data for applicants who successfully complete the
        questionnaire.  ``ImportSubject`` needs information from the first page
        of the questionnaire, **but** it shouldn't run until the questionnaire
        is completed.
      - ``ImportResponses`` should run **each time** we receive a page of
        questionnaire responses, **but** it requires a subject ID, so it can
        only run once ``ImportSubject`` has finished successfully.
      - ``ImportBrowserMetadata`` should run **once** after any single page of
        responses are received, **but** it also requires a subject ID, so it can
        only run after ``ImportSubject`` has finished successfully.

        **However,** if the application detects that the user is completing the
        questionnaire from an embedded application, then this task should
        **not** run.

    .. tip::

       The Triggers framework works best when tasks have to wait for multiple
       asynchronous/unpredictable events in order to run.

       If you find yourself designing tasks that only require a single trigger
       to run, or if you just want to ensure that tasks run in a specific order,
       `Celery already has you covered`_.

3. Give each task and trigger a unique name and write them out like this:

    .. code-block:: javascript

       {
         // Task that runs once.
         "<task name>": {
           "after": ["<trigger>", "<trigger>", ...],
           "run": "<celery task>"
         },

         // Task that can run multiple times:
         "<task name>": {
           "after": ["<trigger>", "<trigger>", ...],
           "andEvery": "<trigger>",
           "run": "<celery task>"
         },

         // Task that will run unless certain condition is met:
         "<task name>": {
           ...
           "unless": ["<trigger>", ...]
         },

         // etc.
       }

    This will form the starting point for your trigger configuration.

    Here's what the starting configuration looks like for the questionnaire
    application:

    .. code-block:: javascript

       {
         "t_importSubject": {
           // Imports data from the first page, but cannot run until
           // the questionnaire is completed.
           "after": ["firstPageReceived", "questionnaireComplete"],

           "run": "app.tasks.ImportSubject"
         },

         "t_importResponses": {
           // Imports response data from EVERY page, but cannot run
           // until the subject data are imported.
           "after": ["t_importSubject"],
           "andEvery": "pageReceived",

           "run": "app.tasks.ImportResponses"
         },

         "t_importBrowserMetadata": {
           // Loads the user agent string from any ONE page of
           // responses (we don't care which one), but cannot run
           // until the subject data are imported...
           "after": ["t_importSubject", "pageReceived"],

           // ... unless the application determines that the requests
           // are coming from an embedded app, in which case, this
           // task should NOT run.
           "unless": ["isEmbeddedApplication"],

           "run": "app.tasks.ImportBrowserMetadata"
         }
       }

    Notice in the above configuration that the trigger task names are distinct
    from the Celery task names; in some cases, you may have multiple trigger
    tasks that reference the same Celery task.

    .. tip::

       Note that you can also use the name of a trigger task itself as a trigger
       (this is a technique known as "cascading", which is described in more
       detail later on).  This allows you to specify that a particular task must
       finish successfully before another task can run.

       In the example configuration, the ``t_importResponses`` trigger task
       cannot run until the ``t_importSubject`` trigger task has finished
       successfully, so we added ``t_importSubject`` to
       ``t_importResponses.after``.

       To make it easier to identify these cases (and to prevent conflicts in
       the event that a trigger has the same name as a trigger task), a ``t_``
       prefix is added to trigger task names.

       You are recommended to follow this convention, but it is not enforced in
       the code.  You may choose a different prefix, or (at your own risk)
       eschew prefixes entirely in your configuration.


Step 3:  Select a Storage Backend
---------------------------------
In order for the Triggers framework to function, it has to store some state
information in a storage backend.

Currently, the only storage backend uses the Django cache.  In the future,
additional backend will be added to provide more options (e.g., Django ORM,
document database, etc.).

.. tip::

   If you use Redis as your cache backend, you can configure the Triggers
   framework so that it stores values with no expiration time.

You can also :doc:`write your own storage backend <storage>`.


Step 4:  Fire Triggers
----------------------
Now it's time to start writing some Python code!

Back in step 2, we defined a bunch of triggers.  Now we're going to write the
code that fires these triggers.

To fire a trigger, create a trigger manager instance, and provide a storage
backend instance, then call the trigger manager's ``fire()`` method.

It looks like this:

.. code-block:: python

   from triggers import TriggerManager, CacheStorageBackend

   storage_backend =\
     CacheStorageBackend(
       # Session UID (required)
       uid = session_uid,

       # Name of cache to use.
       cache = 'default',

       # TTL to use when setting values.
       # Depending on which cache you use (e.g., Redis), setting
       # ``timeout=None`` may store values permanently, or it
       # may use the cache's default timeout value.
       timeout = 3600,
     )

   trigger_manager = TriggerManager(storage_backend)

   trigger_manager.fire(trigger_name)

In the above code, replace ``session_uid`` with the Session UID that you want to
use (see Step 1 above), and ``trigger_name`` with the trigger that you want to
fire.

.. tip::

   Depending on the complexity of your application, you might opt to use a
   function and/or Django settings to create the trigger manager instance.

   See the :doc:`cookbook` for a sample implementation.

Trigger Kwargs
~~~~~~~~~~~~~~
When your application fires a trigger, it can also attach keyword arguments to
that trigger.  These arguments will be made available to the Celery task when it
runs.

Here's an example of how our questionnaire application might fire the
``pageReceived`` trigger:

.. code-block:: python

   def responses(request):
     """
     Django view that processes a page of response data from
     the client.
     """
     responses_form = QuestionnaireResponsesForm(request.POST)
     if responses.is_valid():
       trigger_manager = TriggerManager(
         storage = CacheStorageBackend(
           uid      = responses_form.cleaned_data['questionnaire_id'],
           cache    = 'default',
           timeout  = 3600,
         ),
       )

       trigger_manager.fire(
         trigger_name   = 'pageReceived',
         trigger_kwargs = {'responses': responses.cleaned_data},
       )

       ...

.. caution::

   Behind the scenes, the trigger kwargs will be provided to the Celery task via
   the task's ``kwargs``, so any values that you use for trigger kwargs must be
   compatible with Celery's `serializer`_.


.. _getting-started-initialize-configuration:

Step 5:  Initialize Configuration
---------------------------------
Next, you need to write the code that will initialize the configuration for each
new session.

This is accomplished by invoking :py:meth:`TriggerManager.update_configuration`:

.. code-block:: python

   trigger_manager.update_configuration({
     # Configuration from Step 2 goes here.
   })

Here's an example showing how we would initialize the trigger configuration at
the start of the questionnaire application:

.. code-block:: python

   def start_questionnaire(request):
     """
     Django view tha processes a request to start a new questionnaire.
     """
     # Create the new questionnaire instance.
     # For this example, we will use the PK value of the
     # new database record as the session UID.
     new_questionnaire = Questionnaire.objects.create()

     trigger_manager = TriggerManager(
       storage = CacheStorageBackend(
         # The session UID must be a string value.
         uid = str(new_questionnaire.pk),

         cache    = 'default',
         timeout  = 3600,
       ),
     )

     trigger_manager.update_configuration({
       't_importSubject': {
         'after': ['firstPageReceived', 'questionnaireComplete'],
         'run': 'app.tasks.ImportSubject',
       },

       't_importResponses': {
         'after': ['t_importSubject'],
         'andEvery': 'pageReceived',
         'run': 'app.tasks.ImportResponses',
       },

       't_importBrowserMetadata': {
         'after': ['t_importSubject', 'pageReceived'],
         'unless': ['isEmbeddedApplication'],
         'run': 'app.tasks.ImportBrowserMetadata',
       },
     })

     ...


Step 6:  Write Celery Tasks
---------------------------
The final step is writing the Celery tasks.  These will look similar to normal
Celery tasks, with a couple of differences:

- The tasks must extend :py:class:`triggers.task.TriggerTask`.
- Override the ``_run`` method instead of ``run`` (note the leading underscore).

For more information about see :doc:`tasks`.


.. _celery already has you covered: http://docs.celeryproject.org/en/latest/userguide/canvas.html
.. _serializer: http://docs.celeryproject.org/en/latest/userguide/calling.html#serializers
