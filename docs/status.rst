====================
Task Instance Status
====================
Each task instance has a status value associated with it
(:py:attr:`TaskInstance.status`).

These are the possible status values:

``abandoned``
   The task instance will never run, because its ``unless`` clause was
   satisfied.

``failed``
   The Celery task failed due to an exception.

``finished``
   The Celery task finished successfully.

``replayed``
   The Celery task failed, and it was replayed.

   When a failed instance is replayed, a new task instance is created to rerun
   the Celery task.  This provides a mechanism for recovering from exceptions,
   while retaining the exception and traceback information for investigation.

``running``
   A Celery worker is currently executing the task.

``scheduled``
   The Celery task has been sent to the broker and is waiting for a worker to
   execute it.

   In rare cases, an instance may remain in "scheduled" status for some time
   (for example, if no Celery workers are available to execute the task, or if
   the broker becomes unavailable).

``skipped``
   The Celery task failed, but it was marked as skipped (instead of retrying).

``unstarted``
   The task instance has been created, but it is not ready to run yet.

   This occurs when some – but not all – of the triggers in the task's ``after``
   clause have fired.  The instance will remain in "unstarted" status until the
   remaining triggers have fired.

-------------
Meta-Statuses
-------------
:py:class:`TaskInstance` also defines a few properties that can help your
application to make decisions based on an instance's status:

:py:attr:`TaskInstance.can_abandon`
   Indicates whether the task instance's ``unless`` condition is satisfied.
   Returns ``False`` if the instance already has "abandoned" status.

:py:attr:`TaskInstance.can_run`
   Indicates whether the instance is ready to run (add a Celery task to the
   queue).

:py:attr:`TaskInstance.can_schedule`
   Indicates whether the instance is ready to be scheduled for execution.

   This property is generally only used internally.

   .. important::

      This property does **not** indicate that the instance is ready to *run*;
      use :py:attr:`TaskInstance.can_run` for that.

:py:attr:`TaskInstance.can_replay`
   Indicates whether the instance can be replayed.

:py:attr:`TaskInstance.can_skip`
   Indicates whether the instance can be skipped.

:py:attr:`TaskInstance.is_resolved`
   Indicates whether this instance has a "final" status.  Once an instance is
   resolved, no further operations may be performed on it.

   Examples of resolved instances include:

   - Celery task finished successfully (nothing left to do).
   - ``unless`` clause satisfied (task must not run).
   - Celery task failed, but the failed instance was replayed (a new instance
     was created for the replay).
   - Celery task failed, but the failed instance was skipped (nothing left to
     do).

   If an instance's ``is_resolved`` attribute is ``False``, this means that it
   is currently in progress and/or requires some kind of change before it can be
   resolved.  Some examples include:

   - The instance hasn't been run yet because it is waiting for additional
     triggers (no action necessary).
   - The instance has been scheduled for execution, but it is waiting for a
     Celery worker to become available (no action necessary).
   - The instance is currently being executed by a Celery worker (no action
     necessary).
   - The instance is in failed state (needs to be replayed or skipped).

   Note that most of the time, an unresolved instance is not a bad thing.

========================
Checking Instance Status
========================
For more information about how to check an instance's status, see
:doc:`inspecting`.
