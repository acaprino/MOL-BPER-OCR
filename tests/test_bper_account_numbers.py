"""Invented Rapporto numbers read like the real ones, so OCR meets the same digits it meets on the real pages.

The 12 real Rapporto values of the calibration fold (calibration and control practices, counted without values)
all have the shape "034 <branch, 4 digits> 0017 <8 digits>"; the last block has exactly one leading zero, 5 to 7
distinct digits (5 in 5 values, 6 in 6, 7 in 1) and never the same digit three times in a row. A block of seven
zeros and a digit was misread by the live OCR ("00000001" -> "00000000") where the real tails were read right.
"""

from collections import Counter
from pathlib import Path
import re

import pytest

from bper_profiles import load_profiles
from bper_synthetic_db import synthetic_practices

REPO = Path(__file__).resolve().parents[1]
PROFILE_FILES = {
    "generated-set-01": REPO / "bper-emulator" / "profiles" / "generated-set-01.json",
    "generated-set-02": REPO / "bper-emulator" / "profiles" / "generated-set-02.json",
    "list-names fixture": REPO / "tests" / "fixtures" / "bper_profiles_list_names.json",
}
SOURCES = ["seed", *PROFILE_FILES]
REAL_LEADING_ZEROS = 1
REAL_DISTINCT_DIGITS = {5: 5, 6: 6, 7: 1}
REAL_LONGEST_RUN = 2


def _practices(source: str) -> list[dict]:
    practices = synthetic_practices() if source == "seed" else load_profiles(PROFILE_FILES[source], archive=None)
    return [p for p in practices if p["role"] == "sintetica"]


def _accounts(source: str) -> list[tuple[dict, dict]]:
    """(practice, credit line) of every Rapporto a source shows."""
    return [(p, f) for p in _practices(source) for f in p["fidi"] if f["account"]]


def _tails(source: str) -> list[str]:
    return [f["account"].split()[-1] for _, f in _accounts(source)]


def _leading_zeros(tail: str) -> int:
    return len(tail) - len(tail.lstrip("0"))


def _longest_run(tail: str) -> int:
    return max(len(m.group(0)) for m in re.finditer(r"(\d)\1*", tail))


@pytest.mark.parametrize("source", SOURCES)
def test_no_rapporto_tail_has_more_leading_zeros_than_the_real_ones(source: str) -> None:
    assert sorted(t for t in _tails(source) if _leading_zeros(t) > REAL_LEADING_ZEROS) == []


@pytest.mark.parametrize("source", SOURCES)
def test_every_rapporto_tail_starts_with_one_zero_as_all_real_ones_do(source: str) -> None:
    assert sorted(t for t in _tails(source) if _leading_zeros(t) != REAL_LEADING_ZEROS) == []


@pytest.mark.parametrize("source", SOURCES)
def test_every_rapporto_tail_has_five_to_seven_distinct_digits(source: str) -> None:
    assert sorted(t for t in _tails(source) if len(set(t)) not in REAL_DISTINCT_DIGITS) == []


@pytest.mark.parametrize("source", SOURCES)
def test_no_rapporto_tail_repeats_a_digit_three_times_in_a_row(source: str) -> None:
    assert sorted(t for t in _tails(source) if _longest_run(t) > REAL_LONGEST_RUN) == []


def test_distinct_digit_counts_follow_the_real_shares() -> None:
    tails = [t for source in SOURCES for t in _tails(source)]
    shares = Counter(len(set(t)) for t in tails)
    real = sum(REAL_DISTINCT_DIGITS.values())
    assert [n for n, count in REAL_DISTINCT_DIGITS.items() if abs(shares[n] / len(tails) - count / real) > 0.15] == []


def test_some_rapporto_tails_have_a_digit_twice_in_a_row() -> None:
    # 9 of the 12 real tails do.
    tails = [t for source in SOURCES for t in _tails(source)]
    assert sum(_longest_run(t) == 2 for t in tails) >= len(tails) / 3


def test_every_synthetic_rapporto_is_unique_across_the_catalogue() -> None:
    accounts = [f["account"] for source in SOURCES for _, f in _accounts(source)]
    assert sorted(a for a, n in Counter(accounts).items() if n > 1) == []


@pytest.mark.parametrize("source", SOURCES)
def test_the_rapporto_names_the_bank_the_branch_and_the_line(source: str) -> None:
    # Real: 034, the branch code on four digits and 0017 (12/12, one credit line each); a second line keeps 0018.
    def ok(p: dict, f: dict) -> bool:
        kind = "0018" if f["id"] == "F2" else "0017"
        return re.fullmatch(rf"034 {p['branch'].zfill(4)} {kind} \d{{8}}", f["account"]) is not None

    assert sorted(f["account"] for p, f in _accounts(source) if not ok(p, f)) == []
