============
Introduction
============
The Triggers framework is essentially a distributed implementation of the
`Observer pattern`_.  It keeps track of "triggers" that your application fires,
and schedules asynchronous tasks to run in response.

On the surface, this seems simple enough, but what make the Triggers framework
so compelling (at least, in the eyes of the person writing this documentation)
are:

- It is designed for distributed applications.  You can track events that occur
  across multiple VMs.
- It uses a persistent storage backend to maintain state.  It can schedule tasks
  in response to events, even if they occur days, weeks, even months apart.
- It uses an intuitive JSON configuration schema, allowing administrators to
  create complex workflows without having to write any (Python) code.

What Are Triggers Useful For
============================
The Triggers framework may be a good fit for your application if:

- It needs to be able to schedule asynchronous tasks when sets of 2 or more
  conditions are met, and
- You can't predict when, what order, or even if each of the different
  conditions will be met.

For example, suppose you have a survey application, and you want to schedule an
asynchronous task to run after modules 1 and 4 are received from the client.

However, because of the way the internet works, module 4 might never arrive, or
perhaps the two modules arrive out-of-order, or even at the same time.

The Triggers framework would be a good fit for this application.

What Are Triggers Not Useful For
================================

If your application:

- Is not distributed (e.g., only has one application server), or
- Does not need to maintain state across requests,

then the Triggers framework might be overkill.

For example, using the survey application from the previous section, suppose
that the client always sent the data for modules 1 and 4 in the same web service
request.

In this case, you wouldn't need to use the Triggers framework because your
application would not need to keep track of which modules were received across
multiple web service requests.

=============
Configuration
=============
Let's go back to the example survey application, and see how we might configure
the Triggers framework to execute an asynchronous task after modules 1 and 4 are
received:

.. code-block:: javascript

   {
     // Give your task a name.
     "t_processStepData": {

       // This task runs after these two triggers are fired.
       // Note that order doesn't matter here.
       "after": ["module1Received", "module4Received"],

       // Specify the celery task to run when the above conditions are
       // met.
       "run": "my_app.tasks.ProcessStepData"
     }
   }

That's it!  The Triggers framework will take it from there.

We'll explore exactly what this configuration means, and how to set up more
complex workflows in the :doc:`Configuration </configuration>` section.


.. _Observer pattern: https://en.wikipedia.org/wiki/Observer_pattern
