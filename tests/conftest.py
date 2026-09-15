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


@pytest.fixture(autouse=True)
def _clear_phrase_cache():
    """Phrase cache must never leak between tests (stale paraphrases)."""
    import backend.llm as llm
    llm.clear_phrase_cache()
    yield
    llm.clear_phrase_cache()


@pytest.fixture(autouse=True)
def _isolate_files():
    """Tests historically read/write the real data/*.json (feedback, orders,
    menu popularity, memory). Snapshot + restore per test so the suite never
    leaves lasting pollution (popularity drift, warned flags, sesame bugs)
    while keeping legacy file-based assertions working."""
    import json as _json
    from pathlib import Path as _Path
    import backend.app as app_module

    root = _Path(__file__).resolve().parents[1] / "data"
    targets = ["feedback_log.json", "order_history.json", "memory.json", "menu_data.json"]
    snaps: dict[str, str | None] = {}
    for name in targets:
        p = root / name
        try:
            snaps[name] = p.read_text(encoding="utf-8") if p.exists() else None
        except Exception:
            snaps[name] = None
    # In-memory mirrors (store popularity, memory dict, ratings cache).
    try:
        mem_snapshot = _json.loads(_json.dumps(app_module.memory_store._data))
    except Exception:
        mem_snapshot = None
    try:
        pop_snapshot = {i.id: i.popularity_score for i in app_module.store.all()}
    except Exception:
        pop_snapshot = None
    app_module._ratings_cache.update({"key": None, "map": {}})
    yield
    for name, content in snaps.items():
        p = root / name
        try:
            if content is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_text(content, encoding="utf-8")
        except Exception:
            pass
    try:
        if mem_snapshot is not None:
            app_module.memory_store._data.clear()
            app_module.memory_store._data.update(mem_snapshot)
            app_module.memory_store._save_local()
    except Exception:
        pass
    try:
        if pop_snapshot is not None:
            for iid, pop in pop_snapshot.items():
                it = app_module.store.get(iid)
                if it is not None:
                    it.popularity_score = pop
    except Exception:
        pass
    app_module._ratings_cache.update({"key": None, "map": {}})
