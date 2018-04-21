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


Namespaced Session UIDs
-----------------------
Suppose you have a set of related triggers sessions, and you want to schedule
some tasks to run in a "super session" of sorts.

For example, let's suppose that our questionnaire application has two different
questionnaires:  "Flora" and "Fauna".  We would like to execute a trigger task
after the applicant completes page 3 of the Flora questionnaire and page 6 of
the Fauna questionnaire.  But, we can't predict what order these events will
occur.

To accomplish this, we can create a "namespaced session UID" for the applicant.
When the application is processing responses from the applicant's questionnaire,
it will actually create *two* trigger managers, each with a separate UID:

.. code-block:: python

   from my_app.models import Questionnaire

   def start_questionnaire(request):
     """
     Django view that is called when the user clicks the "start" button
     on a questionnaire.
     """
     questionnaire = get_object_or_404(
       klass = Questionnaire,
       pk    = request.POST["questionnaire_id"],
     )

     # Prepare our regular triggers session for the questionnaire.
     trigger_manager = TriggerManager(...)
     trigger_manager.update_configuration(...)

     # Prepare our "super session", which will maintain state across
     # multiple questionnaires.
     #
     # Note that the UID is tied to the applicant, not a particular
     # questionnaire.  We also add a prefix, to avoid conflicts with
     # regular trigger session UIDs.
     super_trigger_manager = TriggerManager(
       storage = CacheStorageBackend(
         uid = 'applicant:{}'.format(request.session.applicant_id),
       ),
     )

     super_trigger_manager.update_configuration({
       # This task will run after the applicant completes page 3 in the
       # Flora questionnaire, and page 6 in the Fauna questionnaire.
       't_compareResponses': {
         'after': ['flora_page3', 'fauna_page6'],
         'run': CompareResponses.name,
       },
     })

   def responses(request):
     """
     Django view that processes a page of response data from
     the client.
     """
     questionnaire = get_object_or_404(
       klass = Questionnaire,
       pk    = request.POST["questionnaire_id"],
     )

     responses_form = QuestionnaireResponsesForm(request.POST)
     if responses_form.is_valid():
       # Regular triggers session for the questionnaire.
       trigger_manager = TriggerManager(...)
       trigger_manager.fire(...)

       # Fire triggers for "super session".
       super_trigger_manager = TriggerManager(
       storage = CacheStorageBackend(
           uid = 'applicant:{}'.format(request.session.applicant_id),
         ),
       )

       super_trigger_manager.fire(
         # E.g., "fauna_page3", etc.
         trigger_name = '{}_page{}'.format(
           questionnaire.name,
           responses_form.cleaned_data['page_number'],
         ),

         trigger_kwargs = {'responses': responses_form.cleaned_data},
       )

.. _ClassRegistry: https://pypi.python.org/pypi/class-registry
.. _setup.py: https://github.com/eflglobal/triggers/blob/develop/setup.py
