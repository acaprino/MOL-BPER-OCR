"""Behavioral checks for the resumable OCR cache runner and its selection metrics."""

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Callable

import pytest

from training.ocr_runner import Screen, load_assigned_screens, merge_runs, ocr_selection_metrics, report, run_ocr

PROVENANCE = {"models": {"Det": {"file": "det.onnx", "sha256": "d1"}}, "versions": {"rapidocr": "test"}}


def _screens(tmp_path: Path, names: tuple[str, ...] = ("p1__a", "p1__b", "p1__c")) -> list[Screen]:
    screens = []
    for name in names:
        path = tmp_path / "images" / f"{name}.png"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(name.encode("utf-8"))
        screens.append(Screen(name, path, hashlib.sha256(name.encode("utf-8")).hexdigest()))
    return screens


class FakeEngine:
    """Stands in for RapidOCR, the external engine absent from the test environment."""

    def __init__(self, fail_on: tuple[str, ...] = (), interrupt_after: int | None = None,
                 provenance: dict[str, Any] | None = None) -> None:
        self.fail_on = fail_on
        self.interrupt_after = interrupt_after
        self.provenance = provenance or PROVENANCE
        self.reads: list[str] = []
        self.threads: dict[str, int] | None = None

    def factory(self, params: dict[str, str], threads: dict[str, int]) -> tuple[Callable[[Path], list[list[Any]]], dict[str, Any]]:
        self.threads = threads
        return self.read, self.provenance

    def read(self, image_path: Path) -> list[list[Any]]:
        if self.interrupt_after is not None and len(self.reads) == self.interrupt_after:
            raise KeyboardInterrupt
        self.reads.append(image_path.stem)
        if image_path.stem in self.fail_on:
            raise RuntimeError(f"engine failed on {image_path.stem}")
        return [[f"{image_path.stem} call {len(self.reads)}", 0.9, [[0, 0], [9, 0], [9, 9], [0, 9]]]]


def _run(out: Path, screens: list[Screen], engine: FakeEngine, config: str = "A0") -> dict[str, Any]:
    return run_ocr(config, "pc4", screens, out, engine_factory=engine.factory)


def _cache(out: Path) -> dict[str, Any]:
    return json.loads((out / "cache.json").read_text(encoding="utf-8"))


def _manifest(out: Path) -> dict[str, Any]:
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def test_complete_run_writes_a_cache_entry_for_every_screen(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    _run(tmp_path / "run", screens, FakeEngine())
    cache = _cache(tmp_path / "run")
    assert list(cache) == ["p1__a", "p1__b", "p1__c"]
    assert all(isinstance(cache[s]["seconds"], float) and len(cache[s]["items"]) == 1 for s in cache)


def test_complete_run_is_marked_complete(tmp_path: Path) -> None:
    _run(tmp_path / "run", _screens(tmp_path), FakeEngine())
    assert _manifest(tmp_path / "run")["status"] == "complete"


def test_complete_manifest_binds_the_cache_digest(tmp_path: Path) -> None:
    _run(tmp_path / "run", _screens(tmp_path), FakeEngine())
    digest = hashlib.sha256((tmp_path / "run" / "cache.json").read_bytes()).hexdigest()
    assert _manifest(tmp_path / "run")["cache_sha256"] == digest


def test_warm_up_result_is_not_stored(tmp_path: Path) -> None:
    engine = FakeEngine()
    _run(tmp_path / "run", _screens(tmp_path), engine)
    assert engine.reads == ["p1__a", "p1__a", "p1__b", "p1__c"]
    assert _cache(tmp_path / "run")["p1__a"]["items"][0][0] == "p1__a call 2"


def test_interrupted_run_leaves_no_cache(tmp_path: Path) -> None:
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "run", _screens(tmp_path), FakeEngine(interrupt_after=3))
    assert not (tmp_path / "run" / "cache.json").exists()
    assert _manifest(tmp_path / "run")["status"] == "partial"


def test_resumed_run_reads_only_the_screens_still_pending(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "run", screens, FakeEngine(interrupt_after=3))
    engine = FakeEngine()
    _run(tmp_path / "run", screens, engine)
    assert engine.reads == ["p1__a", "p1__c"]
    assert list(_cache(tmp_path / "run")) == ["p1__a", "p1__b", "p1__c"]


