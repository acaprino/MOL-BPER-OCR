# Edge-Agent Async Capture & Page Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple extraction from the capture loop (parallel background pool), unify page identity in a single registry (9/9 real total), and make the stability gate tolerate single bad frames.

**Architecture:** Producer/consumer. `BPERCaptureWorker` only captures/routes/tracks stability and enqueues stable frames; `LocalExtractionClient` runs `ExtractionPipeline.extract_from_image()` on a daemon-thread pool sized by `PARALLEL_WORKERS` (same shared-pipeline pattern as `BatchRunner`, `extraction/cli.py:194,235`). A new `page_registry.py` maps both router vocabularies (LLM page names, ML "screen N" template stems) to one canonical `PageDef`. A new pure `StabilityTracker` replaces the wall-clock-only stability gate.

**Tech Stack:** Python 3.12/3.13, PyQt6, PIL, pytest (new dev dependency). New modules are stdlib-only (no Qt) for testability.

**Spec:** `docs/superpowers/specs/2026-08-17-edge-agent-async-capture-design.md`

## Global Constraints

- Commit authorship (hard rule from CLAUDE.md): commits are authored by the human developer only. NEVER add `Co-Authored-By:`, "Generated with", or any AI mention in commit messages.
- Language policy: English for code/identifiers/comments/commit messages; Italian for UI strings and operator log messages (match existing `tick.emit` style with «» and →).
- Full type annotations on every function (parameters and return type).
- Section markers `# ===...===` where the file already uses them; match surrounding style.
- Never commit API keys. `.env` stays gitignored.
- The edge-agent modules use bare imports (`import app_paths`, `from llm_router import ...`) resolved via the `edge-agent/` directory on `sys.path`; new modules follow the same convention.
- `openpyxl` MUST stay in `requirements.txt` (used by `edge-agent/ui/data_table_tab.py:383` Excel export), even though the worker's Excel logic is deleted.
- Python interpreter for tests: use `.venv\Scripts\python.exe` if `.venv/` exists (created by `run_edge_agent.bat`); otherwise `py -3.13` (fall back `py -3.12`) after `py -3.13 -m pip install -r requirements.txt`. Referred to below as `$PY`.

---

### Task 1: Test infrastructure + PageRegistry + prompts.json metadata

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`
- Create: `tests/test_page_registry.py`
- Create: `edge-agent/page_registry.py`
- Modify: `edge-agent/assets/templates/bper/prompts.json`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `PageDef(name: str, order: int, template: Optional[str], slug: str)` frozen dataclass; `PageRegistry.load(prompts_path: Path) -> PageRegistry` (raises `ValueError` on invalid/duplicate metadata); `PageRegistry.empty() -> PageRegistry` (permissive pass-through); `registry.resolve(label: Optional[str]) -> Optional[PageDef]` (case-insensitive on name OR template; `None` for catch-all/unknown/empty); `registry.acquirable(router_mode: str) -> List[PageDef]` (ordered by `order`; `"ml"` mode filters to pages with a template); `registry.names(router_mode: str = "llm") -> List[str]`; `slugify(name: str) -> str`; `registry.catchall_name: Optional[str]`; `registry.pages: List[PageDef]`. Tasks 5 and 6 import these.

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest>=8.0
```

- [ ] **Step 2: Install dev deps and verify pytest runs**

Run: `$PY -m pip install -r requirements-dev.txt` then `$PY -m pytest --version`
Expected: pytest version printed.

- [ ] **Step 3: Create `tests/conftest.py`**

The `edge-agent` directory has a dash, so it is not importable as a package; tests import its modules directly via `sys.path`.

```python
"""Shared test setup: make repo root and edge-agent/ importable."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EDGE_AGENT_DIR = REPO_ROOT / "edge-agent"

for _p in (str(REPO_ROOT), str(EDGE_AGENT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
```

- [ ] **Step 4: Add `order`/`template`/`catchall` metadata to `prompts.json`**

Edit `edge-agent/assets/templates/bper/prompts.json`. For each entry in `pages`, insert `"order"` and `"template"` keys right after `"name"` (keep `hints` and `fields` untouched). The mapping was verified against the 9 template PNGs (see spec table):

| name | insert |
|---|---|
| Risultato ricerca | `"order": 1, "template": "screen 1",` |
| Risultato ricerca - Colonne estese | `"order": 2, "template": "screen 2",` |
| Risultato ricerca - Tooltip mostrata | `"order": 3, "template": "screen 3",` |
| Elenco Soggetti | `"order": 4, "template": "screen 4",` |
| Gestione Fidi e Garanzie | `"order": 5, "template": "screen 5",` |
| Gestione Fidi e Garanzie - Tooltip Descrizione Fidi | `"order": 6, "template": "screen 6",` |
| Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 1) | `"order": 7, "template": "screen 7",` |
| Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 2) | `"order": 8, "template": "screen 8",` |
| Note da Richiesta | `"order": 9, "template": "screen 9",` |
| Altro / Non riconosciuto | `"catchall": true,` (no order, no template) |

Validate with: `$PY -c "import json; json.load(open('edge-agent/assets/templates/bper/prompts.json', encoding='utf-8')); print('ok')"`
Expected: `ok`. (The LLM router only reads `name`/`hints`, so the new keys are additive and backward compatible: `llm_router.py:110,127-130`.)

- [ ] **Step 5: Write the failing tests**

Create `tests/test_page_registry.py`:

