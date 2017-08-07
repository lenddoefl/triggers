# coding=utf-8
from __future__ import absolute_import, division, print_function, \
    unicode_literals

from multiprocessing import Manager, Process, current_process
from threading import Thread, current_thread
from unittest import TestCase

from triggers.locking import LockAcquisitionFailed, Lockable, acquire_lock


class AcquireLockTestCase(TestCase):
    def test_threads_blocking(self):
        """
        Using blocking locks to control access to a resource among
        multiple threads.
        """
        hits    = []
        total   = []

        def maybe_hit():
            with acquire_lock(key='test', ttl=3600):
                if not hits:
                    hits.append(current_thread().getName())

            total.append(current_thread().getName())

        threads = [Thread(target=maybe_hit) for _ in range(20)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(hits), 1)
        self.assertEqual(len(total), 20)

    def test_threads_non_blocking(self):
        """
        Using non-blocking locks to control access to a resource among
        multiple threads.
        """
        hits    = []
        total   = []

        def maybe_hit():
            try:
                with acquire_lock(key='test', ttl=3600, block=False):
                    if not hits:
                        hits.append(current_thread().getName())
            except LockAcquisitionFailed:
                # We can't predict how many threads will reach this
                # point, so there's no point in tracking them.
                # fails.append(current_thread().getName())
                pass

            total.append(current_thread().getName())

        threads = [Thread(target=maybe_hit) for _ in range(20)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(hits), 1)
        self.assertEqual(len(total), 20)

    def test_processes_blocking(self):
        """
        Using blocking locks to control access to a resource among
        multiple processes.
        """
        manager = Manager()
        hits    = manager.list()
        total   = manager.list()

        def maybe_hit():
            with acquire_lock(key='test', ttl=3600):
                if not hits:
                    hits.append(current_process().ident)

            total.append(current_process().ident)

        processes = [Process(target=maybe_hit) for _ in range(0, 20)]

        for p in processes:
            p.start()

        for p in processes:
            p.join()

        self.assertEqual(len(hits), 1)
        self.assertEqual(len(total), 20)

    def test_processes_non_blocking(self):
        """
        Using non-blocking locks to control access to a resource among
        multiple processes.
        """
        manager = Manager()
        hits    = manager.list()
        total   = manager.list()

        def maybe_hit():
            # noinspection SpellCheckingInspection
            try:
                with acquire_lock(key='test', ttl=3600, block=False):
                    if not hits:
                        hits.append(current_process().ident)
            except LockAcquisitionFailed:
                # We can't predict how many processes will reach this
                # point, so there's no point in tracking them.
                # fails.append(current_process().ident)
                pass

            total.append(current_process().ident)

        processes = [Process(target=maybe_hit) for _ in range(20)]

        for p in processes:
            p.start()

        for p in processes:
            p.join()

        self.assertEqual(len(hits), 1)
        self.assertEqual(len(total), 20)


class LockableTestCase(TestCase):
    def test_acquire_multiple(self):
        """
        A Lockable instance may acquire lock multiple times.
        """
        class Locker(Lockable):
            def get_lock_name(self):
                return 'test'

        locker_1 = Locker()
        locker_2 = Locker()

        # Use a non-blocking lock to prevent the test from hanging if
        #   something goes wrong.
        with locker_1.acquire_lock(block=False):
            with locker_1.acquire_lock(block=False):
                pass

            # Releasing an "inner" lock does not release the "outer"
            #   lock; `locker_1` still has the lock.
            with self.assertRaises(LockAcquisitionFailed):
                with locker_2.acquire_lock(block=False):
                    pass

    def test_thread_safety(self):
        """
        :py:meth:`Lockable.acquire_lock` is thread-safe.

        IMPORTANT: This thread safety only applies to the lock; other
        attributes are not guaranteed to be thread-safe!
        """
        class Locker(Lockable):
            hits    = []
            total   = []

            def maybe_hit(self):
                with self.acquire_lock(ttl=3600):
                    if not self.hits:
                        self.hits.append(current_thread().getName())

                self.total.append(current_thread().getName())

            def get_lock_name(self):
                return 'test'

        # Note single instance shared among multiple threads.
        locker = Locker()

        threads = [Thread(target=locker.maybe_hit) for _ in range(20)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(locker.hits), 1)
        self.assertEqual(len(locker.total), 20)
