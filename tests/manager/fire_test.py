# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from datetime import datetime
from unittest import TestCase

from triggers.manager import TriggerManager, trigger_managers
from triggers.runners import ThreadingTaskRunner
from triggers.storage_backends.base import storage_backends
from triggers.storage_backends.cache import CacheStorageBackend
from triggers.testing import DevNullTask, PassThruTask, \
    TriggerManagerTestCaseMixin
from triggers.types import TaskInstance


class TriggerManagerFireTestCase(TriggerManagerTestCaseMixin, TestCase):
    """
    Defines tests that focus on firing triggers and the consequences
    thereof.
    """
    def setUp(self):
        super(TriggerManagerFireTestCase, self).setUp()

        storage = storage_backends.get('cache', uid=self._testMethodName) # type: CacheStorageBackend
        storage.cache.clear()

        self.manager = trigger_managers.get('default', storage=storage) # type: TriggerManager

    def test_fire(self):
        """
        Firing a trigger causes tasks to run.
        """
        self.manager.update_configuration({
            # This task will be invoked without any kwargs.
            't_alpha': {
                'after':   ['_finishStep'],
                'run':     PassThruTask.name,
            },

            # This task will use its configured kwargs when it is
            # invoked.
            't_bravo': {
                'after':   ['_finishStep'],
                'run':     PassThruTask.name,

                'withParams':  {
                    '_finishStep': {
                        'name': 'observations',
                    },

                    'extra': {
                        'stuff': 'arbitrary',
                    },
                },
            },

            # Control group:  This task will not get invoked (different
            # trigger).
            't_charlie': {
                'after':   ['dataReceived'],
                'run':     PassThruTask.name,
            },
        })

        self.manager.fire('_finishStep')
        ThreadingTaskRunner.join_all()

        # In a real-world scenario, the status of the matching steps
        # would actually be 'scheduled', but because Celery tasks
        # operate in eager mode during unit tests, the tasks get
        # executed immediately.

        # This task config has no kwargs, so no `name` was passed to
        # the task.
        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                '_finishStep': {},
            },
        })

        # The task config's kwargs get applied when the task runs.
        # Note that the keys do not have to match trigger names.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                '_finishStep':  {'name': 'observations'},
                'extra':        {'stuff': 'arbitrary'},
            },
        })

        # This task doesn't run because its trigger never fired.
        self.assertInstanceMissing('t_charlie#0')

    def test_fire_kwargs(self):
        """
        Firing a trigger with custom kwargs.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':   ['_finishStep'],
                'run':     PassThruTask.name,
            },

            # This task's ``_finishStep`` kwargs will be overridden by
            # the kwargs provided to `manager.fire`.
            't_bravo': {
                'after':   ['_finishStep'],
                'run':     PassThruTask.name,

                'withParams':  {
                    '_finishStep': {
                        'name':     'observations',
                        'status':   'clone',
                    },

                    'extra': {
                        'stuff': 'arbitrary',
                    },
                },
            },

            # Control group:  This task will not get invoked (different
            # trigger).
            't_charlie': {
                'after':   ['dataReceived'],
                'run':     PassThruTask.name,
            },
        })

        self.manager.fire(
            trigger_name    = '_finishStep',
            trigger_kwargs  = {'name': 'Dolly', 'greeting': 'Hello'},
        )
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                '_finishStep': {
                    'greeting': 'Hello',
                    'name':     'Dolly',
                },
            },
        })

        # kwargs passed to ``manager.fire`` override the task config's
        # kwargs, but only for the matching trigger.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                # Note that the kwargs we passed to ``manager.fire``
                # were merged into the task's kwargs.
                '_finishStep': {
                    'greeting': 'Hello',
                    'name':     'Dolly',
                    'status':   'clone',
                },

                'extra': {
                    'stuff': 'arbitrary',
                },
            },
        })

        # This task doesn't run because its trigger never fired.
        self.assertInstanceMissing('t_charlie#0')

    def test_fire_complex_trigger(self):
        """
        Invoking a task that requires multiple triggers to fire.
        """
        self.manager.update_configuration({
            # This task will be invoked without any kwargs.
            't_alpha': {
                'after':   ['dataReceived', 'creditsDepleted'],
                'run':     PassThruTask.name,
            },

            # This task will use its configured kwargs when it is
            # invoked.
            't_bravo': {
                'after':   ['dataReceived', 'creditsDepleted'],
                'run':     PassThruTask.name,

                'withParams':  {
                    # Remember:  execution order is always
                    # unpredictable in the trigger framework!
                    'dataReceived': {
                        'name': 'Han',
                    },

                    'calibration': {
                        'name': 'Greedo',
                    },
                },
            },

            # Control group:  This task will not fire (requires extra
            # trigger).
            't_psych2': {
                'after': [
                    'creditsDepleted',
                    'dataReceived',
                    'registerComplete',
                ],

                'run': PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        # We can't run matching tasks yet because they require both
        # ``dataReceived`` and ``creditsDepleted``.
        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_psych2#0')

        # Once both triggers fire, then the task runs.
        # Note that the task receives both sets of kwargs.
        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived':   {},
                'creditsDepleted':       {},
            },
        })

        # The task config's kwargs get applied when the task runs.
        # Note that the keys do not have to match trigger names.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                # Don't get excited; I'm just listing them
                # alphabetically.
                'dataReceived':       {'name': 'Han'},
                'calibration':  {'name': 'Greedo'},
                'creditsDepleted':           {},
            },
        })

        # ``t_psych2`` doesn't get run because it is still waiting for
        # the `registerComplete` trigger to fire.
        self.assertInstanceUnstarted('t_psych2#0')

    def test_fire_complex_trigger_kwargs(self):
        """
        Invoking a task that requires multiple triggers to fire,
        providing custom kwargs each time.
        """
        self.manager.update_configuration({
            # This task will be invoked without any kwargs.
            't_alpha': {
                'after':   ['dataReceived', 'creditsDepleted'],
                'run':     PassThruTask.name,
            },

            # We will provide kwargs to the ``dataReceived`` trigger,
            # which will override the ``dataReceived`` kwargs
            # configured here, but the other kwargs will be unaffected.
            't_bravo': {
                'after':   ['dataReceived', 'creditsDepleted'],
                'run':     PassThruTask.name,

                'withParams':  {
                    # My Little Pony reboot references...
                    # I always knew one day it would come to this.
                    'dataReceived': {
                        'name':     'Rainbow Dash',
                        'species':  'unknown',
                    },

                    'creditsDepleted': {
                        'name': 'Twilight Sparkle',
                    },

                    'calibration': {
                        'name': 'Fluttershy',
                    },
                },
            },

            # Control group:  This task will not fire (requires extra
            # trigger).
            't_psych2': {
                'after': [
                    'creditsDepleted',
                    'dataReceived',
                    'registerComplete',
                ],

                'run': PassThruTask.name,
            },
        })

        # Let's see what happens if we specify kwargs for
        # ``dataReceived``...
        self.manager.fire('dataReceived', {'name': 'Rarity', 'leader': False})
        ThreadingTaskRunner.join_all()

        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_psych2#0')

        # ... but none for ``creditsDepleted``.
        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        # ``t_alpha`` config does not have kwargs, so the task only
        # received the kwargs we provided for the ``dataReceived``
        # trigger.
        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived': {
                    'leader':   False,
                    'name':     'Rarity',
                },

                'creditsDepleted': {},
            },
        })

        # ``t_bravo`` config has kwargs.  We merged kwargs for
        # ``dataReceived``, but none of the other ones.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                'dataReceived': {
                    'leader':   False,
                    'name':     'Rarity',
                    'species':  'unknown',
                },

                'creditsDepleted': {
                    'name': 'Twilight Sparkle',
                },

                'calibration': {
                    'name': 'Fluttershy',
                }
            },
        })

        self.assertInstanceUnstarted('t_psych2#0')

    def test_fire_cascade(self):
        """
        Firing a trigger successfully causes subsequent triggers to
        fire.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':   ['dataReceived'],
                'run':     PassThruTask.name,
            },

            't_bravo': {
                'after':    ['t_alpha'],
                'run':      PassThruTask.name,
            },

            't_charlie': {
                'after':    ['t_alpha'],
                'run':      PassThruTask.name,

                'withParams': {
                    't_alpha': {
                        'foo': 'bar',

                        #
                        # Just to be tricky, try to replace the result
                        # of ``t_alpha`` that gets passed along to
                        # ``t_charlie``.
                        #
                        # The trigger framework will allow you to
                        # inject values, but you can't replace them.
                        #
                        # Relying on this is probably an anti-pattern,
                        # but the trigger framework won't judge you
                        # (although I can't say the same for your
                        # peers).
                        #
                        'kwargs':   {
                            'hacked': True,
                        },
                    },

                    'geek_pun': {
                        'baz': 'luhrmann',
                    },
                },
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        # As expected, this causes the ``t_alpha`` task to run.
        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived': {},
            },
        })

        # Then, once the task finishes, it fires its own name as a
        # trigger, causing the ``t_bravo`` and ``t_charlie`` tasks to run.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                # ``t_alpha`` passed its result along.
                't_alpha':  {
                    'kwargs': {
                        'dataReceived': {},
                    },
                },
            }
        })

        self.assertInstanceFinished('t_charlie#0', {
            'kwargs': {
                # The task kwargs were merged into the instance kwargs
                # recursively.
                #
                # The result is... confusing, which is why you probably
                # shouldn't ever rely on this functionality.
                't_alpha':  {
                    'foo': 'bar',

                    'kwargs': {
                        'dataReceived': {},
                        'hacked': True,
                    },
                },

                'geek_pun': {'baz': 'luhrmann'},
            },
        })

    def test_fire_cascade_kwargs(self):
        """
        Firing a trigger successfully causes subsequent triggers to
        fire, with the result of the successful task acting as
        kwargs for the cascading tasks.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':   ['dataReceived'],
                'run':     PassThruTask.name,
            },

            't_bravo': {
                'after':    ['t_alpha'],
                'run':      PassThruTask.name,

                'withParams': {
                    # Inject some flags into the result of
                    # ``t_alpha``.
                    't_alpha': {
                        'partitionOnLetter': True,
                        'partitionOnNumber': False,
                    },

                    'arbitrary': {
                        'expected': 'maybe',
                    },
                },
            },

            't_charlie': {
                'after':    ['t_alpha'],
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived', {'inattention': '4.5'})
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived': {'inattention': '4.5'},
            },
        })

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    # In a more realistic scenario, this would look
                    # like e.g., ``{"score": "red"}``, but we're trying
                    # to keep things simple for unit tests.
                    'kwargs': {
                        'dataReceived': {'inattention': '4.5'},
                    },

                    # Task kwargs get injected.
                    'partitionOnLetter': True,
                    'partitionOnNumber': False,
                },

                # As expected by this point, any extra kwargs included
                # in the task configuration are passed along as well.
                'arbitrary': {
                    'expected': 'maybe',
                },
            },
        })

        self.assertInstanceFinished('t_charlie#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {'inattention': '4.5'},
                    },
                },
            },
        })

    def test_fire_cascade_complex_trigger(self):
        """
        Firing a trigger successfully causes cascade, but matching
        task has unsatisfied complex trigger.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['dataReceived', 'creditsDepleted'],
                'run':      PassThruTask.name,
            },

            't_bravo': {
                # Note that this task will only run after
                # ``t_alpha`` has completed AND the ``registerComplete``
                # trigger is fired.
                'after':    ['t_alpha', 'registerComplete'],
                'run':      PassThruTask.name,
            },

            # Control group:  Will not run because it requires an extra
            # trigger that will not be fired during this test.
            't_charlie': {
                'after':    ['t_alpha', 'demo'],
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        # ``t_alpha#0`` was created to store kwargs.
        self.assertInstanceUnstarted('t_alpha#0')

        # The other tasks have no instances yet, since none of their
        # triggers fired.
        self.assertInstanceMissing('t_bravo#0')
        self.assertInstanceMissing('t_charlie#0')

        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived':   {},
                'creditsDepleted':       {},
            },
        })

        # New instances were created to store kwargs, but not all of
        # their triggers have fired yet.
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_charlie#0')

        self.manager.fire('registerComplete')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived':     {},
                        'creditsDepleted':  {},
                    },
                },

                'registerComplete': {},
            },
        })

        self.assertInstanceUnstarted('t_charlie#0')

    def test_fire_cascade_complex_trigger_reverse(self):
        """
        Firing a trigger successfully causes cascade, and matching
        task's complex trigger is satisfied.

        This is basically a reverse of the previous test.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['dataReceived', 'creditsDepleted'],
                'run':      PassThruTask.name,
            },

            't_bravo': {
                # Note that this task will only run after
                # ``t_alpha`` has completed AND the ``registerComplete``
                # trigger is fired.
                'after':    ['t_alpha', 'registerComplete'],
                'run':      PassThruTask.name,
            },

            # Control group:  Will not run because it requires an extra
            # trigger that will not be fired during this test.
            't_charlie': {
                'after':    ['t_alpha', 'demo'],
                'run':      PassThruTask.name,
            },
        })

        # This time, we'll fire ``registerComplete`` first and THEN
        # we'll trigger ``t_alpha``.
        self.manager.fire('registerComplete')
        ThreadingTaskRunner.join_all()

        self.assertInstanceMissing('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceMissing('t_charlie#0')

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceMissing('t_charlie#0')

        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived':     {},
                'creditsDepleted':  {},
            },
        })

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived':     {},
                        'creditsDepleted':  {},
                    },
                },

                'registerComplete': {},
            },
        })

        self.assertInstanceUnstarted('t_charlie#0')

    def test_redundant_trigger(self):
        """
        Firing a task whose trigger contains parts of its dependencies'
        triggers.

        This is useful when you want Task B to run after Task A, but
        you also want some of Task A's kwargs to be accessible to
        Task B.

        In these unit tests, we are using PassThruTask so that every
        task returns its kwargs, so this seems like a really weird
        use case.

        But, in a real-world scenario, tasks will return all kinds of
        different values, so the "redundant trigger" scenario may
        come up a lot more than you'd expect.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['dataReceived', 'creditsDepleted'],
                'run':      DevNullTask.name,
            },

            't_bravo': {
                # ``dataReceived`` seems redundant here, since it's
                # included in the trigger for ``t_alpha``, but it's
                # actually very important, as we'll see later.
                'after':    ['t_alpha', 'dataReceived'],
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire(
            trigger_name    = 'dataReceived',
            trigger_kwargs  = {'section_timer': '42', 'test_admin': 'bob'},
        )
        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        # Note that ``t_alpha`` is configured to run DevNullTask in
        # this test, so it returns an empty result.
        self.assertInstanceFinished('t_alpha#0', {})

        # Once ``t_alpha`` fires, ``t_bravo`` runs.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                # As expected, ``t_alpha`` provided an empty result
                # to ``t_bravo``.
                't_alpha': {},

                # The ``dataReceived`` kwargs are also passed along!
                # If we didn't add ``dataReceived`` to the ``t_bravo``
                # task's trigger, the task would have no way to access
                # these values!
                'dataReceived': {
                    'section_timer':    '42',
                    'test_admin':       'bob',
                },
            },
        })

    def test_update_task_metadata(self):
        """
        Updating an instance's metadata without changing its status.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['__marketingOptIn'],
                'run':      DevNullTask.name,
            },
        })

        timestamp = datetime(2017, 3, 13, 12, 22, 47)

        with self.manager.storage.acquire_lock() as writable_storage: # type: CacheStorageBackend
            instance =\
                writable_storage.create_instance(
                    task_config = writable_storage.tasks['t_alpha'],
                )

            # Simulate the instance completing successfully.
            instance.status = TaskInstance.STATUS_FINISHED

            instance.metadata[TaskInstance.META_TIMESTAMPS] = {
                TaskInstance.TIMESTAMP_CREATED:         timestamp,
                TaskInstance.TIMESTAMP_LAST_MODIFIED:   timestamp,
                TaskInstance.STATUS_FINISHED:           timestamp,
            }

            writable_storage.save()

        self.manager.update_task_metadata(
            instance_name = 't_alpha#0',

            metadata = {
                'foo': 'bar',
                'baz': 'luhrmann',
            },
        )

        instance = self.manager.storage.instances['t_alpha#0'] # type: TaskInstance

        # Values added to the instance's metadata attribute.
        self.assertEqual(instance.metadata['foo'], 'bar')
        self.assertEqual(instance.metadata['baz'], 'luhrmann')

        # Updating metadata did not change the instance's status.
        self.assertEqual(instance.status, TaskInstance.STATUS_FINISHED)

        # The ``lastModified`` timestamp is bumped, but the other
        # timestamps remain untouched.
        self.assertNotEqual(instance.last_modified, timestamp)

        self.assertEqual(
            instance.metadata
                [TaskInstance.META_TIMESTAMPS]
                [TaskInstance.TIMESTAMP_CREATED],

            timestamp,
        )

        self.assertEqual(
            instance.metadata
                [TaskInstance.META_TIMESTAMPS]
                [TaskInstance.STATUS_FINISHED],

            timestamp,
        )