```python
"""Tests for edge-agent/page_registry.py."""

import json
from pathlib import Path

import pytest

from page_registry import PageDef, PageRegistry, slugify

REAL_PROMPTS = (
    Path(__file__).resolve().parent.parent
    / "edge-agent" / "assets" / "templates" / "bper" / "prompts.json"
)


def _write_spec(tmp_path: Path, pages: list) -> Path:
    p = tmp_path / "prompts.json"
    p.write_text(json.dumps({"pages": pages}), encoding="utf-8")
    return p


def test_slugify_flattens_punctuation() -> None:
    assert (
        slugify("Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 1)")
        == "gestione_fidi_e_garanzie_tooltip_descrizione_garanzie_riga_1"
    )
    assert slugify("Note da Richiesta") == "note_da_richiesta"


def test_load_real_prompts_json() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    assert len(reg.pages) == 9
    assert reg.catchall_name == "Altro / Non riconosciuto"
    assert [p.order for p in reg.pages] == list(range(1, 10))
    assert reg.pages[0].name == "Risultato ricerca"
    assert reg.pages[8].name == "Note da Richiesta"


def test_resolve_template_and_name_case_insensitive() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    fidi_tooltip = "Gestione Fidi e Garanzie - Tooltip Descrizione Fidi"
    assert reg.resolve("screen 6").name == fidi_tooltip
    assert reg.resolve("Screen 6").name == fidi_tooltip
    assert reg.resolve(fidi_tooltip).template == "screen 6"
    assert reg.resolve("elenco soggetti").template == "screen 4"


def test_resolve_catchall_unknown_and_empty_return_none() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    assert reg.resolve("Altro / Non riconosciuto") is None
    assert reg.resolve("pagina inventata") is None
    assert reg.resolve(None) is None
    assert reg.resolve("") is None


def test_acquirable_ml_mode_counts_only_templated_pages(tmp_path: Path) -> None:
    spec = [
        {"name": "Pagina A", "order": 1, "template": "screen 1"},
        {"name": "Pagina B", "order": 2, "template": None},
        {"name": "Altro", "catchall": True},
    ]
    reg = PageRegistry.load(_write_spec(tmp_path, spec))
    assert [p.name for p in reg.acquirable("ml")] == ["Pagina A"]
    assert [p.name for p in reg.acquirable("llm")] == ["Pagina A", "Pagina B"]
    assert reg.names("hybrid") == ["Pagina A", "Pagina B"]


def test_real_prompts_ml_total_is_nine() -> None:
    reg = PageRegistry.load(REAL_PROMPTS)
    assert len(reg.acquirable("ml")) == 9


def test_duplicate_template_raises(tmp_path: Path) -> None:
    spec = [
        {"name": "A", "order": 1, "template": "screen 1"},
        {"name": "B", "order": 2, "template": "screen 1"},
    ]
    with pytest.raises(ValueError):
        PageRegistry.load(_write_spec(tmp_path, spec))


def test_missing_order_raises(tmp_path: Path) -> None:
    spec = [{"name": "A", "template": "screen 1"}]
    with pytest.raises(ValueError):
        PageRegistry.load(_write_spec(tmp_path, spec))


def test_empty_registry_is_permissive() -> None:
    reg = PageRegistry.empty()
    page = reg.resolve("screen 3")
    assert isinstance(page, PageDef)
    assert page.name == "screen 3"
    assert page.order == 0
    assert page.slug == "screen_3"
    assert reg.acquirable("ml") == []
    assert reg.resolve(None) is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `$PY -m pytest tests/test_page_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'page_registry'`.

- [ ] **Step 7: Implement `edge-agent/page_registry.py`**

```python
"""Single source of truth for BPER page identity: name, order, template, slug."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


def slugify(name: str) -> str:
    """Filesystem-safe key: 'Note da Richiesta' -> 'note_da_richiesta'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "pagina"


@dataclass(frozen=True)
class PageDef:
    """Canonical page definition (name doubles as display label and id)."""

    name: str
    order: int
    template: Optional[str]
    slug: str


class PageRegistry:
    """Loads prompts.json and resolves router labels (names or template stems)."""

    def __init__(self, pages: List[PageDef], catchall_name: Optional[str]) -> None:
        self.pages: List[PageDef] = sorted(pages, key=lambda p: p.order)
        self.catchall_name = catchall_name
        self._by_name: Dict[str, PageDef] = {p.name.lower(): p for p in self.pages}
        self._by_template: Dict[str, PageDef] = {
            p.template.lower(): p for p in self.pages if p.template
        }
        self._permissive: bool = False

    @classmethod
    def load(cls, prompts_path: Path) -> "PageRegistry":
        """Parse prompts.json; raises ValueError on missing/duplicate metadata."""
        spec = json.loads(Path(prompts_path).read_text(encoding="utf-8"))
        pages: List[PageDef] = []
        catchall: Optional[str] = None
        for entry in spec.get("pages", []):
            name = (entry.get("name") or "").strip()
            if not name:
                raise ValueError("prompts.json: page entry without 'name'")
            if entry.get("catchall"):
                catchall = name
                continue
            order = entry.get("order")
            if not isinstance(order, int) or order < 1:
                raise ValueError(f"prompts.json: missing/invalid 'order' for '{name}'")
            template = (entry.get("template") or "").strip() or None
            pages.append(PageDef(name=name, order=order, template=template, slug=slugify(name)))
        _ensure_unique([p.name.lower() for p in pages], "name")
        _ensure_unique([p.order for p in pages], "order")
        _ensure_unique([p.template.lower() for p in pages if p.template], "template")
        return cls(pages, catchall)

    @classmethod
    def empty(cls) -> "PageRegistry":
        """Permissive fallback when prompts.json is unavailable/broken."""
        registry = cls([], None)
        registry._permissive = True
        return registry

    def resolve(self, label: Optional[str]) -> Optional[PageDef]:
        """Router label (page name or template stem) -> PageDef; None if catch-all/unknown."""
        if not label:
            return None
        key = label.strip().lower()
        if self.catchall_name and key == self.catchall_name.lower():
            return None
        found = self._by_name.get(key) or self._by_template.get(key)
        if found is not None:
            return found
        if self._permissive:
            return PageDef(name=label.strip(), order=0, template=None, slug=slugify(label))
        return None

    def acquirable(self, router_mode: str) -> List[PageDef]:
        """Pages reachable in the given router mode, in capture order."""
        if (router_mode or "ml").lower() == "ml":
            return [p for p in self.pages if p.template]
        return list(self.pages)

    def names(self, router_mode: str = "llm") -> List[str]:
        """Canonical names of acquirable pages (for UI combos)."""
        return [p.name for p in self.acquirable(router_mode)]


def _ensure_unique(values: List, what: str) -> None:
    seen = set()
    for value in values:
        if value in seen:
            raise ValueError(f"prompts.json: duplicate {what}: {value!r}")
        seen.add(value)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_page_registry.py -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add requirements-dev.txt tests/conftest.py tests/test_page_registry.py "edge-agent/page_registry.py" "edge-agent/assets/templates/bper/prompts.json"
git commit -m "Add page registry mapping templates to canonical BPER pages"
```

---

### Task 2: StabilityTracker

**Files:**
- Create: `edge-agent/stability.py`
- Create: `tests/test_stability.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `StabilityConfig(min_matches: int = 2, min_seconds: float = 2.0, miss_tolerance: int = 1)` frozen dataclass; `StabilityTracker(config: Optional[StabilityConfig] = None)` with `observe(page: Optional[str], now: float) -> Optional[str]` (returns the page name when stable, else `None`), `reset() -> None`, attribute `candidate: Optional[str]`, attribute `config: StabilityConfig`. Task 5 imports these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stability.py`:

```python
"""Tests for edge-agent/stability.py (page stability state machine)."""

from stability import StabilityConfig, StabilityTracker

CFG = StabilityConfig(min_matches=2, min_seconds=2.0, miss_tolerance=1)


def test_capture_requires_matches_and_min_seconds() -> None:
    t = StabilityTracker(CFG)
    assert t.observe("s9", 0.0) is None
    assert t.observe("s9", 1.0) is None  # 2 matches but only 1.0s elapsed
    assert t.observe("s9", 2.1) == "s9"


