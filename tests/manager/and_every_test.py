# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from unittest import TestCase

from triggers.manager import TriggerManager, trigger_managers
from triggers.runners import ThreadingTaskRunner
from triggers.storage_backends.base import storage_backends
from triggers.storage_backends.cache import CacheStorageBackend
from triggers.testing import PassThruTask, TriggerManagerTestCaseMixin


class TriggerManagerAndEveryTestCase(
        TriggerManagerTestCaseMixin,
        TestCase,
):
    """
    Defines tests that focus on trigger tasks that can be run multiple
    times.
    """
    def setUp(self):
        super(TriggerManagerAndEveryTestCase, self).setUp()

        storage = storage_backends.get('cache', uid=self._testMethodName) # type: CacheStorageBackend
        storage.cache.clear()

        self.manager = trigger_managers.get('default', storage=storage) # type: TriggerManager

    def test_tasks_are_one_shot_by_default(self):
        """
        Firing a trigger that has already been fired.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':   ['_finishStep'],
                'run':     PassThruTask.name,
            },
        })

        # Run the task once.
        self.manager.fire('_finishStep', {'counter': 1})
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                '_finishStep': {
                    'counter':  1,
                },
            },
        })

        # Again! Again!
        self.manager.fire('_finishStep', {'counter': 2, 'extra': 'foo'})
        ThreadingTaskRunner.join_all()

        # There is no second result because the task only ran once.
        self.assertInstanceMissing('t_alpha#1')

        # We retain the result from the first (only) time the task was
        # run.
        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                '_finishStep': {
                    'counter':  1,
                },
            },
        })

    def test_allowing_multiple(self):
        """
        Firing a trigger multiple times for a task that supports
        multiple execution.
        """
        self.manager.update_configuration({
            # This task will be invoked without any kwargs.
            't_alpha': {
                'after':    [],
                'andEvery': '_finishStep',
                'run':      PassThruTask.name,
            },

            # This task will use its configured kwargs when it is
            # invoked.
            't_bravo': {
                'after':    [],
                'andEvery': '_finishStep',
                'run':      PassThruTask.name,

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
                'after':    [],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('_finishStep')
        ThreadingTaskRunner.join_all()

        # No surprises so far.
        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                '_finishStep': {},
            },
        })

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                '_finishStep':  {'name': 'observations'},
                'extra':        {'stuff': 'arbitrary'},
            },
        })

        self.assertInstanceMissing('t_charlie#0')

        # Let's see what happens when we fire the trigger a second
        # time.
        self.manager.fire('_finishStep')
        ThreadingTaskRunner.join_all()

        # A shiny new instance of each task is created!
        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                '_finishStep': {},
            },
        })

        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                '_finishStep':  {'name': 'observations'},
                'extra':        {'stuff': 'arbitrary'},
            },
        })

        self.assertInstanceMissing('t_charlie#0')

    def test_kwargs(self):
        """
        Running a task multiple times with different kwargs.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    [],
                'andEvery': '_finishStep',
                'run':      PassThruTask.name,
            },

            # This task's ``_finishStep`` kwargs will be overridden by
            # the kwargs provided to ``manager.fire``.
            't_bravo': {
                'after':   [],
                'andEvery': '_finishStep',

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
                'after':    [],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
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

        # And now for something completely different.
        self.manager.fire(
            trigger_name    = '_finishStep',
            trigger_kwargs  = {'name': 'Dave', 'greeting': 'Goodbye'},
        )
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                '_finishStep': {
                    # This conversation can serve no purpose anymore.
                    'greeting': 'Goodbye',
                    'name':     'Dave',
                },
            },
        })

        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                '_finishStep': {
                    'greeting': 'Goodbye',
                    'name':     'Dave',
                    'status':   'clone',
                },

                'extra': {
                    'stuff': 'arbitrary'
                }
            },
        })

        # The original results are unmodified.
        # Note that we are checking the ``#0`` instance here.
        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                '_finishStep': {
                    'greeting': 'Hello',
                    'name':     'Dolly',
                },
            },
        })

    def test_complex_trigger(self):
        """
        Running a task with a complex trigger multiple times.
        """
        self.manager.update_configuration({
            # This task will be invoked without any kwargs.
            't_alpha': {
                'after':    ['dataReceived'],
                'andEvery': 'creditsDepleted',
                'run':      PassThruTask.name,
            },

            # This task will use its configured kwargs when it is
            # invoked.
            't_bravo': {
                'after':    ['dataReceived'],
                'andEvery': 'creditsDepleted',
                'run':      PassThruTask.name,

                'withParams': {
                    'dataReceived': {'name': 'Han'},
                    'calibration':  {'name': 'Greedo'},
                },
            },

            # Control group:  This task will not fire (requires extra
            # trigger).
            't_charlie': {
                'after':    ['dataReceived', 'registerComplete'],
                'andEvery': 'creditsDepleted',
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        # TaskInstance objects were created to store the trigger
        # kwargs, but none of them are ready to run yet.
        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_charlie#0')

        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived':     {},
                'creditsDepleted':  {},
            },
        })

        # The task config's kwargs get applied when the task runs.
        # Note that the keys do not have to match trigger names.
        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                'calibration':      {'name': 'Greedo'},
                'dataReceived':     {'name': 'Han'},
                'creditsDepleted':  {},
            },
        })

        self.assertInstanceUnstarted('t_charlie#0')

        # All of the tasks are configured to handle multiple ``creditsDepleted``
        # triggers.  Let's see what happens if we fire a different
        # one.
        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        # No TaskInstances were created!
        self.assertInstanceMissing('t_alpha#1')
        self.assertInstanceMissing('t_bravo#1')

        # Let them eat...
        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                'dataReceived':     {},
                'creditsDepleted':  {},
            },
        })

        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                'calibration':      {'name': 'Greedo'},
                'dataReceived':     {'name': 'Han'},
                'creditsDepleted':  {},
            },
        })

    def test_complex_trigger_kwargs(self):
        """
        Running a task with a complex trigger multiple times,
        specifying different kwargs.
        """
        self.manager.update_configuration({
            # This task will be invoked without any kwargs.
            't_alpha': {
                'after':    ['creditsDepleted'],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
            },

            # We will provide kwargs to the ``dataReceived`` trigger, which
            # will override the ``dataReceived`` kwargs configured here, but
            # the other kwargs will be unaffected.
            't_bravo': {
                'after':    ['creditsDepleted'],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,

                'withParams':  {
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

            # Control group: This task will not fire (requires extra
            # trigger).
            't_charlie': {
                'after':    ['creditsDepleted', 'registerComplete'],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
            },
        })

        # Let's see what happens if we specify kwargs for ``dataReceived``...
        self.manager.fire('dataReceived', {'name': 'Rarity', 'leader': False})
        ThreadingTaskRunner.join_all()

        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_charlie#0')

        # ... but none for ``creditsDepleted``.
        self.manager.fire('creditsDepleted')
        ThreadingTaskRunner.join_all()

        # ``t_alpha`` config does not have kwargs, so the task only
        # received the kwargs we provided for the ``dataReceived`` trigger.
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
                },
            },
        })

        self.assertInstanceUnstarted('t_charlie#0')

        # Let's try that again....
        self.manager.fire(
            trigger_name    = 'dataReceived',
            trigger_kwargs  = {'leader': True, 'name': 'Big Macintosh'},
        )

        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                'dataReceived': {
                    'leader':   True,
                    'name':     'Big Macintosh',
                },

                'creditsDepleted': {},
            },
        })

        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                'dataReceived': {
                    'leader':   True,
                    'name':     'Big Macintosh',
                    'species':  'unknown',
                },

                # Note that the kwargs from the ``creditsDepleted``
                # trigger are retained.
                'creditsDepleted': {
                    'name':     'Twilight Sparkle',
                },

                'calibration': {
                    'name':     'Fluttershy',
                },
            },
        })

    def test_cascade(self):
        """
        A task runs multiple times, and the resulting cascading
        triggers cause other tasks to run.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    [],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
            },

            # Now things REALLY start getting interesting.
            't_bravo': {
                'after':    [],
                'andEvery': 't_alpha',
                'run':      PassThruTask.name,
            },

            't_charlie': {
                'after':    [],
                'andEvery': 't_alpha',
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

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha':  {
                    'kwargs': {
                        'dataReceived': {},
                    },
                },
            }
        })

        self.assertInstanceFinished('t_charlie#0', {
            'kwargs': {
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

        # Once more unto the breach!
        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        # New instances were created for ``t_alpha`` and all of its
        # dependent tasks.
        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                'dataReceived': {},
            },
        })

        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                't_alpha':  {
                    'kwargs': {
                        'dataReceived': {},
                    },
                },
            }
        })

        self.assertInstanceFinished('t_charlie#1', {
            'kwargs': {
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

    def test_cascade_kwargs(self):
        """
        A task runs multiple times with different kwargs, and the
        resulting cascading triggers cause other tasks to run as
        well.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    [],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
            },

            't_bravo': {
                'after':    [],
                'andEvery': 't_alpha',
                'run':      PassThruTask.name,

                'withParams': {
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
                'after':    [],
                'andEvery': 't_alpha',
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived', {'rating': '4.5'})
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived': {'rating': '4.5'},
            },
        })

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {'rating': '4.5'},
                    },

                    'partitionOnLetter': True,
                    'partitionOnNumber': False,
                },

                'arbitrary': {
                    'expected': 'maybe',
                },
            },
        })

        self.assertInstanceFinished('t_charlie#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {'rating': '4.5'},
                    },
                },
            },
        })

        # This time with feeling!
        self.manager.fire('dataReceived', {'rating': '3.2', 'alternate': True})
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#1', {
            # As expected, the different kwargs get passed along to the
            # second ``t_alpha`` instance.
            'kwargs': {
                'dataReceived': {
                    'rating':  '3.2',
                    'alternate':    True,
                },
            },
        })

        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                't_alpha': {
                    # The results of ``t_alpha#1`` cascade.
                    'kwargs': {
                        'dataReceived': {
                            'rating':       '3.2',
                            'alternate':    True,
                        },
                    },

                    'partitionOnLetter': True,
                    'partitionOnNumber': False,
                },

                'arbitrary': {
                    'expected': 'maybe',
                },
            },
        })

        self.assertInstanceFinished('t_charlie#1', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {
                            'rating':       '3.2',
                            'alternate':    True,
                        },
                    },
                },
            },
        })

    def test_cascade_complex_trigger(self):
        """
        A task runs multiple times, but the resulting cascading
        triggers are not sufficient to cause other tasks with
        complex triggers to run.
        """
        self.manager.update_configuration({
            't_alpha': {
                # You only get to pick *one* trigger for
                # ``andEvery``.
                'after':    ['creditsDepleted'],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,

            },

            't_bravo': {
                # Note that this task will only run after
                # ``t_alpha`` has completed AND the ``registerComplete``
                # trigger is fired.
                'after':    ['registerComplete'],
                'andEvery': 't_alpha',
                'run':      PassThruTask.name,
            },

            # Control group:  Will not run because it requires an extra
            # trigger that will not be fired during this test.
            't_charlie': {
                'after':    ['demo'],
                'andEvery': 't_alpha',
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceMissing('t_bravo#0')
        self.assertInstanceMissing('t_charlie#0')

        self.manager.fire('creditsDepleted', {'time': 42})
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived': {},

                'creditsDepleted': {
                    'time': 42,
                },
            },
        })

        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_charlie#0')

        self.manager.fire('registerComplete')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {},

                        'creditsDepleted': {
                            'time': 42,
                        },
                    },
                },

                'registerComplete': {},
            },
        })

        self.assertInstanceUnstarted('t_charlie#0')

        # Trigger ``t_alpha`` to run again.
        self.manager.fire('dataReceived', {'alternate': True})
        ThreadingTaskRunner.join_all()

        # ``creditsDepleted`` already fired, so a second ``t_alpha`` instance is
        # created and runs immediately.
        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                'dataReceived': {
                    'alternate': True,
                },

                'creditsDepleted': {
                    'time': 42,
                },
            },
        })

        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived': {
                            'alternate': True,
                        },

                        'creditsDepleted': {
                            'time': 42,
                        },
                    },
                },

                'registerComplete': {},
            },
        })

        # An additional instance of ``t_charlie`` was created to
        # collect kwargs from the second ``t_alpha``, but it is not
        # ready to run because ``demo`` hasn't fired yet.
        self.assertInstanceUnstarted('t_charlie#1')

    def test_cascade_one_shot(self):
        """
        A task that allows multiple causes cascades, triggering one-
        shot tasks.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    [],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
            },

            # This task is configured as a one-shot.
            't_bravo': {
                'after':    ['t_alpha'],
                'run':      PassThruTask.name,

            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {'dataReceived': {}},
        })

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {'dataReceived': {}},
                },
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {'dataReceived': {}},
        })

        # Since ``t_bravo`` is one-shot, a second instance is NOT
        # created.
        self.assertInstanceMissing('t_bravo#1')

    def test_cascade_one_shot_reverse(self):
        """
        A task has ``andEvery`` set to the name of a one-shot task.
        """
        self.manager.update_configuration({
            # This task is configured as a one-shot.
            't_alpha': {
                'after':    ['dataReceived'],
                'run':      PassThruTask.name,
            },

            't_bravo': {
                'after':    [],
                'andEvery': 't_alpha',
                'run':      PassThruTask.name,
            },
        })

        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {'dataReceived': {}},
        })

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {'dataReceived': {}},
                },
            },
        })

        # Do it again.
        self.manager.fire('dataReceived')
        ThreadingTaskRunner.join_all()

        # Since ``t_alpha`` is a one-shot, it does NOT run a second
        # time.
        self.assertInstanceMissing('t_alpha#1')

        # Since ``t_alpha`` never runs a second time, it also does
        # not cause a second cascade.
        self.assertInstanceMissing('t_bravo#1')

    def test_deferred_kwargs(self):
        """
        An instance of an ``andEvery`` task isn't created until
        after trigger kwargs have changed.
        """
        self.manager.update_configuration({
            't_alpha': {
                'after':    ['creditsDepleted'],
                'andEvery': 'dataReceived',
                'run':      PassThruTask.name,
            },

            't_bravo': {
                'after':    ['creditsDepleted'],
                'andEvery': 't_alpha',
                'run':      PassThruTask.name,
            },

            't_charlie': {
                # Just to make things interesting, let's flip the value
                # of ``andEvery`` and see what happens.
                'after':    ['t_alpha'],
                'andEvery': 'creditsDepleted',
                'run':      PassThruTask.name,

            },
        })

        self.manager.fire('creditsDepleted', {'counter': 1})
        ThreadingTaskRunner.join_all()

        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_charlie#0')

        self.manager.fire('creditsDepleted', {'counter': 2})
        ThreadingTaskRunner.join_all()

        self.assertInstanceUnstarted('t_alpha#0')
        self.assertInstanceUnstarted('t_bravo#0')
        self.assertInstanceUnstarted('t_charlie#0')

        # An extra instance of ``t_charlie`` is created to store the
        # new kwargs.
        self.assertInstanceUnstarted('t_charlie#1')

        self.manager.fire('dataReceived', {'counter': 3})
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#0', {
            'kwargs': {
                'dataReceived': {'counter': 3},

                # When ``t_alpha#0`` was created, the ``creditsDepleted``
                # trigger had fired with ``counter=1``.
                'creditsDepleted': {'counter': 1},
            },
        })

        self.assertInstanceFinished('t_bravo#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived':     {'counter': 3},
                        'creditsDepleted':  {'counter': 1},
                    },
                },

                # At the moment that ``t_bravo#0`` was created, the
                # ``creditsDepleted`` trigger had fired with
                # ``counter=1``.
                'creditsDepleted': {'counter': 1},
            },
        })

        self.assertInstanceFinished('t_charlie#0', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived':     {'counter': 3},
                        'creditsDepleted':  {'counter': 1},
                    },
                },

                # At the moment that ``t_charlie#0`` was created, the
                # ``creditsDepleted`` trigger had fired with
                # ``counter=1``.
                'creditsDepleted': {'counter': 1},
            },
        })

        self.assertInstanceFinished('t_charlie#1', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived':     {'counter': 3},
                        'creditsDepleted':  {'counter': 1},
                    },
                },

                # At the moment that ``t_charlie#1`` was created, the
                # ``creditsDepleted`` trigger had fired with
                # ``counter=2``.
                'creditsDepleted': {'counter': 2},
            },
        })

        self.manager.fire('dataReceived', {'counter': 4})
        ThreadingTaskRunner.join_all()

        self.assertInstanceFinished('t_alpha#1', {
            'kwargs': {
                'dataReceived': {'counter': 4},

                # At the moment that ``t_alpha#1`` was created, the
                # most recent ``creditsDepleted`` trigger was fired
                # with ``counter=2``.
                'creditsDepleted': {'counter': 2},
            },
        })

        # An additional ``t_bravo`` instance was created to process the
        # result of the cascading ``t_alpha`` task.
        self.assertInstanceFinished('t_bravo#1', {
            'kwargs': {
                't_alpha': {
                    'kwargs': {
                        'dataReceived':     {'counter': 4},
                        'creditsDepleted':  {'counter': 2},
                    },
                },

                'creditsDepleted': {'counter': 2},
            },
        })
