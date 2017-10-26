====================
Task Instance Status
====================
Each task instance has a status value associated with it.

These are the possible status values:

``unstarted``
   The task instance has been created, but it is not ready to run yet (i.e., its
   ``after`` condition isn't satisfied).

``scheduled``
   The Celery task has been sent to the broker and is waiting for a worker to
   execute it.

``running``
   A Celery worker is currently executing the task.

``finished``
   The Celery task finished successfully.

``failed``
   The Celery task failed due to an exception.

``replayed``
   The Celery task failed, and a new instance was created to try again.

``skipped``
   The Celery task failed, but it was marked as skipped (instead of retrying).

``abandoned``
   The task instance was abandoned because its ``unless`` clause was satisfied.

For more information about how to check an instance status, see :doc:`managers`.