def test_two_quick_matches_do_not_capture_mid_scroll() -> None:
    t = StabilityTracker(CFG)
    assert t.observe("s6", 0.0) is None
    assert t.observe("s6", 0.4) is None  # matches ok, elapsed < min_seconds


def test_single_miss_is_tolerated() -> None:
    # Regression for the 13:38:06 log: one unrecognized frame killed a valid candidate.
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s9", 1.0)
    assert t.observe(None, 1.5) is None
    assert t.candidate == "s9"
    assert t.observe("s9", 2.2) == "s9"


def test_two_consecutive_misses_reset() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe(None, 0.5)
    t.observe(None, 1.0)
    assert t.candidate is None


def test_single_different_page_blip_keeps_candidate() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s9", 1.0)
    assert t.observe("s2", 1.4) is None  # blip, tolerated as miss
    assert t.candidate == "s9"
    assert t.observe("s9", 2.1) == "s9"


def test_two_consecutive_new_page_observations_switch_candidate() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s9", 1.0)
    assert t.observe("s2", 1.5) is None
    assert t.observe("s2", 2.0) is None
    assert t.candidate == "s2"
    # first_seen anchored at the first s2 observation (1.5): 1.5 + 2.0 = 3.5
    assert t.observe("s2", 3.4) is None
    assert t.observe("s2", 3.6) == "s2"


def test_miss_overflow_adopts_pending_page() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.observe("s2", 0.5)   # miss 1, pending s2
    t.observe("s6", 1.0)   # miss 2 > tolerance: reset, adopt pending s6
    assert t.candidate == "s6"


def test_observe_none_without_candidate_is_noop() -> None:
    t = StabilityTracker(CFG)
    assert t.observe(None, 0.0) is None
    assert t.candidate is None


def test_reset_clears_state() -> None:
    t = StabilityTracker(CFG)
    t.observe("s9", 0.0)
    t.reset()
    assert t.candidate is None
    assert t.observe("s9", 5.0) is None  # fresh cycle after reset
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$PY -m pytest tests/test_stability.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stability'`.

- [ ] **Step 3: Implement `edge-agent/stability.py`**

```python
"""Pure page-stability state machine for BPER capture (no Qt)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StabilityConfig:
    """Thresholds for declaring a page stable."""

    min_matches: int = 2      # concordant observations required on the candidate
    min_seconds: float = 2.0  # minimum candidate presence (anti mid-scroll)
    miss_tolerance: int = 1   # consecutive discordant/null observations tolerated


class StabilityTracker:
    """Decides when a recognized page is stable enough to capture.

    observe() takes the resolved page name (or None when unrecognized) plus a
    timestamp and returns the page name once the candidate has both
    min_matches concordant observations and min_seconds of presence. Up to
    miss_tolerance discordant/null observations do not reset the candidate;
    two consecutive concordant observations of a different page switch the
    candidate immediately (anchored at the first of the two).
    """

    def __init__(self, config: Optional[StabilityConfig] = None) -> None:
        self.config = config or StabilityConfig()
        self.candidate: Optional[str] = None
        self._first_seen: float = 0.0
        self._matches: int = 0
        self._misses: int = 0
        self._pending: Optional[str] = None
        self._pending_since: float = 0.0

    def reset(self) -> None:
        self.candidate = None
        self._first_seen = 0.0
        self._matches = 0
        self._misses = 0
        self._pending = None
        self._pending_since = 0.0

    def observe(self, page: Optional[str], now: float) -> Optional[str]:
        if page is None:
            self._register_miss()
            return None
        if self.candidate is None:
            self._adopt(page, now)
            return None
        if page == self.candidate:
            self._matches += 1
            self._misses = 0
            self._pending = None
            if (
                self._matches >= self.config.min_matches
                and (now - self._first_seen) >= self.config.min_seconds
            ):
                return self.candidate
            return None
        if self._pending == page:
            # Second consecutive concordant observation of a new page: switch.
            first_seen = self._pending_since
            self.reset()
            self.candidate = page
            self._first_seen = first_seen
            self._matches = 2
            return None
        self._pending = page
        self._pending_since = now
        self._register_miss()
        return None

    def _adopt(self, page: str, now: float) -> None:
        self.reset()
        self.candidate = page
        self._first_seen = now
        self._matches = 1

    def _register_miss(self) -> None:
        if self.candidate is None:
            return
        self._misses += 1
        if self._misses > self.config.miss_tolerance:
            pending, pending_since = self._pending, self._pending_since
            self.reset()
            if pending is not None:
                self.candidate = pending
                self._first_seen = pending_since
                self._matches = 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_stability.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add "edge-agent/stability.py" tests/test_stability.py
git commit -m "Add stability tracker with miss tolerance and fast page switch"
```

---

### Task 3: DaemonThreadPool

**Files:**
- Create: `edge-agent/extraction_pool.py`
- Create: `tests/test_extraction_pool.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DaemonThreadPool(max_workers: int, name_prefix: str = "extract")` with `submit(fn: Callable[..., Any], *args: Any) -> bool` (False after stop), `pending() -> int`, `stop() -> None` (discards queued-not-started tasks; running tasks finish on their own; daemon threads never block interpreter exit). Task 4 imports this.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extraction_pool.py`:

```python
"""Tests for edge-agent/extraction_pool.py (daemon worker pool)."""

import threading
import time

from extraction_pool import DaemonThreadPool


def test_submitted_tasks_execute_with_args() -> None:
    pool = DaemonThreadPool(2)
    done = threading.Event()
    results = []
    pool.submit(lambda a, b: (results.append(a + b), done.set()), 1, 2)
    assert done.wait(2.0)
    assert results == [3]


def test_threads_are_daemon() -> None:
    pool = DaemonThreadPool(3)
    assert len(pool._threads) == 3
    assert all(t.daemon for t in pool._threads)


def test_exception_does_not_kill_worker() -> None:
    pool = DaemonThreadPool(1)
    done = threading.Event()

    def boom() -> None:
        raise RuntimeError("task failure")

    pool.submit(boom)
    pool.submit(done.set)
    assert done.wait(2.0)


def test_concurrency_is_bounded_by_max_workers() -> None:
    pool = DaemonThreadPool(2)
    gate = threading.Event()
    active = []
    peak = []
    lock = threading.Lock()

    def task() -> None:
        with lock:
            active.append(1)
            peak.append(len(active))
        gate.wait(2.0)
        with lock:
            active.pop()

    for _ in range(4):
        pool.submit(task)
    time.sleep(0.3)
    gate.set()
    time.sleep(0.3)
    assert max(peak) <= 2


