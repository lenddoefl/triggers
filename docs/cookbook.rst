========
Cookbook
========
This page describes some strategies for customizing the behavior of the
Triggers framework, depending on the needs of your application.


Setting the Manager/Storage Type at Runtime
-------------------------------------------
Internally, the Triggers framework uses a library called `ClassRegistry`_ to
manage the registered trigger managers and storage backends.  ClassRegistry
works by assigning each class a unique key and adding it to a registry
(dict-like object).

You can leverage this feature in your application to make the manager and/or
storage type configurable at runtime, by storing the corresponding keys in
application settings (e.g., in a Django ``settings.py`` module).

Here's an example:

First, we set some sensible defaults:

.. code-block:: python

   # my_app/settings.py

   TRIGGER_MANAGER_TYPE = 'default'
   TRIGGER_STORAGE_TYPE = 'cache'

.. tip::
   The values ``'default'`` and ``'cache'`` can be found in the entry point
   definitions for :py:class:`TriggerManager` and
   :py:class:`CacheStorageBackend`, respectively.

   Entry point definitions are set in the library's `setup.py`_; look for the
   ``entry_points`` configuration.

   See :ref:`managers-registering` for more information.

Next, we'll define a function that will build the trigger manager object from
these settings:

.. code-block:: python

   # my_app/triggers.py

   from typing import Text
   from triggers import TriggerManager
   from triggers.manager import trigger_managers
   from triggers.storages import storage_backends

   from my_app.settings import TRIGGER_MANAGER_TYPE, \
     TRIGGER_STORAGE_TYPE

   def get_trigger_manager(uid):
     # type: (Text) -> TriggerManager
     """
     Given a session UID, returns a configured trigger manager.
     """
     storage = storage_backends.get(TRIGGER_STORAGE_TYPE, uid)
     manager = trigger_managers.get(TRIGGER_MANAGER_TYPE, storage)

     return manager

Note the use of :py:data:`triggers.manager.trigger_managers` and
:py:data:`triggers.storages.storage_backends`.  These are the registries of
trigger managers and storage backends, respectively.

The :py:meth:`get` method retrieves the class corresponding to the identifier
(e.g., ``TRIGGER_STORAGE_TYPE`` — "cache" in this case) and instantiates it
using the remaining arguments (e.g., ``uid``).

Finally, call ``get_trigger_manager()`` in your application wherever you need a
:py:class:`TriggerManager` instance.

By changing the values of the ``TRIGGER_MANAGER_TYPE`` and/or
``TRIGGER_STORAGE_TYPE`` settings, you can customize the trigger manager and/or
storage backend that your application uses, without having to rewrite any logic.


.. _cookbook-finalizing:

Finalizing a Session
--------------------
In many cases, it is useful to schedule trigger tasks to run when everything
else is finished.

For example, we may want to have our questionnaire application set a status flag
in the database once the questionnaire is 100% complete and all of the other
trigger tasks have finished successfully.

To make this work, we will define a new trigger called ``sessionFinalized`` that
fires when all of the trigger tasks in a session have finished running.

We can detect that a trigger task has finished running by waiting for its
:ref:`cascade <tasks-cascading>`; that is, we can perform the "is session
finalized" check after each trigger fires.

To accomplish this, we must create our own :doc:`trigger manager <managers>` and
override its :py:meth:`_post_fire` hook.

We will also take advantage of the trigger manager's ability to
:ref:`find unresolved tasks <inspecting-unresolved>`, so that we can determine
if there are any tasks waiting to run.

The end result looks like this:

.. code-block:: python

   class FinalizingTriggerManager(TriggerManager):
     TRIGGER_SESSION_FINALIZED = "sessionFinalized"

     def _post_fire(self, trigger_name, tasks_scheduled):
       # Prevent infinite recursion.
       if trigger_name == self.TRIGGER_SESSION_FINALIZED:
         return

       # A session can only be finalized once.
       if self.TRIGGER_SESSION_FINALIZED in self.storage.latest_kwargs:
         return

       # Check for any unresolved tasks...
       for config in self.get_unresolved_tasks():
         # ... ignoring any that are waiting for session finalized.
         if self.TRIGGER_SESSION_FINALIZED not in config.after:
           return

       # If we get here, we are ready to finalize the session.
       self.fire(self.TRIGGER_SESSION_FINALIZED)


.. important::
   Don't forget to :ref:`register your trigger manager <managers-registering>`!

- namespaced session uids
  .. e.g., want to schedule trigger tasks across multiple related sessions


.. _ClassRegistry: https://pypi.python.org/pypi/class-registry
.. _setup.py: https://github.com/eflglobal/triggers/blob/develop/setup.py
