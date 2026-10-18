"""Behavioral checks for word-aligned LiLT training, without downloaded weights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from training.model import (
    _augment, dataset_fingerprint, encode_chunks, normalize_boxes, predict,
    score_predictions, train_model, validate_reviewed_dataset, validate_splits,
)


class Encoding(dict[str, Any]):
    def __init__(self, ids: list[int], word_ids: list[int | None]) -> None:
        super().__init__(input_ids=ids, attention_mask=[1] * len(ids))
        self._word_ids = word_ids

    def word_ids(self) -> list[int | None]:
        return self._word_ids


class BoundaryTokenizer:
    """An external tokenizer boundary with visible, deterministic subwords."""

    pad_token_id = 0

    def num_special_tokens_to_add(self, pair: bool = False) -> int:
        return 2

    def __call__(
        self,
        words: list[str],
        *,
        is_split_into_words: bool,
        add_special_tokens: bool = True,
        truncation: bool = False,
        **kwargs: Any,
    ) -> Encoding:
        assert is_split_into_words
        assert not truncation, "Training may never silently truncate a labeled word"
        ids, word_ids = [], []
        if add_special_tokens:
            ids.append(1)
            word_ids.append(None)
        for i, word in enumerate(words):
            pieces = 2 if word.startswith("long") else 1
            ids.extend([3 + i] * pieces)
            word_ids.extend([i] * pieces)
        if add_special_tokens:
            ids.append(2)
            word_ids.append(None)
        return Encoding(ids, word_ids)


def example(texts: list[str], rows: list[int] | None = None) -> dict[str, Any]:
    return {
        "id": "sample", "practice": "practice-a", "split": "train",
        "image_size": [1000, 500],
        "words": [
            {"text": text, "x0": 100 + 10 * i, "y0": 50, "x1": 110 + 10 * i,
             "y1": 60, "row": rows[i] if rows is not None else i}
            for i, text in enumerate(texts)
        ],
        "labels": ["ndg"] * len(texts),
        "values": {"ndg": "sample"},
    }


def test_boxes_use_the_full_image_frame() -> None:
    item = example(["a", "b"])
    assert normalize_boxes(item) == [[100, 100, 110, 120], [110, 100, 120, 120]]
    assert "box" not in item["words"][0]


def test_chunks_keep_a_row_together_when_it_fits() -> None:
    item = example(["a", "b", "c", "d", "e"], [0, 0, 1, 1, 1])
    chunks = encode_chunks(item, BoundaryTokenizer(), ["O", "ndg"], max_length=6)
    assert [chunk["group"] for chunk in chunks] == [[0, 1], [2, 3, 4]]


def test_chunks_split_an_oversized_row_without_losing_words() -> None:
    item = example(["a", "long-b", "c", "d"], [0, 0, 0, 0])
    chunks = encode_chunks(item, BoundaryTokenizer(), ["O", "ndg"], max_length=5)
    assert [chunk["group"] for chunk in chunks] == [[0, 1], [2, 3]]
    assert [i for chunk in chunks for i in chunk["group"]] == list(range(4))
    assert all(len(chunk["input_ids"]) <= 5 for chunk in chunks)


def test_only_first_subwords_receive_a_training_target() -> None:
    item = example(["long-a", "b"])
    item["labels"] = ["ndg", "IGNORE"]
    chunk = encode_chunks(item, BoundaryTokenizer(), ["O", "ndg"])[0]
    assert chunk["labels"] == [-100, 1, -100, -100, -100]
    assert chunk["bbox"][1:3] == [[100, 100, 110, 120]] * 2


def test_a_word_longer_than_the_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="word.*window|window.*word"):
        encode_chunks(example(["long-a"]), BoundaryTokenizer(), ["O", "ndg"], max_length=3)


def test_a_tokenizer_that_drops_a_word_is_rejected() -> None:
    class DroppingTokenizer(BoundaryTokenizer):
        def __call__(self, words: list[str], **kwargs: Any) -> Encoding:
            return super().__call__(words[:-1], **kwargs)

    with pytest.raises(ValueError, match="word"):
        encode_chunks(example(["a", "b"]), DroppingTokenizer(), ["O", "ndg"])


def test_prediction_preserves_input_word_order_across_chunks() -> None:
    torch = pytest.importorskip("torch")
    from transformers import LiltConfig, LiltForTokenClassification

    torch.manual_seed(7)
    config = LiltConfig(
        vocab_size=20, hidden_size=48, num_hidden_layers=1,
        num_attention_heads=4, intermediate_size=64, channel_shrink_ratio=4,
        max_position_embeddings=64, num_labels=2, pad_token_id=0,
    )
    model = LiltForTokenClassification(config).eval()
    item = example(["a", "long-b", "c", "d"])
    roles, probs = predict(model, BoundaryTokenizer(), item, ["O", "ndg"], max_length=5)
    assert len(roles) == len(probs) == 4
    assert set(roles) <= {"O", "ndg"}
    assert all(0.5 <= p <= 1.0 for p in probs)


def test_practices_cannot_cross_split_boundaries() -> None:
    first = example(["a"])
    second = {**example(["b"]), "id": "other", "split": "test"}
    with pytest.raises(ValueError, match="practice"):
        validate_splits([first, second])


def test_reviewed_dataset_rejects_modified_labels() -> None:
    examples = []
    for index in range(113):
        practice = index % 12
        item = {**example(["a"]), "id": str(index), "practice": str(practice),
                "split": "train" if practice < 8 else "val" if practice < 10 else "test",
                "values": {f"field-{field}": "value" for field in range(9 if index < 104 else 8)}}
        examples.append(item)
    roles = ["O", "ndg"]
    manifest = {"reviewed_rows": 1008, "screens": 113, "practices": 12, "roles": roles,
                "dataset_version": "ground-truth-v3.1", "leakage_audit": {"status": "passed"},
                "dataset_content_sha256": dataset_fingerprint(examples, roles)}
    validate_reviewed_dataset(examples, roles, manifest)
    examples[0]["labels"] = ["O"]
    with pytest.raises(ValueError, match="fingerprint|hash"):
        validate_reviewed_dataset(examples, roles, manifest)


def _tiny_base(tmp_path: Path) -> tuple[Path, list[dict[str, Any]]]:
    torch = pytest.importorskip("torch")
    pytest.importorskip("tokenizers")
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from tokenizers.processors import TemplateProcessing
    from transformers import LiltConfig, LiltForTokenClassification, PreTrainedTokenizerFast

    torch.set_num_threads(1)
    base = tmp_path / "base"
    config = LiltConfig(vocab_size=8, hidden_size=48, num_hidden_layers=1,
                        num_attention_heads=4, intermediate_size=64, channel_shrink_ratio=4,
                        max_position_embeddings=64, num_labels=2, pad_token_id=0)
    LiltForTokenClassification(config).save_pretrained(base)
    raw = Tokenizer(WordLevel({"<pad>": 0, "<s>": 1, "</s>": 2, "<unk>": 3,
                               "a": 4, "b": 5, "c": 6, "d": 7}, unk_token="<unk>"))
    raw.pre_tokenizer = Whitespace()
    raw.post_processor = TemplateProcessing(single="<s> $A </s>", special_tokens=[("<s>", 1), ("</s>", 2)])
    tokenizer = PreTrainedTokenizerFast(tokenizer_object=raw, pad_token="<pad>", unk_token="<unk>",
                                        bos_token="<s>", eos_token="</s>")
    tokenizer.save_pretrained(base)
    examples = [{**example(["a", "b"]), "id": split, "practice": split, "split": split}
                for split in ("train", "val", "test")]
    return base, examples


@pytest.fixture(scope="module")
def tiny_training_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    tmp_path = tmp_path_factory.mktemp("tiny-lilt")
    base, examples = _tiny_base(tmp_path)
    output = tmp_path / "trained"
    result = train_model(examples, ["O", "ndg"], output, {}, base_path=str(base),
                         epochs=1, variants=0, device="cpu")
    return result, output


def test_a_bounded_run_may_last_sixteen_epochs(tmp_path: Path) -> None:
    base, examples = _tiny_base(tmp_path)
    result = train_model(examples, ["O", "ndg"], tmp_path / "trained", {}, base_path=str(base),
                         epochs=16, variants=0, device="cpu")
    assert 1 <= result["best_epoch"] <= 16


def test_a_bounded_run_may_wait_four_epochs_without_improvement(tmp_path: Path) -> None:
    base, examples = _tiny_base(tmp_path)
    result = train_model(examples, ["O", "ndg"], tmp_path / "trained", {}, base_path=str(base),
                         epochs=6, variants=0, device="cpu", patience=4)
    assert len(result["train_log"]) >= min(6, result["best_epoch"] + 4)


def test_a_run_past_sixteen_epochs_is_refused(tmp_path: Path) -> None:
    base, examples = _tiny_base(tmp_path)
    with pytest.raises(ValueError, match="bounded experiment"):
        train_model(examples, ["O", "ndg"], tmp_path / "trained", {}, base_path=str(base),
                    epochs=17, variants=0, device="cpu")


def test_a_cpu_training_run_saves_the_selected_checkpoint(tiny_training_run: tuple[dict[str, Any], Path]) -> None:
    from transformers import LiltForTokenClassification

    result, output = tiny_training_run
    assert result["best_epoch"] == 1
    assert set(result["test_predictions"]) == {"test"}
    assert all("test_f1" not in row for row in result["train_log"])
    assert result["manifest"]["test_evaluations"] == 1
    saved = LiltForTokenClassification.from_pretrained(output)
    assert saved.config.id2label == {0: "O", 1: "ndg"}
    assert json.loads((output / "splits.json").read_text())["test"]["practices"] == ["test"]


def test_training_result_contains_only_native_json_types(tiny_training_run: tuple[dict[str, Any], Path]) -> None:
    """A lightweight caller must not need torch to deserialize remote metadata."""
    result, _ = tiny_training_run

    def assert_native(value: Any) -> None:
        assert type(value) in {dict, list, str, int, float, bool, type(None)}, type(value)
        if type(value) is dict:
            for key, child in value.items():
                assert type(key) is str
                assert_native(child)
        elif type(value) is list:
            for child in value:
                assert_native(child)

    assert_native(result)


def test_fidi_table_block_is_not_split_from_its_header_across_chunks() -> None:
    words = ["top1", "top2", "top3", "FIDI", "Fido", "Rapporto", "F1", "034"]
    rows = [0, 1, 2, 3, 4, 4, 5, 5]
    item = example(words, rows)
    chunks = encode_chunks(item, BoundaryTokenizer(), ["O", "ndg"], max_length=8)
    assert [chunk["group"] for chunk in chunks] == [[0, 1, 2], [3, 4, 5, 6, 7]]


def test_augmentation_preserves_thousand_zeros_and_column_separation() -> None:
    import random

    item = {
        "id": "fidi", "practice": "p1", "split": "train",
        "image_size": [1000, 1000],
        "words": [
            {"text": "150.000", "x0": 327.0, "y0": 580.0, "x1": 344.0, "y1": 595.0, "row": 0},
            {"text": "380.000", "x0": 470.0, "y0": 625.0, "x1": 510.0, "y1": 640.0, "row": 1},
        ],
        "labels": ["importo_euro", "O"],
        "values": {"importo_euro": "150.000"},
    }
    rng = random.Random(42)
    for _ in range(20):
        aug = _augment(item, rng)
        pos_word, bg_word = aug["words"]
        assert pos_word["text"].endswith(".000")
        assert bg_word["text"].endswith(".000")
        # x0=327 must never drift left into the scadenza column (x1 <= 320)
        assert pos_word["x0"] > 321.0


def test_score_predictions_reports_whole_field_and_non_note_metrics() -> None:
    item = {
        "id": "s1", "practice": "p1", "split": "val",
        "image_size": [1000, 1000],
        "words": [
            {"text": "nota1", "x0": 10, "y0": 10, "x1": 40, "y1": 20, "row": 0},
            {"text": "nota2", "x0": 50, "y0": 10, "x1": 80, "y1": 20, "row": 0},
            {"text": "150.000", "x0": 330, "y0": 580, "x1": 350, "y1": 595, "row": 1},
        ],
        "labels": ["note_della_richiesta", "note_della_richiesta", "importo_euro"],
        "values": {"note_della_richiesta": "nota1 nota2", "importo_euro": "150.000"},
    }
    preds = {"s1": {"pred": ["note_della_richiesta", "note_della_richiesta", "scadenza"]}}
    roles = ["O", "note_della_richiesta", "importo_euro", "scadenza"]
    scored = score_predictions([item], preds, roles)
    assert scored["field_accuracy"] == 0.5
    assert scored["credit_field_accuracy"] == 0.0
    assert scored["non_note_f1"] == 0.0

