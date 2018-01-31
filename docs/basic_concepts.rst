==============
Basic Concepts
==============
The Triggers framework is loosely based on the `Observer pattern`_, so many of
the concepts described here might look familiar.


Triggers
--------
A trigger is very similar to an event in the `Observer pattern`_.  Essentially,
it is just a string/identifier, with some optional metadata attached to it.

What makes triggers so important is that **your application decides what they
are named, and when to fire them**.

Here's an example of how a survey application might fire a trigger in response
to receiving a payload containing data collected by a module:

.. code-block:: python

   def process_module_1(module_data):
     """
     Processes the data received from module 1.
     """
     #
     # ... process the module data, store results to DB, etc. ...
     #

     # Create a Trigger Manager instance (more on this later).
     trigger_manager = TriggerManager(...)

     # Fire a trigger.
     trigger_manager.fire('module1Received')

In this example, the ``module1Received`` trigger has meaning because your
application will only fire it once it finishes processing the data from module
1.


Trigger Kwargs
~~~~~~~~~~~~~~
When your application fires a trigger, it can also attach some kwargs to it.
Any task that runs in response to this trigger will have access to these kwargs,
so you can use this to provide additional metadata that a task might need.

Using the above example, let's imagine that your application stores the module
data to a document database, and you want to add the document ID to the trigger
kwargs.

The result might look something like this:

.. code-block:: python

   def process_module_1(module_data):
     """
     Processes the data received from module 1.
     """
     # Store the module data to a document database.
     document_id = db.store(module_data)

     # Create a Trigger Manager instance (more on this later).
     trigger_manager = TriggerManager(...)

     # Fire a trigger, with kwargs.
     trigger_manager.fire('module1Received', {'document_id': document_id})

When the application fires the ``module1Received`` trigger, it attaches a kwarg
for ``document_id``.  This value will be accessible to any task that runs in
response to this trigger, so that it can load the module data from the document
database.

.. note::
   Celery schedules tasks by sending messages to a queue in a message broker, so
   trigger kwargs must be serializable using Celery's `task_serializer`_.


Tasks
-----
Firing triggers is fun and all, but the whole point here is to execute Celery
tasks in response to those triggers!

This is where trigger tasks come into play.

A trigger task acts like a wrapper for a Celery task:

- The Celery task does the actual work.
- The trigger task defines the conditions that will cause the Celery task to
  get executed.


Task Configurations
~~~~~~~~~~~~~~~~~~~
Here's an example trigger configuration that defines two tasks, named
`t_createApplicant` and `t_computeScore`:

.. code-block:: javascript

   {
     "t_createApplicant": {
       "after": ["startSession", "observationsReceived"],
       "run": "applicant_journey.tasks.Import_CreateApplicant"
     },

     "t_computeScore": {
       "after": ["t_createApplicant", "sessionFinalized"],
       "run": "applicant_journey.tasks.Score_ComputePsychometric"
     }
   }

We can translate the above configuration into English like this::

   Trigger Task "t_createApplicant":
     After the "startSession" and "observationsReceived" triggers fire,
     Run the "Import_CreateApplicant" Celery task.

   Trigger Task "t_computeScore":
     After the "t_createApplicant" and "sessionFinalized" triggers fire,
     Run the "Score_ComputePsychometric" Celery task.

We'll explore what this all means in the :doc:`/configuration`
section.

.. note::

   Did you notice that one of the triggers for ``t_computeScore`` (inside its
   ``after`` attribute) is the name of another trigger task
   (``t_createApplication``)?

   This takes advantage of a feature called `cascading`, where a trigger task
   fires its own name as a trigger when its Celery task finishes successfully.

   In this way, you can "chain" trigger tasks together.

   We will cover cascading in more detail in :doc:`/configuration`.


.. _basic-concepts-task-instances:

Task Instances
--------------
In certain cases, a task may run multiple times.  To accommodate this, the
Triggers framework creates a separate task instance for each execution of a
task.

Each task instance is named after its task configuration, with an incrementing
sequence number (e.g., ``t_createApplicant#0``,
``t_computeScore#0``, etc.).


Sessions
--------
A session acts as a container for triggers and trigger task instances.  This
allows you to maintain multiple states in isolation from each other.

For example, if you maintain a survey application, each survey would have its
own session.  This way, any triggers fired while processing a particular survey
would not interfere with any other surveys.


Session UIDs
~~~~~~~~~~~~
Each session should have a unique identifier (UID).  This value is provided to
the storage backend at initialization, so that the trigger manager can load the
saved state for that session.


Trigger Managers
----------------
The trigger manager acts as the controller for the Triggers framework.  It is
responsible for firing triggers, managing trigger task instances, and so on.

To interact with the Triggers framework in your application, create an instance
of the trigger manager class, like this:

.. code-block:: python

   from triggers import CacheStorageBackend, TriggerManager

   # Specify the session UID.
   sessionUid = '...'

   # Create the trigger manager instance.
   trigger_manager = TriggerManager(CacheStorageBackend(sessionUid))

   # Fire triggers.
   trigger_manager.fire('ventCoreFrogBlasted')


Storage Backends
----------------
To maintain state across multiple processes, the trigger manager relies on a
storage backend.

The storage backend is responsible for loading and storing the session state.

The Triggers framework comes bundled with a cache storage backend, which stores
session state using Django's cache.  Additional backends will be added in future
versions of the library.


.. _observer pattern: https://en.wikipedia.org/wiki/Observer_pattern
.. _task_serializer: http://docs.celeryproject.org/en/latest/userguide/calling.html#serializers
