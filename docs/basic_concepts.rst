==============
Basic Concepts
==============
The Triggers framework is loosely based on the `Observer pattern`_, so many of
the concepts described here might look familiar.

Triggers
========
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
--------------
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
=====
It's all fine and good to fire triggers, but in order to accomplish anything,
you've got to have tasks that run in response to those triggers!

Configuration
-------------
Unlike triggers, tasks do not live in your application code (or at least, not
directly).  Instead, tasks are defined in your trigger configuration.

We'll explore where the trigger configuration lives in the :doc:`Usage </usage>`
section; for now, we'll just focus on what the configuration looks like.

Here's an example trigger configuration that defines two tasks, named
`t_createApplicant` and `t_computePsychometricScore`:

.. code-block:: javascript

   {
     "t_createApplicant": {
       "after": ["startSession", "observationsReceived"],
       "run": "applicant_journey.tasks.Import_CreateApplicant"
     },

     "t_computePsychometricScore": {
       "after": ["t_createApplicant", "sessionFinalized"],
       "run": "applicant_journey.tasks.Score_ComputePsychometric"
     }
   }

There's a lot more to configuration than this; we'll explore what you can do
with task configuration in the :doc:`Configuration </configuration>` section.

todo: a diagram would be really helpful

- instances
- cascading


Trigger Managers
================
- trigger manager
- storage backend


.. _observer pattern: https://en.wikipedia.org/wiki/Observer_pattern
.. _task_serializer: http://docs.celeryproject.org/en/latest/userguide/calling.html#serializers
