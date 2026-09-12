"""Force offline AI for the whole suite: no live OpenRouter calls in tests."""
import os

import pytest

os.environ["CAMPUSBITE_OFFLINE"] = "1"


@pytest.fixture(autouse=True)
def _no_queues(monkeypatch):
    """Zero live queues by default so ETA assertions are time-independent."""
    import backend.queue as q
    monkeypatch.setattr(q, "current_queues",
                        lambda: {n: 0 for n in q.COUNTERS})
