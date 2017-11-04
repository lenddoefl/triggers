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



- inspecting
   - get instance by name
   - get instance by task
   - get unresolved instances
   - ``debug_repr``
- manipulating state
   - update configuration (add task)
   - create instance
   - change instance status
- error recovery
   - replaying failed tasks
   - skipping failed tasks