def test_stop_discards_queued_tasks_and_rejects_new_ones() -> None:
    pool = DaemonThreadPool(1)
    gate = threading.Event()
    ran = []
    pool.submit(lambda: (ran.append("first"), gate.wait(2.0)))
    for i in range(5):
        pool.submit(lambda i=i: ran.append(f"queued-{i}"))
    time.sleep(0.2)          # let the first task start and hold the only worker
    pool.stop()              # queued tasks must be discarded
    gate.set()
    time.sleep(0.3)
    assert ran == ["first"]
    assert pool.submit(lambda: ran.append("late")) is False
    assert pool.pending() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$PY -m pytest tests/test_extraction_pool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'extraction_pool'`.

- [ ] **Step 3: Implement `edge-agent/extraction_pool.py`**

```python
"""Daemon-thread pool for background extraction jobs (no Qt)."""

from __future__ import annotations

import queue
import threading
import traceback
from typing import Any, Callable

_SENTINEL: Any = object()


class DaemonThreadPool:
    """Runs callables on N daemon threads.

    Daemon threads do not block interpreter exit: closing the window while
    extractions are in flight terminates the process immediately. This is why
    concurrent.futures.ThreadPoolExecutor is not used here (its non-daemon
    threads are joined at interpreter shutdown, keeping the process alive
    until in-flight LLM calls time out).
    """

    def __init__(self, max_workers: int, name_prefix: str = "extract") -> None:
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._stopped: bool = False
        self._threads = [
            threading.Thread(target=self._run, name=f"{name_prefix}-{i}", daemon=True)
            for i in range(max(1, int(max_workers)))
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, fn: Callable[..., Any], *args: Any) -> bool:
        """Enqueue a task; returns False if the pool has been stopped."""
        if self._stopped:
            return False
        self._queue.put((fn, args))
        return True

    def pending(self) -> int:
        """Approximate number of tasks not yet started."""
        return self._queue.qsize()

    def stop(self) -> None:
        """Discard queued tasks and unblock workers; running tasks finish alone."""
        self._stopped = True
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        for _ in self._threads:
            self._queue.put(_SENTINEL)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            fn, args = item
            try:
                fn(*args)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_extraction_pool.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add "edge-agent/extraction_pool.py" tests/test_extraction_pool.py
git commit -m "Add daemon thread pool for background extraction"
```

---

### Task 4: Async LocalExtractionClient

**Files:**
- Modify: `edge-agent/local_extraction_client.py`
- Create: `tests/test_local_extraction_client.py`

**Interfaces:**
- Consumes: `DaemonThreadPool` (Task 3).
- Produces: `LocalExtractionClient(parent: Optional[QObject] = None, pipeline: Optional[ExtractionPipeline] = None)`; existing signal `result_ready(str, dict)` unchanged; NEW signal `frame_queued(str, str)` emitted as `(job_id, page_type)` synchronously inside `ingest_frame()`; `ingest_frame(...)` signature unchanged but now enqueue-and-return; NEW `shutdown() -> None`; NEW `pending_extractions() -> int`. Tasks 5 and 6 rely on: `ingest_frame()` returning in milliseconds, `frame_queued`, `shutdown()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_local_extraction_client.py`:

```python
"""Async behavior tests for LocalExtractionClient with an injected fake pipeline."""

import os
import time

# Must be set before importing extraction.config (read at import time).
os.environ.setdefault("LLM_API_KEY", "test-key")

from PIL import Image
from PyQt6.QtCore import QCoreApplication

import local_extraction_client as lec


class FakePipeline:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict:
        time.sleep(0.2)  # simulate slow VLM work
        return {
            "screen_id": screen_id,
            "fields": {"ndg": {"value": "123", "confidence": 1.0}},
            "_status": "OK",
        }


class BrokenPipeline:
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict:
        raise RuntimeError("VLM down")


def _app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def _wait_for(condition, app: QCoreApplication, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while not condition() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_ingest_frame_returns_immediately_and_result_arrives_async() -> None:
    app = _app()
    client = lec.LocalExtractionClient(pipeline=FakePipeline())
    queued: list = []
    got: list = []
    client.frame_queued.connect(lambda job, page: queued.append((job, page)))
    client.result_ready.connect(lambda job, result: got.append((job, result)))

    img = Image.new("RGB", (10, 10))
    t0 = time.time()
    client.ingest_frame("job1", img, page_no=5, page_type="Gestione Fidi e Garanzie")
    assert time.time() - t0 < 0.15  # ben sotto i 0.2s del fake: non ha atteso l'estrazione
    assert queued == [("job1", "Gestione Fidi e Garanzie")]

    _wait_for(lambda: got, app)
    assert got and got[0][0] == "job1"
    result = got[0][1]
    assert result["_page_type"] == "Gestione Fidi e Garanzie"
    assert result["_page_no"] == 5
    assert result["screen_id"] == "Gestione Fidi e Garanzie"  # no .title() mangling
    assert client.get_results("job1")[0]["_status"] == "OK"
    client.shutdown()


def test_pipeline_error_produces_error_result() -> None:
    app = _app()
    client = lec.LocalExtractionClient(pipeline=BrokenPipeline())
    got: list = []
    client.result_ready.connect(lambda job, result: got.append(result))
    client.ingest_frame("job2", Image.new("RGB", (10, 10)), page_no=1, page_type="Elenco Soggetti")
    _wait_for(lambda: got, app)
    assert got[0]["_status"] == "ERROR"
    assert "VLM down" in got[0]["_error"]
    client.shutdown()


def test_shutdown_stops_accepting_work() -> None:
    _app()
    client = lec.LocalExtractionClient(pipeline=FakePipeline())
    client.shutdown()
    assert client.pending_extractions() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_local_extraction_client.py -v`
Expected: FAIL. `LocalExtractionClient.__init__` rejects the `pipeline` kwarg (TypeError) and `frame_queued` does not exist.

- [ ] **Step 3: Modify `edge-agent/local_extraction_client.py`**

Changes against the current file:

1. Add import after the existing `from extraction...` block and extend the config import:

```python
from extraction.llm_factory import create_chat_model
from extraction.pipeline import ExtractionPipeline
from extraction.config import LLM_PROVIDER, LLM_MODEL, LLM_MODEL_ANCHOR, PARALLEL_WORKERS
from extraction.normalization import escape_csv_formula

from extraction_pool import DaemonThreadPool
```

2. Replace the signal declaration block and `__init__` (current lines 46-61):

```python
    result_ready = QtCore.pyqtSignal(str, dict)   # (job_id, result)
    frame_queued = QtCore.pyqtSignal(str, str)    # (job_id, page_type)

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
        pipeline: Optional[ExtractionPipeline] = None,
    ) -> None:
        super().__init__(parent)

        if pipeline is None:
            main_model = create_chat_model(LLM_PROVIDER, model=LLM_MODEL)
            anchor_model = create_chat_model(LLM_PROVIDER, model=LLM_MODEL_ANCHOR)
            pipeline = ExtractionPipeline(
                main_model=main_model,
                anchor_model=anchor_model,
                main_model_name=LLM_MODEL,
                anchor_model_name=LLM_MODEL_ANCHOR,
            )
        self._pipeline = pipeline

        # Extraction runs on a daemon pool; the shared-pipeline pattern matches
        # BatchRunner (extraction/cli.py): one pipeline, N worker threads.
        self._pool = DaemonThreadPool(max_workers=max(1, int(PARALLEL_WORKERS)))

        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
