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

- finalizing a session
- namespaced session uids
  .. e.g., want to schedule trigger tasks across multiple related sessions


.. _ClassRegistry: https://pypi.python.org/pypi/class-registry
.. _setup.py: https://github.com/eflglobal/triggers/blob/develop/setup.py
