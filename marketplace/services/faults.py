"""
Fault injection for simulating a Gemini outage.

Does nothing unless ALLOW_FAULT_INJECTION is true. Modes (GEMINI_FAULT):
- "fail": the call raises immediately (like a 503 or 429).
- "hang": the call waits until our own timeout and then raises, which is
  what a hung dependency plus a client timeout looks like. The sleep happens
  in our code, where the HTTP timeout cannot interrupt it, so the sleep is
  capped at the timeout explicitly.
"""

import time

from django.conf import settings


class InjectedFault(Exception):
    pass


def maybe_inject(timeout_ms: int):
    if not settings.ALLOW_FAULT_INJECTION:
        return
    mode = settings.GEMINI_FAULT
    if mode == "fail":
        raise InjectedFault("injected failure")
    if mode == "hang":
        hang_s = settings.GEMINI_FAULT_HANG_S
        if timeout_ms:
            hang_s = min(hang_s, timeout_ms / 1000)
        time.sleep(hang_s)
        raise TimeoutError("injected hang")