```

3. Replace `ingest_frame()` (current lines 69-110) with enqueue-and-return plus the worker method:

```python
    def ingest_frame(
        self,
        job_id: str,
        img: Image.Image,
        page_no: int = 0,
        page_type: str = "",
        confidence: float = 0.0,
        fields_json: str = "{}",
    ) -> None:
        """Enqueue a frame for background extraction and return immediately.

        Called from the capture QThread; extraction runs on the internal
        daemon pool so the capture loop is never blocked.
        """
        self.frame_queued.emit(job_id, page_type)
        self._pool.submit(
            self._process_frame, job_id, img, page_no, page_type, confidence, fields_json
        )

    def _process_frame(
        self,
        job_id: str,
        img: Image.Image,
        page_no: int,
        page_type: str,
        confidence: float,
        fields_json: str,
    ) -> None:
        """Pool worker: run the pipeline and publish the result."""
        screen_id = page_type if page_type else f"pagina {page_no}"

        try:
            # extract_from_image (not extract_from_screen): the Edge Agent has
            # already pre-processed the image, normalize_image would be redundant.
            result = self._pipeline.extract_from_image(img, screen_id)
        except Exception as e:  # noqa: BLE001
            result = {
                "screen_id": screen_id,
                "fields": {},
                "_status": "ERROR",
                "_error": str(e),
            }

        result["_page_type"] = page_type
        result["_page_no"] = page_no
        result["_page_confidence"] = confidence

        with self._lock:
            self._results.setdefault(job_id, []).append(result)

        # Qt signal is thread-safe across thread boundaries
        self.result_ready.emit(job_id, dict(result))
```

Note: the old `friendly = page_type.replace('_', ' ').title()` is deliberately gone; `page_type` is now the canonical display name and `.title()` would mangle it ("Gestione Fidi E Garanzie...").

4. Add at the end of the APIClient-compatible section (after `requeue_job`):

```python
    def pending_extractions(self) -> int:
        """Number of queued frames not yet being processed."""
        return self._pool.pending()

    def shutdown(self) -> None:
        """Stop the pool: queued frames are discarded; running tasks cannot
        block process exit (daemon threads)."""
        self._pool.stop()
```

- [ ] **Step 4: Run the new test and the full suite**

Run: `$PY -m pytest tests -v`
Expected: all PASS (registry, stability, pool, client).

- [ ] **Step 5: Commit**

```bash
git add "edge-agent/local_extraction_client.py" tests/test_local_extraction_client.py
git commit -m "Run extraction on a background daemon pool in LocalExtractionClient"
```

---

### Task 5: BPERCaptureWorker rewrite

**Files:**
- Modify: `edge-agent/workers/capture/bper_capture_worker.py`

**Interfaces:**
- Consumes: `PageRegistry`, `PageDef`, `slugify` (Task 1); `StabilityTracker` (Task 2); async `ingest_frame()` (Task 4).
- Produces: same public surface used by `CaptureTab`: constructor `(config, job_id_getter, api_client, parent)`, `force_capture(page_name: str)` slot, `stop()`. NEW attribute `registry: PageRegistry` (Task 6's combo may use it). The `page_sequence` attribute is REMOVED (Task 6 removes its only external reference, a safe `getattr(..., [])` fallback in `capture_tab.py:238`).

No new unit tests: the new decision logic lives in the already-tested registry and tracker; the worker becomes glue around Qt/mss which the suite cannot drive. Verification is compile + full suite + the Task 7 smoke test.

- [ ] **Step 1: Rewrite imports and module constants**

Replace current lines 1-33 with:

```python
"""Worker di cattura specifico per il flusso BPER."""

from __future__ import annotations

import json
import time
import uuid
from typing import Optional, Set, Tuple, List, Dict, Any

import imagehash
from PIL import Image
from PyQt6 import QtCore
from llm_router import PageRouter, MLPageRouter, LLMPageRouter, RouterResult  # type: ignore

try:
    from page_classifier import BPERPagePrototypeClassifier  # type: ignore
except Exception:  # noqa: BLE001
    BPERPagePrototypeClassifier = None  # type: ignore

from .base_capture_worker import BaseCaptureWorker
from image_ops import preprocess_for_ocr
import app_paths
from page_registry import PageDef, PageRegistry
from stability import StabilityTracker
```

Deleted: `io`, `re`, `Path`, `to_png8`, `to_webp_lossless` imports; `PAGE_ORDER_FALLBACK`; `_SKIP_PAGE_TYPES` (the registry resolves the catch-all to `None`).

- [ ] **Step 2: Rewrite `__init__` state**

Replace the current stability/sequence state (lines 49-53 class constants and 65-108 instance state). Keep `DEDUP_HASH_THRESHOLD = 3`; delete `STABILITY_SECONDS` (now `StabilityConfig.min_seconds`). New `__init__` body after `self.api_client = api_client`:

```python
        # Stato dedup
        self._last_frame_hash: Optional[imagehash.ImageHash] = None

        # Stabilità pagina (macchina a stati pura, vedi stability.py)
        self._tracker = StabilityTracker()

        # Pagine già acquisite in questo job (nomi canonici dal registro)
        self.captured_page_types: Set[str] = set()

        # Registro pagine: caricato in run() nel thread worker
        self.registry: PageRegistry = PageRegistry.empty()
        self._acquirable_names: List[str] = []

        # Routing (ML o LLM): l'inizializzazione vera avviene in run(), nel
        # thread worker — il caricamento DINOv2 non deve congelare la UI.
        self.classifier: Optional[Any] = None
        self.router: Optional[PageRouter] = None
        self._router_ready: bool = False

        # Throttling routing su frame duplicati: ultimo tentativo eseguito
        self._last_route_attempt_ts: Optional[float] = None

        # Contatore errori di cattura consecutivi (auto-stop oltre soglia)
        self._consecutive_capture_errors: int = 0
        self._MAX_CONSECUTIVE_CAPTURE_ERRORS: int = 5

        # mss context singleton (creato una volta nel QThread, non in __init__)
        self._mss_ctx: Optional[Any] = None

        # Anti-spam log: ultima guida emessa e ultima pagina "già acquisita"
        self._last_guidance_page: Optional[str] = None
        self._last_already_captured: Optional[str] = None

        # Ultimo errore router già loggato (per non ripeterlo a ogni frame)
        self._last_router_error: Optional[str] = None
