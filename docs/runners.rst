============
Task Runners
============
When the trigger manager determines that a task instance is ready to run, it
instantiates a runner to handle the execution.

By default, this runner uses Celery
(:py:class:`triggers.runners.CeleryTaskRunner`), but you can customize this.

For example, during :ref:`unit tests <testing-wait-for-tasks>`, the trigger
manager will use :py:class:`triggers.runners.ThreadingTaskRunner` instead.


CeleryTaskRunner
----------------
As the name implies, :py:class:`CeleryTaskRunner` executes task instances using
`Celery`_.

Each trigger task is implemented as a :doc:`Celery task <tasks>`, and when the
trigger manager schedules a task instance for execution, the
:py:class:`CeleryTaskRunner` will schedule a matching Celery task for execution.

.. tip::
   You can leverage Celery's `router`_ to send tasks to different queues, just
   like regular Celery tasks.


ThreadingTaskRunner
-------------------
:py:class:`ThreadingTaskRunner` operates completely independently from Celery.
Instead of sending tasks to the Celery broker, it executes each task in a
separate thread.

Generally, this runner is only used during :doc:`testing <testing>`, but in
certain cases, it may be useful to utilize this runner in other contexts.

.. tip::
   If you need your application to wait for all running tasks to finish before
   continuing, invoke :py:meth:`ThreadingTaskRunner.join_all`.

   Note that this will wait for *all* running tasks to finish (including
   any :ref:`cascades <tasks-cascading>` that may occur).

   It is not possible (nor in line with the philosophy of the triggers
   framework) to wait for a particular task to finish before continuing.  If you
   need certain logic to run after a particular task finishes, it is recommended
   that you implement that logic as a separate task that is triggered by a
   cascade from the first task.


Writing Your Own Task Runner
----------------------------
As with :doc:`managers` and :doc:`storages`, you can inject your own task
runners into the Triggers framework.


Anatomy of a Task Runner
~~~~~~~~~~~~~~~~~~~~~~~~
A task runner must extend :py:class:`triggers.runners.BaseTaskRunner`.  The base
class declares the following attributes/methods that you must implement in your
custom task runner:

:py:attr:`name: Text`
   A unique identifier for your task runner.

   Generally this matches the name of the task runner's entry point in your
   project's ``setup.py`` file (see below).

:py:attr:`run(self, manager: TriggerManager, task_instance: TaskInstance) -> NoReturn`
   Given a trigger manager and task instance, finds the correct Celery task
   (i.e., using the :py:meth:`resolve` method) and executes it.

   .. tip::
      See :py:meth:`ThreadingTaskRunner.run` for a sample implementation.


Registering Your Task Runner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:ref:`As with trigger managers <managers-registering>`, you must register your
custom task runner before it can be used.

To do this, define a ``triggers.runners`` `entry point`_ in your project's
``setup.py`` file:

.. code-block:: python

   from setuptools import setup

   setup(
     ...

     entry_points = {
       'triggers.runners': [
         'custom_runner = app.triggers:CustomRunner',
       ],
     },
   )

.. tip::
   Any time you make changes to ``setup.py``, you must reinstall your project
   (e.g., by running ``pip install -e .`` again) before the changes will take
   effect.


Using Your Task Runner
~~~~~~~~~~~~~~~~~~~~~~
Unlike :doc:`managers` and :doc:`storages`, your application does not select the
task runner directly.

Instead, the task runner is configured via one of two methods (in descending
order of priority):

#. In the trigger task's :ref:`using <configuration-using>` clause.

   Add your custom task runner to each task's configuration:

   .. code-block:: python

      from app.triggers import CustomRunner

      trigger_manager.update_configuration({
        't_importSubject': {
          ...
          'using': CustomRunner.name,
        },
        ...
      })

   .. tip::
      This approach is useful if you only want some of your tasks to use
      the custom task runner (whereas the rest should use e.g., the
      default :py:class:`CeleryTaskRunner`).

#. Via the trigger manager's :py:attr:`default_task_runner_name` property.

   In order for this to work correctly, you must subclass
   :py:class:`TriggerManager`:

   .. code-block:: python

      class CustomTriggerManager(TriggerManager):
        name = 'custom'
        default_task_runner_name = CustomRunner.name

      trigger_manager = CustomTriggerManager(...)
      tirgger_manager.fire(...)

   .. important::
      Don't forget to
      :ref:`register your custom trigger manager <managers-registering>`!


.. _Celery: http://www.celeryproject.org/
.. _entry point: https://www.eflglobal.com/setuptools-entry-points/
.. _router: http://docs.celeryproject.org/en/latest/userguide/routing.html
