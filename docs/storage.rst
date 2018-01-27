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



--------------------------------
Writing Your Own Storage Backend
--------------------------------


- writing your own
  - loading and saving
  - entry points