```

Also fix the class docstring bullet list: replace "logica di stabilità temporale" with "logica di stabilità (conteggio + permanenza, tollera 1 frame anomalo)" and DELETE the "stop automatico quando tutte le pagine previste sono acquisite" line (never implemented).

- [ ] **Step 3: Replace `run()` and the sequence loader**

`_init_router()` stays as-is. Replace `run()` (lines 205-212) and DELETE `_load_page_sequence()` (252-385), `_normalize_page_label()` (387-450), `_friendly_name()` (225-238), `_next_pending_page()` (240-249):

```python
    def run(self) -> None:
        """Inizializza router e registro pagine nel thread worker, poi entra nel loop."""
        if not self._router_ready:
            self.tick.emit("[Worker] Inizializzazione riconoscimento in corso...")
            self._init_router()
            self._load_registry()
            self._router_ready = True
        super().run()

    # ------------------------------------------------------------------ page registry

    def _load_registry(self) -> None:
        """Carica il registro pagine da prompts.json e annuncia la sequenza."""
        try:
            self.registry = PageRegistry.load(app_paths.templates_dir() / "prompts.json")
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
            self.registry = PageRegistry.empty()
            self.tick.emit("[BPER] prompts.json non valido: acquisizione libera senza sequenza.")

        mode = (self.config.router_mode or "ml").lower()
        pages = self.registry.acquirable(mode)
        self._acquirable_names = [p.name for p in pages]

        if pages:
            self.tick.emit(f"─── Schermate da acquisire: {len(pages)} ───")
            for i, page in enumerate(pages, 1):
                self.tick.emit(f"  {i:2}. {page.name}")
            self.tick.emit("──────────────────────────────────────")
            first = self._next_pending_page()
            if first:
                self.tick.emit(f"→ Prima schermata da aprire nel sistema BPER: «{first}»")
        else:
            self.tick.emit("[BPER] Attenzione: nessuna pagina definita; funzionamento libero.")

    def _next_pending_page(self) -> Optional[str]:
        """Nome canonico della prossima pagina non ancora acquisita."""
        for name in self._acquirable_names:
            if name not in self.captured_page_types:
                return name
        return None
```

- [ ] **Step 4: Replace `_capture_once()`**

Replace the whole method (current lines 454-547):

```python
    def _capture_once(self) -> None:
        """
        Loop di cattura per BPER:

            - legge job_id
            - cattura screenshot
            - dedup via pHash (con throttling del routing sui duplicati)
            - riconosce pagina via router e la risolve nel registro
            - applica la macchina a stati di stabilità
            - accoda il frame stabile per l'estrazione in background
        """
        job_id = self.job_id_getter()
        if not job_id:
            return

        raw = self._grab_raw()
        if raw is None:
            return

        is_dup = self._is_duplicate_frame(raw)
        if is_dup:
            now_ts = time.time()
            min_interval = float(getattr(self.config, "route_retry_seconds", 1.0) or 1.0)
            if self._last_route_attempt_ts is not None and (now_ts - self._last_route_attempt_ts) < min_interval:
                return

        self._last_route_attempt_ts = time.time()
        img = self._preprocess(raw)
        label, score, fields = self._detect_page(img)
        page = self.registry.resolve(label)

        # Pagina già acquisita: non riacquisire (con l'estrazione asincrona una
        # ri-acquisizione costerebbe una seconda estrazione completa).
        if page is not None and page.name in self.captured_page_types:
            if self._last_already_captured != page.name:
                nxt = self._next_pending_page()
                hint = f" → apri nel sistema BPER: «{nxt}»" if nxt else ""
                self.tick.emit(f"ℹ️ «{page.name}» già acquisita{hint}")
                self._last_already_captured = page.name
            self._tracker.reset()
            return

        prev_candidate = self._tracker.candidate
        ready = self._tracker.observe(page.name if page else None, time.time())

        if page is not None and self._tracker.candidate == page.name and prev_candidate != page.name:
            self.tick.emit(
                f"⏳ Rilevata «{page.name}» — mantieni aperta la schermata "
                f"({self._tracker.config.min_seconds:.0f}s richiesti per la stabilità)"
            )

        if ready is None or page is None:
            return

        n_captured = len(self.captured_page_types) + 1
        n_total: Any = len(self._acquirable_names) or "?"
        self._upload_page(job_id, img, page, score, fields)
        self.captured_page_types.add(page.name)
        self._tracker.reset()
        self._last_already_captured = None

        next_page = self._next_pending_page()
        if next_page:
            self.tick.emit(
                f"✅ «{page.name}» acquisita [{n_captured}/{n_total}] "
                f"→ apri nel sistema BPER: «{next_page}»"
            )
            self._last_guidance_page = next_page
        else:
            self.tick.emit(
                f"✅ «{page.name}» acquisita [{n_captured}/{n_total}] — tutte le schermate completate!"
            )
```

Also DELETE `_maybe_upload_dataset()` (lines 730-732) and `_reset_stability()` (736-739); their callers are gone.

- [ ] **Step 5: Update `_detect_page()` display names**

In `_detect_page()` keep the structure but resolve labels for logging. Replace the two `_friendly_name` usages:

Match branch (current lines 654-658):

```python
            if res.page_type:
                resolved = self.registry.resolve(res.page_type)
                shown = resolved.name if resolved else res.page_type
                self.tick.emit(
                    f"[Router] Riconosciuta: «{shown}» (score={res.confidence:.3f})"
                )
                return res.page_type, float(res.confidence), dict(res.fields or {})
```

ML fallback branch (current lines 681-685) and the final ML-only branch (689-692): same pattern, `shown = (self.registry.resolve(label) or ...)`:

```python
                if self.classifier is not None and isinstance(self.router, LLMPageRouter):
                    label, score = self.classifier.classify(img)
                    if label is not None:
                        resolved = self.registry.resolve(label)
                        shown = resolved.name if resolved else label
                        self.tick.emit(f"[ML] Riconosciuta via fallback: «{shown}» (score={score:.3f})")
                        return label, float(score or 0.0), {}
                return None, 0.0, {}

        # Fallback: solo ML classifier
        label, score = self.classifier.classify(img) if self.classifier else (None, 0.0)
        if label is not None:
            resolved = self.registry.resolve(label)
            shown = resolved.name if resolved else label
            self.tick.emit(f"[ML] Riconosciuta: «{shown}» (score={score:.3f})")
        return label, float(score or 0.0), {}
```

The unrecognized-branch guidance block (lines 666-678) stays; `_next_pending_page()` now returns canonical names.

- [ ] **Step 6: Replace `_upload_page()` and `force_capture()`**

```python
    # ------------------------------------------------------------------ upload

    def _upload_page(
        self,
        job_id: str,
        img: Image.Image,
        page: PageDef,
        confidence: float = 0.0,
        fields: Optional[dict] = None,
    ) -> None:
        """Accoda lo screenshot di una pagina riconosciuta per l'estrazione."""
        if page.order > 0:
            filename = f"{page.order:02d}-{page.slug}.png"
        else:
            filename = f"{page.slug}-{uuid.uuid4().hex}.png"

        if self.api_client and hasattr(self.api_client, "ingest_frame"):
            try:
                self.api_client.ingest_frame(
                    job_id=job_id,
                    img=img,
                    page_no=page.order,
                    page_type=page.name,
                    confidence=confidence,
                    fields_json=json.dumps(fields or {}),
                )
                self.tick.emit(f"📤 In coda per estrazione: {filename}")
                return
            except Exception as exc:  # noqa: BLE001
                self.on_error(exc)
                return

        self.tick.emit(f"[ERRORE] Client locale non configurato correttamente per {filename}")
