================
Storage Backends
================
The storage backend's job is to manage the state for a session and to load and
save data from a (usually) permanent storage medium, such as a database or
filesystem.

The Triggers framework ships with a single storage backend that uses the Django
cache to persist data.  However, you can write and use your own storage backend
if desired.

----------------------------
Anatomy of a Storage Backend
----------------------------
A session state is comprised of 3 primary components:

:py:attr:`tasks`: ``Dict[Text, TaskConfig]``
   This is effectively the same dict that was provided to the trigger manager's
   :py:meth:`update_configuration` method.  Keys are the task names (e.g.,
   ``t_importSubject``), and values are :py:class:`triggers.types.TaskConfig`
   objects.

:py:attr:`instances`: ``Dict[Text, TaskInstance]``
   Contains all of the :ref:`task instances <basic-concepts-task-instances>`
   that have been created for this session.  Keys are the instance names (e.g.,
   ``t_importSubject#0``), and values are
   :py:class:`triggers.types.TaskInstance` objects.

   .. note::
      Task instances may appear in this dict even if they haven't run yet.


:py:attr:`metadata`: ``Dict``
   Contains any additional metadata that the trigger manager and/or storage
   backend needs in order to function properly.  For example,
   :py:attr:`metadata` keep track of all of the triggers that have fired during
   this session, so that the trigger manager can initialize instances for
   :ref:`tasks that run multiple times <configuration-and-every>`.


Working with Session State
~~~~~~~~~~~~~~~~~~~~~~~~~~
The storage backend provides a number of methods for interacting with trigger
tasks and instances:

:py:attr:`__getitem__(task_instance)`
   Returns the task instance with the specified name.  For example:

   .. code-block:: python

      task_instance = trigger_manager.storage['t_importSubject#0']

:py:attr:`__iter__(task_instance)`
   Returns an iterator for the task instances.  Order is undefined.  For
   example:

   .. code-block:: python

      for task_instance in iter(trigger_manager.storage):
        ...

:py:attr:`create_instance(task_config, **kwargs)`
   Creates a new instance of the specified trigger task.

   Additional keyword arguments are passed directly to the
   :py:class:`TaskInstance` initializer.

:py:attr:`clone_instance(task_instance)`
   Given a task instance name or :py:class:`TaskInstance` object, creates and
   installs a copy into the trigger session.

   .. tip::
      This method is used internally when
      :ref:`replaying a failed task <inspecting-replaying>`.

:py:attr:`get_instances_with_unresolved_logs()`
   Unsurprisingly, returns all task instances with
   :ref:`unresolved logs <logs-tracking-log-levels>`.

:py:attr:`get_unresolved_instances()`
   Returns all task instances with :doc:`unresolved status <status>`.

:py:attr:`get_unresolved_tasks()`
   Returns all trigger tasks that either:

   - Do not have any instances yet, or
   - Have at least one task instance with unresolved status.

:py:attr:`instances_of_task(task_config)`
   Returns all task instances that have been created for the specified trigger
   task.

.. note::
   The storage backend contains several more methods, but they are intended to
   be used internally.


--------------------------------
Writing Your Own Storage Backend
--------------------------------
To create your own storage backend, you only need to define methods to load and
save the session data; the base class will take care of everything else for you.

Your backend must implement the following methods:

:py:attr:`_load_from_backend(self)`
   Given ``self.uid``, loads the corresponding session data from the persistence
   medium.

   This method should return a tuple with three values:

   - Item 0 contains the trigger task configurations.
   - Item 1 contains the task instances.
   - Item 2 contains the session metadata.

   .. tip::
      These values do not have to be stored together, as long as the
      :py:meth:`_load_from_backend` method knows how to consolidate them.

:py:attr:`_save(self)`
   Given ``self.uid``, saves the corresponding session data to the persistence
   medium.

   This method should be sure to save the following values:

   - :py:attr:`self._configs`:  Trigger task configurations.
   - :py:attr:`self._instances`:  Trigger task instance.
   - :py:attr:`self._metas`:  Session metadata.

   Note the leading underscore on each of these attributes.

   .. tip::
      To serialize values for storage, use the :py:meth:`self._serialize`
      method.

For more information and examples, look at the implementation of
:py:class:`triggers.storage_backends.cache.CacheStorageBackend`.


Registering Your Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:ref:`As with trigger managers <managers-registering>`, you must register your
custom storage backend before it can be used.

To do this, define a ``triggers.storage_backends`` `entry point`_ in your
project's ``setup.py`` file:

.. code-block:: python

   from setuptools import setup

   setup(
     ...

     entry_points = {
       'triggers.storage_backends': [
         'custom_storage = app.triggers:CustomStorageBackend',
       ],
     },
   )

.. tip::
   Any time you make changes to ``setup.py``, you must reinstall your project
   (e.g., by running ``pip install -e .`` again) before the changes will take
   effect.

Once you've registered your trigger storage backend, you can then use it in your
application:

.. code-block:: python

   from app.triggers import CustomStorageBackend
   from triggers import TriggerManager

   trigger_manager =\
     TriggerManager(CustomStorageBackend(session_uid))

.. important::
   Make sure that your application always uses the same storage backend (unless
   you are 110% sure you know what you are doing).


.. _entry point: https://www.eflglobal.com/setuptools-entry-points/
