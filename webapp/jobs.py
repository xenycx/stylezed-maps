"""Two small background queues so the server never does more than a little at once.

* fetch queue (1 worker): new places — OSM download + elevation. Network-bound and polite to the free OSM servers.
* render queue (RENDER_WORKERS, default 1): drawing a theme. CPU-bound, ~2–6 s each, in a subprocess.

Identical jobs are merged (two people asking for the same render share one job). Visitors poll /api/job/<id>.
"""
import itertools
import os
import queue
import threading
import time
import traceback

_ids = itertools.count(1)
_lock = threading.Lock()
_jobs = {}        # id -> Job
_by_key = {}      # key -> Job (only while queued / running)
MAX_QUEUED = int(os.environ.get("MAX_QUEUED", "60"))


class Busy(Exception):
    pass


class Job:
    def __init__(self, kind, key, fn, owner=None):
        self.id = next(_ids)
        self.kind, self.key, self.fn, self.owner = kind, key, fn, owner
        self.status, self.error, self.result = "queued", None, None
        self.created, self.started, self.finished = time.time(), None, None
        self.done = threading.Event()

    def public(self, position=None):
        return {"id": self.id, "kind": self.kind, "status": self.status, "error": self.error,
                "position": position, "seconds": round((self.finished or time.time()) - (self.started or self.created), 1)}


class Queue:
    def __init__(self, name, workers):
        self.name, self.q, self.order = name, queue.Queue(), []
        for i in range(workers):
            threading.Thread(target=self._work, name=f"{name}-{i}", daemon=True).start()

    def submit(self, kind, key, fn, owner=None):
        with _lock:
            job = _by_key.get(key)
            if job:
                return job
            if len(self.order) >= MAX_QUEUED:
                raise Busy()
            job = Job(kind, key, fn, owner)
            _jobs[job.id] = job
            _by_key[key] = job
            self.order.append(job)
        self.q.put(job)
        return job

    def position(self, job):
        with _lock:
            waiting = [j for j in self.order if j.status == "queued"]
            return waiting.index(job) + 1 if job in waiting else 0

    def _work(self):
        while True:
            job = self.q.get()
            job.status, job.started = "running", time.time()
            try:
                job.result = job.fn()
                job.status = "done"
            except Exception as e:  # noqa: BLE001
                job.status, job.error = "failed", str(e)[:1500] or type(e).__name__
                traceback.print_exc()
            finally:
                job.finished = time.time()
                with _lock:
                    _by_key.pop(job.key, None)
                    if job in self.order:
                        self.order.remove(job)
                job.done.set()
                _gc()


fetch_q = None
render_q = None


def start():
    global fetch_q, render_q
    fetch_q = Queue("fetch", 1)
    render_q = Queue("render", max(1, int(os.environ.get("RENDER_WORKERS", "1"))))


def get(job_id):
    return _jobs.get(job_id)


def describe(job):
    q = fetch_q if job.kind == "fetch" else render_q
    return job.public(q.position(job) if job.status == "queued" else None)


def find(key):
    with _lock:
        return _by_key.get(key)


def stats():
    with _lock:
        return {"fetch": {"queued": sum(j.status == "queued" for j in fetch_q.order), "running": sum(j.status == "running" for j in fetch_q.order)},
                "render": {"queued": sum(j.status == "queued" for j in render_q.order), "running": sum(j.status == "running" for j in render_q.order)}}


def _gc():
    cutoff = time.time() - 1800
    with _lock:
        for jid in [k for k, j in _jobs.items() if j.finished and j.finished < cutoff]:
            del _jobs[jid]