```

```python
    # ------------------------------------------------------------------ forza scatto manuale
    @QtCore.pyqtSlot(str)
    def force_capture(self, page_name: str) -> None:
        """
        Forza lo scatto e l'accodamento dell'immagine corrente come pagina indicata.

        Il nome arriva dal combo della UI (nomi canonici del registro); accetta
        anche uno stem template ("screen 5"). Non richiede stabilità né match
        del router. Aggiunge la pagina a `captured_page_types`.
        """
        try:
            if not self._router_ready:
                self.tick.emit("[BPER] Forza scatto: inizializzazione in corso, riprova tra qualche secondo.")
                return

            job_id = self.job_id_getter()
            if not job_id:
                self.tick.emit("[BPER] Forza scatto: nessun job attivo.")
                return

            page = self.registry.resolve(page_name)
            if page is None:
                self.tick.emit(f"[BPER] Forza scatto: pagina sconosciuta: '{page_name}'.")
                return

            img = self._capture_screenshot()
            if img is None:
                self.tick.emit("[BPER] Forza scatto: nessuno screenshot disponibile.")
                return

            self._upload_page(job_id, img, page, 0.0, {})
            self.captured_page_types.add(page.name)
            self._tracker.reset()
            self._last_already_captured = None
            self.tick.emit(f"[BPER] Forza scatto completato per «{page.name}».")
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
```

- [ ] **Step 7: Verify compile + suite + no dangling references**

Run:
- `$PY -m py_compile "edge-agent/workers/capture/bper_capture_worker.py"`
- `$PY -m pytest tests -v`
- `git grep -n "_load_page_sequence\|_normalize_page_label\|_friendly_name\|_maybe_upload_dataset\|_reset_stability\|PAGE_ORDER_FALLBACK\|STABILITY_SECONDS\|_valid_page_keys\|_available_page_keys\|page_order" -- "edge-agent/workers"`

Expected: compile OK; suite green; grep finds no hits in `edge-agent/workers`. (`page_sequence` is still referenced by `capture_tab.py:238` via a safe `getattr` fallback; Task 6 removes it.)

- [ ] **Step 8: Commit**

```bash
git add "edge-agent/workers/capture/bper_capture_worker.py"
git commit -m "Drive BPER capture from page registry and stability tracker"
```

---

### Task 6: UI wiring + config cleanup

**Files:**
- Modify: `edge-agent/ui/capture_tab.py`
- Modify: `edge-agent/ui/main_window.py`
- Modify: `edge-agent/ui/extraction_results_tab.py`
- Modify: `edge-agent/config.py`

**Interfaces:**
- Consumes: `frame_queued` signal + `shutdown()` (Task 4); `PageRegistry.names()` (Task 1); worker without `page_sequence` (Task 5).
- Produces: no new interfaces; user-visible behavior only.

- [ ] **Step 1: `capture_tab.py` — connect signals once, add queued/extracted counters**

1. In `__init__` (after `self._n_results: int = 0`, line 65) add and connect (the client outlives every job, so connections are made once here, not per start):

```python
        self._n_queued: int = 0

        self._init_ui()

        # Connessioni uniche al client (vive quanto la finestra): i contatori
        # filtrano per job_id, quindi nessun connect/disconnect per sessione.
        try:
            self.api_client.result_ready.connect(self._on_result_ready_count)
            self.api_client.frame_queued.connect(self._on_frame_queued)
        except Exception:
            pass
```

(`self._init_ui()` already exists at line 67; the try/connect block goes after it so `job_label` exists.)

2. In `_on_start_capture()` remove the connect block (lines 209-213) and update the reset (lines 207-208):

```python
        self._n_results = 0
        self._n_queued = 0
        self._update_session_label()
```

3. Replace `_on_result_ready_count()` (lines 382-385) with:

```python
    def _update_session_label(self) -> None:
        self.job_label.setText(
            f"Sessione attiva  |  Acquisite: {self._n_queued}  |  Estratte: {self._n_results}"
        )

    def _on_frame_queued(self, job_id: str, _page_type: str) -> None:
        if job_id == self.job_id:
            self._n_queued += 1
            self._update_session_label()

    def _on_result_ready_count(self, job_id: str, result: dict) -> None:
        if job_id == self.job_id:
            self._n_results += 1
            self._update_session_label()
            page = str(result.get("_page_type") or result.get("screen_id") or "?")
            status = str(result.get("_status") or "OK")
            self._log(f"✅ Estrazione completata: «{page}» (stato: {status})")
```

4. Replace `_on_stop_capture()` (lines 300-332): drop the `terminate()` branch and the disconnect; report the still-draining queue:

```python
    def _on_stop_capture(self) -> None:
        if self.worker is None:
            return

        self._log("Richiesta arresto cattura...")
        try:
            self.worker.stop()
            if not self.worker.wait(5000):
                # Il loop di cattura non esegue più lavoro lungo: se accade,
                # è un bug da indagare, non da mascherare con terminate().
                self._log("[WARN] Worker di cattura ancora attivo dopo 5s.")
        except Exception as exc:  # noqa: BLE001
            self._log(f"[ERROR] Errore in stop_capture: {exc}")
        finally:
            self.worker = None
            in_flight = self._n_queued - self._n_results
            if in_flight > 0:
                self._log(f"Cattura arrestata. Estrazioni ancora in corso: {in_flight} (proseguono in background).")
            else:
                self._log("Cattura arrestata.")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.force_page_combo.setEnabled(False)
            self.force_capture_button.setEnabled(False)
            # Nasconde overlay se presente
            try:
                if self._overlay is not None:
                    self._overlay.hide()
                    self._overlay.deleteLater()
            finally:
                self._overlay = None
```

5. Replace `_load_bper_page_names()` (lines 155-169) and its call site (lines 233-240):

```python
    @staticmethod
    def _load_bper_page_names(router_mode: str) -> list:
        """Nomi pagina acquisibili dal registro (per il combo 'Acquisisci ora')."""
        try:
            import app_paths
            from page_registry import PageRegistry
            registry = PageRegistry.load(app_paths.templates_dir() / "prompts.json")
            return registry.names(router_mode)
        except Exception:
            return []
```

Call site becomes (no worker fallback, `page_sequence` no longer exists):

```python
            self._log("Avvio cattura in modalità BPER.")
            # Popola combo pagine dal registro (prompts.json, source of truth)
            pages = self._load_bper_page_names(self.config.router_mode)
