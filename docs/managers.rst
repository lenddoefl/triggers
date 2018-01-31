================
Trigger Managers
================
The trigger manager acts as the controller for the Triggers framework.  Working
in conjunction with a :doc:`storage backend <storage>`, it provides an
interface for effecting changes on a triggers session.

From the :doc:`basic_concepts` documentation, you can see that initializing a
trigger manager is fairly straightforward:

.. code-block:: python

   from triggers import TriggerManager

   trigger_manager = TriggerManager(storage_backend)

Where ``storage_backend`` is a :doc:`storage backend <storage>`.

---------------------------------
Interacting with Trigger Managers
---------------------------------
Trigger managers provide the following methods:

:py:meth:`update_configuration(configuration)`
  Initializes or updates the trigger task configuration.  See :doc:`tasks` for
  more information.

:py:meth:`fire(trigger_name, [trigger_kwargs])`
  Fires a trigger.  See :doc:`getting_started` for more information on how to
  use this method.

:py:meth:`replay_failed_instance(failed_instance, [replacement_kwargs])`
  Given a :doc:`failed <status>` task instance, creates a copy and attempts to
  run it.  If desired, you can provide replacement kwargs, if the original task
  failed due to an invalid kwarg value.

  See :ref:`inspecting-replaying` for more information.

  .. note:: As the name implies, only failed instances can be replayed.

:py:meth:`skip_failed_instance(failed_instance, [cascade], [result])`
  Given a :doc:`failed <status>` task instance, marks the instance as skipped,
  so that it is considered to be :ref:`resolved <inspecting-unresolved>`.

  If desired, you may also specify a fake result for the task instance, to
  trigger a :ref:`cascade <tasks-cascading>`.

  See :ref:`inspecting-skipping` for more information.

  .. note:: As the name implies, only failed instances can be skipped.

:py:meth:`update_instance_status(task_instance, status, [metadata], [cascade], [cascade_kwargs])`
  Manually changes the status for a task instance.  This method can also be used
  to trigger a :ref:`cascade <tasks-cascading>`.

:py:meth:`update_instance_metadata(task_instance, metadata)`
  Manually update the metadata for a task instance.  This method can be used to
  attach arbitrary data to a task instance for logging/troubleshooting purposes.

:py:meth:`mark_instance_logs_resolved(task_instance)`
  Given a task instance, updates its metadata so that its
  :ref:`log messages are resolved <logs-resolving>`.

-------------------------------
Writing Custom Trigger Managers
-------------------------------
You can customize the behavior of the trigger manager(s) that your application
interacts with.

For example, you can write a custom trigger manager that contains additional
logic to :ref:`finalize sessions <cookbook-finalizing>`.

~~~~~
Hooks
~~~~~
Whenever the base trigger manager completes certain actions, it invokes a
corresponding hook, which you can override in your custom trigger manager.

The following hooks are supported:

:py:meth:`_post_fire(trigger_name, tasks_scheduled)`
  Invoked after processing a call to :py:meth:`fire`.  It receives the name of
  the trigger that was fired, and a list of any task instances that were
  scheduled to run as a result.

:py:meth:`_post_replay(task_instance)`
  Invoked after processing a call to :py:meth:`replay_failed_instance`.  It
  receives the **replayed** task instance.

  .. tip::
     You can find the failed instance by inspecting the replayed instance's
     metadata and extracting the ``parent`` item:

     .. code-block:: python

        def _post_replay(task_instance)
          # type: (TaskInstance) -> NoReturn
          parent_name = task_instance.metadata['parent']  # type: Text
          parent_instance = self.storage[parent_name]  # type: TaskInstance

:py:meth:`_post_skip(task_instance, cascade)`
  Invoked after processing a call to :py:meth:`skip_failed_instance`.  It
  receives the skipped task instance, and a boolean indicating whether a cascade
  was simulated.

  .. note::
     This method gets invoked **after** the cascade happens (i.e., after
     :py:meth:`_post_fire` is invoked).


.. _managers-registering:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Registering Your Trigger Manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Because of the way :doc:`trigger tasks <tasks>` work, you must register your
custom trigger manager in order for it to work correctly.

To do this, you must create a custom `entry point`_.

In your project's ``setup.py`` file, add a ``triggers.managers`` entry point
for your custom trigger manager.

For example, if you wanted to register ``app.triggers.CustomManager``, you would
add the following to your project's ``setup.py`` file:

.. code-block:: python

   from setuptools import setup

   setup(
     ...

     entry_points = {
       'triggers.managers': [
         'custom_manager = app.triggers:CustomManager',
       ],
     },
   )

.. tip::
   Any time you make changes to ``setup.py``, you must reinstall your project
   (e.g., by running ``pip install -e .`` again) before the changes will take
   effect.

Once you've registered your trigger manager, you can then use it in your
application:

.. code-block:: python

   from app.triggers import CustomManager
   from triggers import CacheStorageBackend

   trigger_manager =\
     CustomManager(CacheStorageBackend(session_uid))

.. important::
   Make sure that your application always uses the same trigger manager (unless
   you are 110% sure you know what you are doing).


.. _entry point: https://www.eflglobal.com/setuptools-entry-points/
