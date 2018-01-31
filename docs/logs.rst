=======
Logging
=======
The trigger task's :ref:`Task Context <task_context>` provides a number of
objects and methods that are important to help a trigger task do its job
properly.

One of its most critical features is creating a logger, via its
:py:meth:`get_logger_context` method.

Typically, :py:meth:`get_logger_context` is the first statement in the task
body:

.. code-block:: python

   from triggers.task import TaskContext, TriggerTask

   class ImportSubject(TriggerTask):
     def _run(self, context):
       # type: (TaskContext) -> dict
       with context.get_logger_context() as logger:
         ...

The resulting ``logger`` instance acts like a regular :py:class:`logging.Logger`
object, with a couple of notable differences:

- You can attach "context" variables to the logger and log messages.
- The max log level emitted by this logger is recorded by the trigger manager
  for later reference.


Context Variables
-----------------
Oftentimes, it is difficult to convey all of the desired information in a log
message.  Developers often have to resort to workarounds such as tacking reprs
of critical state values onto the end of the log message.

However, this results in long, unformatted text dumps that are a pain to sift
through and contribute significantly to `warning fatigue`_.

:py:meth:`get_logger_context` tackles this problem in a different way.

When emitting a log level, your task may optionally attach a "context" object to
the log message, like this:

.. code-block:: python

   from my_app.models import Subject
   from triggers.task import TaskContext, TriggerTask

   class ImportSubject(TriggerTask):
     def _run(self, context):
       # type: (TaskContext) -> dict
       with context.get_logger_context() as logger:
         page_data =\
           context.trigger_kwargs['firstPageReceived']['responses']

         given_names = page_data.get('givenNames')
         if not given_names:
           logger.warning(
             'Missing givenNames in response data.',

             # Attach the ``page_data`` to the log message via its context dict.
             extras={'context': {
               'page_data': page_data,
             }},
           )

In the above example, a missing or empty ``givenNames`` value in the response
data is notable enough to warrant a warning message, but not an exception.

When troubleshooting this issue, it may be useful for a developer to have a full
readout of the page data.  Rather than try to include this (potentially massive)
value in the log message itself, the code attaches it to the log's ``context``
dict.

.. note::
   Depending on how your application processes log messages, you may need to
   configure your log formatter(s) specifically to take advantage of this
   feature.

   Review the `logging module documentation`_ for more information.

.. tip::
   You can also provide a dict directly to :py:meth:`get_logger_context`.  These
   context values will be attached automatically to every log message:

   .. code-block:: python

      from my_app import __version__

      class ImportSubject(TriggerTask):
        def _run(self, context):
          # type: (TaskContext) -> dict

          extra_context = {
            "app_version": __version__,
          }

          with context.get_logger_context(extra_context) as logger:
            # The application version number will be attached to every
            # log emitted by ``logger``.
            ...


Exception Context
~~~~~~~~~~~~~~~~~
As with log messages, you can also attach context values to exceptions that your
task raises.

To use this feature, pass the exception to
:py:func:`triggers.exceptions.with_context` before raising it.

As an example, suppose we wanted to add some kind of a spam filter to our
``ImportSubject`` trigger task:

.. code-block:: python

   from triggers.exceptions import with_context
   from triggers.task import TaskContext, TriggerTask

   class ImportSubject(TriggerTask):
     def _run(self, context):
       # type: (TaskContext) -> dict
       with context.get_logger_context() as logger:
         ...
         spam_score = ...
         if spam_score < threshold:
           raise with_context(
             exc = ValueError("Response data failed spam check."),

             context = {
               'spam_score': spam_score,
               'threshold': threshold,
             },
           )

The actual spam score and threshold are interesting information, but it might
not be that helpful to include them in the exception message itself (how often
do you check those values when your email application flags an email as spam)?

Still, it's useful to attach them to the exception to assist with any
troubleshooting efforts.

:py:func:`with_context` facilitates this.

.. important::
   The exception will only get logged if it is raised inside of the
   :py:meth:`get_logger_context` block!


.. _logs-tracking-log-levels:

Tracking Log Levels
-------------------
The logger returned by :py:meth:`get_logger_context` also keeps track of the
max log level emitted inside of that context.

This enables your application to track task instance failure/success with a
finer degree of granularity.

For example, if you integrate a custom trigger manager with logic to
:ref:`"finalize" a session <cookbook-finalizing>`, you may opt to have it only
finalize the session only if none of the task instances emitted log messages
with ``WARNING`` or higher level.


Task Instance Log Level
~~~~~~~~~~~~~~~~~~~~~~~
Once a task instance has finished running (successfully or otherwise), the max
log level emitted is stored in its :py:attr:`log_level` property:

.. code-block:: python

   task_instance = trigger_manager.storage['t_importSubject#0']

   task_instance.log_level       # e.g.: logging.INFO
   task_instance.log_level_name  # e.g.: 'INFO'

.. note::

   If the task instance hasn't finished running yet, its :py:attr:`log_level`
   will be ``NOTSET``.


.. _logs-resolving:

Resolving Logs
~~~~~~~~~~~~~~
In some cases, it may be necessary to mark a task instance's logs as "resolved".

For example, a task instance may emit a ``WARNING`` or ``ERROR`` log, but the
application determines that these logs are no longer relevant (e.g., a user
reviewed them and addressed any issues manually).

To resolve an instance's logs use the :py:meth:`mark_instance_logs_resolved`
method:

.. code-block:: python

   trigger_manager.mark_instance_logs_resolved('t_importSubject#0')


.. _logging module documentation: https://docs.python.org/3/library/logging.html#logging.debug
.. _warning fatigue: https://en.wikipedia.org/wiki/Alarm_fatigue
