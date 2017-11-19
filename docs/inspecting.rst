===================================
Inspecting State and Error Recovery
===================================
Each time you create a trigger manager instance, you also assign a storage
backend.  The storage backend is responsible for maintaining session state, but
it also provides a number of methods and attributes that your application can
inspect.

------------------------
What's In Session State?
------------------------
Inside of a session's state are 3 objects:

- ``tasks`` contains the configured trigger tasks.
- ``instances`` contains instances of each task.
- ``metadata`` contains internal metadata.

In general, you won't need to interact with these objects directly, but they can
be useful for inspecting and troubleshooting sessions.

------------------------
Inspecting Session State
------------------------
To inspect a session's state, your application will interact with the trigger
manager's storage backend.

.. tip::

   If you only want to inspect a session's state (i.e., you don't need to fire
   triggers, change task instance status, etc.), you do not need to create a
   trigger manager instance; you only need an instance of the storage backend.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Inspecting Task Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To inspect a trigger task's configuration, load it from ``tasks``:

.. code-block:: python

   task = trigger_manager.storage.tasks['t_importSubject']

In the above example, ``task`` is an instance of
:py:class:`triggers.types.TaskConfig`.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Inspecting Instance Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To inspect a trigger instance configuration, load it from ``instances``:

.. code-block:: python

   instance = trigger_manager.storage.instances['t_importSubject#0']

In the above example, ``instance`` is an instance of
:py:class:`triggers.types.TaskInstance`.

.. note::

   To get the instance, you must provide the name of the *instance*, not the
   name of the *task*:

   .. code-block:: python

      # Using instance name:
      >>> trigger_manager.storage.instances['t_importSubject#0']
      TaskInstance(...)

      # Using task name:
      >>> trigger_manager.storage.instances['t_importSubject']
      KeyError: 't_importSubject'

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Finding Instances By Trigger Task
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
If you want to find all the instances for a particular task, use the
``instances_of_task`` method:

.. code-block:: python

   instances =\
     trigger_manager.storage.instances_of_task['t_importSubject']

In the above example, ``instances`` is a list of :py:class:`TaskInstance`
objects.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Finding Unresolved Tasks and Instances
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
When inspecting the state of a session, one of the most critical pieces of
information that applications need is the list of tasks that haven't been
finished yet.

The storage backend provides two methods to facilitate this:

``get_unresolved_tasks()``
   Returns a list of all tasks that haven't run yet, or have one or more
   unresolved instances.

``get_unresolved_instances()``
   Returns a list of all unresolved instances.

The difference between these methods is subtle but important.

It is best explained using an example:

.. code-block:: python

   >>> from uuid import uuid4
   >>> from triggers import TriggerManager
   >>> from triggers.storage_backends.cache import CacheStorageBackend

   >>> trigger_manager =\
   ...   TriggerManager(CacheStorageBackend(uuid4().hex))
   ...

   >>> trigger_manager.update_configuration({
   ...   't_importSubject': {
   ...     'after': ['firstPageReceived', 'questionnaireComplete'],
   ...     'run':   '...',
   ...   },
   ... })
   ...

   # ``t_importSubject`` hasn't run yet, so it is unresolved.
   >>> trigger_manager.storage.get_unresolved_tasks()
   [<TaskConfig 't_importSubject'>]

   # None of the triggers in ``t_importSubject.after`` have fired
   # yet, so no task instance has been created yet.
   >>> trigger_manager.storage.get_unresolved_instances()
   []

   >>> trigger_manager.fire('firstPageReceived')

   # After the trigger fires, the trigger manager creates an
   # instance for ``t_importSubject``, but it can't run yet, because
   # it's still waiting for the other trigger.
   >>> [<TaskInstance 't_importSubject#0'>]


^^^^^^^^^^^^^^^^^^^^^^^^
Getting the Full Picture
^^^^^^^^^^^^^^^^^^^^^^^^
If you want to get a snapshot of the state of every task and instance,
invoke the ``debug_repr`` method:

.. code-block:: python

   from pprint import pprint
   pprint(trigger_manager.storage.debug_repr())

.. tip::

   As the name implies, this is intended to be used only for debugging purposes.

   If you find yourself wanting to use it as part of normal operations, this
   likely indicates a deficiency in the Trigger Manager's feature set; please
   post a feature request on the `Triggers Framework Bug Tracker`_ so that we
   can take a look!


- manipulating state
   - update configuration (add task)
   - create instance
   - change instance status
- error recovery
   - replaying failed tasks
   - skipping failed tasks

.. _Triggers Framework Bug Tracker: https://github.com/eflglobal/triggers/issues
