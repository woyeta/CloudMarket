"""
Per-request stage timing.

StageTimer collects how long each stage of a request took (DB connect,
cache lookup, embedding call, DB queries, LLM call, ...) and renders the
result as a Server-Timing header, so every response shows where its time went.
"""

import time
from contextlib import contextmanager

from django.db import connection


class StageTimer:

    def __init__(self):
        self._start = time.perf_counter()
        self.stages = {}   # stage name -> milliseconds
        self.notes = {}    # stage name -> short description, e.g. "hit" / "miss"

    def add(self, name, ms):
        self.stages[name] = self.stages.get(name, 0.0) + ms

    @contextmanager
    def stage(self, name):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add(name, (time.perf_counter() - t0) * 1000)

    @contextmanager
    def track_db(self):
        """Sum the execution time of every SQL query run inside the block."""
        def wrapper(execute, sql, params, many, context):
            t0 = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                self.add("db", (time.perf_counter() - t0) * 1000)

        with connection.execute_wrapper(wrapper):
            yield

    def total_ms(self):
        return (time.perf_counter() - self._start) * 1000

    def header(self):
        parts = []
        for name, ms in self.stages.items():
            part = f"{name};dur={ms:.1f}"
            if name in self.notes:
                part += f';desc="{self.notes[name]}"'
            parts.append(part)
        parts.append(f"total;dur={self.total_ms():.1f}")
        return ", ".join(parts)