```

6. Delete the now-unused `_SKIP_PAGE_TYPES_UI` constant (lines 33-34).

- [ ] **Step 2: `main_window.py` — shut the pool down on close**

Replace `closeEvent` (lines 95-101):

```python
    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            if hasattr(self.capture_tab, "stop_capture"):
                self.capture_tab.stop_capture()
        except Exception:
            pass
        try:
            self.extraction_client.shutdown()
        except Exception:
            pass
        super().closeEvent(event)
```

- [ ] **Step 3: `extraction_results_tab.py` — drop the name-mangling helper**

Delete `_friendly_name()` (lines 34-40) and change its two call sites to use the raw canonical name:

- line 163-164: `friendly = str(r.get("_page_type") or r.get("screen_id") or "?")` (rename variable usage accordingly)
- line 205: `page_type = str(result.get("_page_type") or "")`

- [ ] **Step 4: `config.py` — remove dead required-pages options**

Delete: defaults at lines 50-52 (`DEFAULT_REQUIRED_PAGES_ONLY`, `DEFAULT_REQUIRED_PAGES_CSV` and their comment), instance attrs at lines 82-84, INI parsing at lines 214-217, and the two `save()` keys at lines 355-356. (Their only consumer was the deleted `_load_page_sequence()`; the shipped `config.ini` does not contain these keys.)

- [ ] **Step 5: Verify**

Run:
- `$PY -m py_compile "edge-agent/ui/capture_tab.py" "edge-agent/ui/main_window.py" "edge-agent/ui/extraction_results_tab.py" "edge-agent/config.py"`
- `$PY -m pytest tests -v`
- `git grep -n "required_pages\|_SKIP_PAGE_TYPES_UI\|page_sequence\|_friendly_name" -- "edge-agent"`

Expected: compile OK; suite green; grep returns no hits.

- [ ] **Step 6: Commit**

```bash
git add "edge-agent/ui/capture_tab.py" "edge-agent/ui/main_window.py" "edge-agent/ui/extraction_results_tab.py" "edge-agent/config.py"
git commit -m "Update capture UI for async extraction and drop required-pages config"
```

---

### Task 7: Documentation + smoke test

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: updated project documentation; a user-validated smoke run.

- [ ] **Step 1: Update CLAUDE.md**

Precise edits (keep surrounding text):

1. **Edge-agent capture flow section:** in the ASCII diagram replace the line `└── _upload_page() → LocalExtractionClient.ingest_frame()` and the note about synchronous calls: `ingest_frame()` now enqueues on a daemon pool (`PARALLEL_WORKERS` threads, shared pipeline) and returns immediately; results still flow via `result_ready`. Replace `Stability check (STABILITY_SECONDS = 2.0 steady-state)` with `Stability check (StabilityTracker: >= 2 concordant matches AND >= 2.0s presence, 1 miss tolerated)`.
2. **Detection hook bullet:** change "(synchronously, in the capture QThread)" to "(asynchronously: the frame is queued and extracted on `LocalExtractionClient`'s internal daemon pool)".
3. **`edge-agent/` package table:** add rows for `page_registry.py` ("`PageDef`/`PageRegistry`: canonical page identity, template mapping, capture order from `prompts.json`"), `stability.py` ("`StabilityTracker`: count+time stability gate with miss tolerance"), `extraction_pool.py` ("`DaemonThreadPool`: background extraction workers; daemon so window close kills the process").
4. **Dependencies section:** change the `openpyxl` comment from `(edge-agent/workers/capture/bper_capture_worker.py)` to `(edge-agent/ui/data_table_tab.py Excel export)`.
5. **Testing & Validation:** add as new item 1: "**Unit tests:** `python -m pytest tests -v` (page registry, stability tracker, extraction pool, async client; requires `pip install -r requirements-dev.txt`)." Renumber the rest.
6. **Missing Infrastructure:** update the "Tests" bullet: unit tests now exist for the edge-agent pure logic under `tests/`; the extraction package itself is still untested.
7. **Architectural constraint 12** stays valid; append to it: "capture and extraction are decoupled: `ingest_frame()` queues and returns, extraction runs on `PARALLEL_WORKERS` daemon threads sharing one pipeline (same pattern as `BatchRunner`)."

- [ ] **Step 2: Full suite one last time**

Run: `$PY -m pytest tests -v`
Expected: all PASS.

- [ ] **Step 3: Smoke test from source (manual gate with the user)**

Run: `python edge-agent/edge_agent.py` (or `run_edge_agent.bat`) with `router = ml`, then have the user replay their session: start capture, scroll through the 9 screenshots in `mnt/data` holding each ~2-3s.

Checklist to verify in the log:
- Startup lists `─── Schermate da acquisire: 9 ───` with the real BPER names (not 19, no "Screen N" entries).
- Each stable page logs `📤 In coda per estrazione: NN-<slug>.png` immediately, and `✅ «name» acquisita [n/9] → apri ...` with the NEXT recognizable page.
- Scrolling continues while extractions run: `[Router] Riconosciuta` lines keep appearing between `✅ Estrazione completata` lines (no 30s blind window).
- Session label counts `Acquisite: X | Estratte: Y` with Y catching up to X.
- Sitting on an already-captured page logs `ℹ️ ... già acquisita` once, with no duplicate extraction.
- Stop is instant; queued extractions keep landing in Risultati / Dati Estratti afterwards.
- Closing the window mid-extraction terminates the process (check no lingering `python.exe`).

- [ ] **Step 4: Commit docs**

```bash
git add CLAUDE.md
git commit -m "Document async edge-agent capture flow and test suite"
```

- [ ] **Step 5: Note for the packaged exe**

The user's session ran `dist/EdgeAgent`. After the smoke test passes, rebuild with `build_exe.bat` (it xcopies `edge-agent/assets`, picking up the new `prompts.json`). Do not commit `dist/`.

---

## Self-Review Notes

- Spec coverage: blind window → Tasks 3-5; stability loss → Task 2+5; page identity/19 → Tasks 1+5; double-capture guard → Task 5 Step 4; terminate() removal → Task 6; shutdown-on-close → Tasks 3+6; counters → Task 6; docs → Task 7.
- Between Task 4 and Task 5 the worker's old log line "✅ Elaborazione locale completata" is momentarily inaccurate (extraction is already async); accepted, each commit still runs, wording fixed in Task 5.
- `capture_tab.py:238` references `worker.page_sequence` until Task 6, but via `getattr(..., []) `, so Task 5's removal cannot break it.
- Type/name consistency verified: `PageDef.order`/`name`/`slug` (Tasks 1, 5), `StabilityTracker.observe/reset/candidate/config` (Tasks 2, 5), `DaemonThreadPool.submit/pending/stop` (Tasks 3, 4), `frame_queued`/`shutdown`/`pending_extractions` (Tasks 4, 6).
