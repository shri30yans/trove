"""Reindex vocabulary: how much background work one embedding reconcile sweep may create.

The worker's sweep re-queues every memory that has no embedding yet for accounts with AI
processing on. A 20,000-memory archive would otherwise enqueue all of them at once and bury a
capture made moments later, because the queue claims jobs in availability order.
"""

from __future__ import annotations

# Memories one sweep may enqueue; the rest wait for the next sweep.
REINDEX_BATCH_LIMIT = 500
# Spacing between those jobs, so 500 reindex jobs spread over 25 minutes instead of all at once.
REINDEX_STAGGER_SECONDS = 3.0
# Hours a failed memory must sit before the sweep re-arms it, so a permanently broken memory
# cannot burn download and model attempts on every sweep.
REINDEX_RETRY_COOLDOWN_HOURS = 24.0