def test_failed_screen_does_not_stop_the_other_screens(tmp_path: Path) -> None:
    engine = FakeEngine(fail_on=("p1__b",))
    _run(tmp_path / "run", _screens(tmp_path), engine)
    assert engine.reads == ["p1__a", "p1__a", "p1__b", "p1__c"]


def test_failed_screen_keeps_the_run_partial(tmp_path: Path) -> None:
    _run(tmp_path / "run", _screens(tmp_path), FakeEngine(fail_on=("p1__b",)))
    manifest = _manifest(tmp_path / "run")
    assert manifest["status"] == "partial"
    assert manifest["failed"] == {"p1__b": "RuntimeError: engine failed on p1__b"}
    assert not (tmp_path / "run" / "cache.json").exists()


def test_failed_screen_is_retried_on_resume(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    _run(tmp_path / "run", screens, FakeEngine(fail_on=("p1__b",)))
    engine = FakeEngine()
    _run(tmp_path / "run", screens, engine)
    assert engine.reads == ["p1__a", "p1__b"]
    assert _manifest(tmp_path / "run")["status"] == "complete"


def test_resume_with_another_configuration_is_refused(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    _run(tmp_path / "run", screens, FakeEngine(fail_on=("p1__b",)))
    with pytest.raises(ValueError, match="configuration"):
        _run(tmp_path / "run", screens, FakeEngine(), config="A1")


def test_resume_with_other_model_files_is_refused(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    _run(tmp_path / "run", screens, FakeEngine(fail_on=("p1__b",)))
    other = {"models": {"Det": {"file": "det.onnx", "sha256": "d2"}}, "versions": {"rapidocr": "test"}}
    with pytest.raises(ValueError, match="engine"):
        _run(tmp_path / "run", screens, FakeEngine(provenance=other))


def test_screenshot_with_unexpected_bytes_is_refused(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    screens[1].path.write_bytes(b"another image")
    with pytest.raises(ValueError, match="p1__b"):
        _run(tmp_path / "run", screens, FakeEngine())


def test_unknown_configuration_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="A9"):
        _run(tmp_path / "run", _screens(tmp_path), FakeEngine(), config="A9")


def test_profile_threads_reach_the_engine(tmp_path: Path) -> None:
    engine = FakeEngine()
    run_ocr("A0", "vdi2", _screens(tmp_path), tmp_path / "run", engine_factory=engine.factory)
    assert engine.threads == {"intra_op": 2, "inter_op": 1}


def test_timing_summary_describes_the_stored_screens(tmp_path: Path) -> None:
    _run(tmp_path / "run", _screens(tmp_path), FakeEngine())
    seconds = [entry["seconds"] for entry in _cache(tmp_path / "run").values()]
    timing = _manifest(tmp_path / "run")["timing"]
    assert timing["screens"] == 3
    assert timing["mean"] == pytest.approx(statistics.mean(seconds))
    assert timing["max"] == pytest.approx(max(seconds))


def test_report_refuses_a_partial_run(tmp_path: Path) -> None:
    _run(tmp_path / "run", _screens(tmp_path), FakeEngine(fail_on=("p1__b",)))
    with pytest.raises(ValueError, match="not a complete OCR run"):
        report(tmp_path / "run", tmp_path / "workbook.xlsx", tmp_path / "images")


def test_report_refuses_a_cache_edited_after_the_run(tmp_path: Path) -> None:
    _run(tmp_path / "run", _screens(tmp_path), FakeEngine())
    (tmp_path / "run" / "cache.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not a complete OCR run"):
        report(tmp_path / "run", tmp_path / "workbook.xlsx", tmp_path / "images")


# ============================================================
# Merging runs read in parallel
# ============================================================


def _shards(tmp_path: Path, screens: list[Screen], groups: tuple[tuple[int, ...], ...] = ((0,), (1, 2)),
            engines: tuple[FakeEngine, ...] | None = None, configs: tuple[str, ...] | None = None) -> list[Path]:
    paths = []
    for number, group in enumerate(groups):
        engine = engines[number] if engines else FakeEngine()
        config = configs[number] if configs else "A0"
        out = tmp_path / "shards" / str(number)
        _run(out, [screens[index] for index in group], engine, config=config)
        paths.append(out)
    return paths


def test_merged_cache_holds_every_shard_entry_in_screen_order(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    shards = _shards(tmp_path, screens, groups=((2,), (0, 1)))
    merge_runs(shards, screens, tmp_path / "merged")
    expected = {**_cache(shards[1]), **_cache(shards[0])}
    assert list(_cache(tmp_path / "merged").items()) == [(s.id, expected[s.id]) for s in screens]


def test_merged_run_is_marked_complete(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    merge_runs(_shards(tmp_path, screens), screens, tmp_path / "merged")
    assert _manifest(tmp_path / "merged")["status"] == "complete"


def test_merged_manifest_binds_the_cache_digest(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    merge_runs(_shards(tmp_path, screens), screens, tmp_path / "merged")
    digest = hashlib.sha256((tmp_path / "merged" / "cache.json").read_bytes()).hexdigest()
    assert _manifest(tmp_path / "merged")["cache_sha256"] == digest


def test_merged_identity_names_the_whole_screen_set(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    merge_runs(_shards(tmp_path, screens), screens, tmp_path / "merged")
    assert _manifest(tmp_path / "merged")["identity"]["screens"] == {s.id: s.sha256 for s in screens}


def test_merged_timing_counts_every_screen(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    shards = _shards(tmp_path, screens)
    merge_runs(shards, screens, tmp_path / "merged")
    seconds = [entry["seconds"] for shard in shards for entry in _cache(shard).values()]
    timing = _manifest(tmp_path / "merged")["timing"]
    assert (timing["screens"], timing["max"]) == (3, pytest.approx(max(seconds)))


def test_merged_timing_counts_the_sessions_of_every_shard(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    merge_runs(_shards(tmp_path, screens), screens, tmp_path / "merged")
    assert _manifest(tmp_path / "merged")["timing"]["sessions"] == 2


def test_shards_read_on_different_hosts_record_each_host(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    hosts = (FakeEngine(provenance={**PROVENANCE, "platform": {"processor": "cpu-x"}}),
             FakeEngine(provenance={**PROVENANCE, "platform": {"processor": "cpu-y"}}))
    merge_runs(_shards(tmp_path, screens, engines=hosts), screens, tmp_path / "merged")
    assert _manifest(tmp_path / "merged")["provenance"]["platforms"] == [{"processor": "cpu-x"}, {"processor": "cpu-y"}]


def test_merge_refuses_a_partial_shard(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    engines = (FakeEngine(), FakeEngine(fail_on=("p1__c",)))
    with pytest.raises(ValueError, match="is not a complete OCR run"):
        merge_runs(_shards(tmp_path, screens, engines=engines), screens, tmp_path / "merged")


def test_merge_refuses_a_shard_cache_edited_after_its_run(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    shards = _shards(tmp_path, screens)
    (shards[0] / "cache.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="is not a complete OCR run"):
        merge_runs(shards, screens, tmp_path / "merged")


def test_merge_refuses_shards_that_leave_a_screen_unread(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    with pytest.raises(ValueError, match="leave unread: p1__c"):
        merge_runs(_shards(tmp_path, screens, groups=((0,), (1,))), screens, tmp_path / "merged")


def test_merge_refuses_shards_that_read_a_screen_twice(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    with pytest.raises(ValueError, match="read more than once: p1__b"):
        merge_runs(_shards(tmp_path, screens, groups=((0, 1), (1, 2))), screens, tmp_path / "merged")


def test_merge_refuses_a_shard_of_another_reviewed_image(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    shards = _shards(tmp_path, screens)
    reviewed = [screens[0]._replace(sha256="0" * 64), *screens[1:]]
    with pytest.raises(ValueError, match="differs from the reviewed image: p1__a"):
        merge_runs(shards, reviewed, tmp_path / "merged")


def test_merge_refuses_shards_of_another_configuration(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    with pytest.raises(ValueError, match="another configuration or profile"):
        merge_runs(_shards(tmp_path, screens, configs=("A0", "A1")), screens, tmp_path / "merged")


def test_merge_refuses_shards_of_another_engine_build(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    other = {**PROVENANCE, "models": {"Det": {"file": "det.onnx", "sha256": "d2"}}}
    engines = (FakeEngine(), FakeEngine(provenance=other))
    with pytest.raises(ValueError, match="another engine build"):
        merge_runs(_shards(tmp_path, screens, engines=engines), screens, tmp_path / "merged")


def test_merge_into_an_existing_directory_is_refused(tmp_path: Path) -> None:
    screens = _screens(tmp_path)
    (tmp_path / "merged").mkdir()
    with pytest.raises(FileExistsError):
        merge_runs(_shards(tmp_path, screens), screens, tmp_path / "merged")


# ============================================================
# Selection metrics on a derived dataset
# ============================================================


def _example(practice: str, split: str, values: dict[str, str | None],
             ocr: dict[str, str]) -> dict[str, Any]:
    alignment = {field: {"status": "aligned", "ocr_text": text, "exact_text": text == values[field]}
                 for field, text in ocr.items()}
    return {"id": f"{practice}__Pagina", "practice": practice, "split": split,
            "words": [], "labels": [], "values": values, "field_alignment": alignment}


def _corpus() -> list[dict[str, Any]]:
    return [
        _example("t1", "train", {"ndg_1": "36237200", "rapporto": "034 0014 0017 05665788"},
                 {"ndg_1": "38237200", "rapporto": "034 0014 0017 05665788"}),
        _example("v1", "val", {"ndg_1": "32221698", "scadenza": "361 mesi", "tipo": None},
                 {"ndg_1": "32221698", "scadenza": "381 mesi"}),
        _example("x1", "test", {"ndg_1": "36248986"}, {"ndg_1": "36248988"}),
    ]


def test_selection_metrics_leave_out_the_historical_test(tmp_path: Path) -> None:
    metrics = ocr_selection_metrics(_corpus())
    assert set(metrics["by_split"]) == {"train", "val", "train_val"}
    assert set(metrics["per_practice"]) == {"t1", "v1"}


def test_selection_ocr_availability_counts_exact_non_null_values() -> None:
    metrics = ocr_selection_metrics(_corpus())
    assert metrics["by_split"]["train_val"]["ocr_non_null"] == {"available": 2, "total": 4}


def test_selection_identifier_availability_counts_subject_ndgs_and_accounts() -> None:
    train = ocr_selection_metrics(_corpus())["by_split"]["train"]
    assert train["subject_ndg"] == {"available": 0, "total": 1}
    assert train["rapporto"] == {"available": 1, "total": 1}


def test_six_read_as_eight_is_counted_per_practice() -> None:
    practice = ocr_selection_metrics(_corpus())["per_practice"]
    assert practice["t1"]["six_as_eight"] == 1
    assert practice["v1"]["six_as_eight"] == 1


def test_other_digit_confusions_are_not_counted_as_six_read_as_eight() -> None:
    corpus = [_example("t1", "train", {"ndg_1": "36237200"}, {"ndg_1": "36237201"})]
    assert ocr_selection_metrics(corpus)["per_practice"]["t1"]["six_as_eight"] == 0


# ============================================================
# Screens of a lot: only what the G8 assignment allows to read
# ============================================================


def _assignment(tmp_path: Path) -> Path:
    path = tmp_path / "g8_assegnazione.json"
    path.write_text(json.dumps({
        "gruppi": {"validazione_estesa": ["60000001"], "conferma": ["60000002"]},
        "schermate": {"60000001__Elenco": {"image_sha256": "aaa"}, "60000001__Note": {"image_sha256": "bbb"},
                      "60000002__Elenco": {"image_sha256": "ccc"}}}), encoding="utf-8")
    return path


def test_assigned_screens_are_those_of_the_chosen_practice(tmp_path: Path) -> None:
    screens = load_assigned_screens(_assignment(tmp_path), tmp_path, ["60000001"])
    assert [(screen.id, screen.sha256) for screen in screens] == [("60000001__Elenco", "aaa"), ("60000001__Note", "bbb")]


def test_reading_a_practice_of_the_confirmation_group_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="60000002"):
        load_assigned_screens(_assignment(tmp_path), tmp_path, ["60000002"])


def test_reading_a_practice_outside_the_assignment_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="60000003"):
        load_assigned_screens(_assignment(tmp_path), tmp_path, ["60000003"])
