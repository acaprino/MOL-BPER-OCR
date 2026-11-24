"""Invented branches read like the real ones: "Filiale relazione" stays on one line of the PEF pages.

The real archive's "<code> - <name>" (calibration and control practices, counted without values) has 11 to 19
characters, names of at most 12 and codes of 2, 3 or 4 digits; of its 17 names 11 have one word, 5 two and 1 three.
Every synthetic practice the emulator serves (the seed, both generated sets, the list-name fixture) keeps within it.
"""

from collections import Counter
from pathlib import Path

import pytest

from bper_profiles import load_profiles
from bper_synthetic_db import BRANCHES, synthetic_practices

REPO = Path(__file__).resolve().parents[1]
PROFILE_FILES = {
    "generated-set-01": REPO / "bper-emulator" / "profiles" / "generated-set-01.json",
    "generated-set-02": REPO / "bper-emulator" / "profiles" / "generated-set-02.json",
    "list-names fixture": REPO / "tests" / "fixtures" / "bper_profiles_list_names.json",
}
REAL_WORDS = {1: 11, 2: 5, 3: 1}


def _branches(source: str) -> set[tuple[str, str]]:
    """(code, name) of the branches a source shows."""
    if source == "seed table":
        return {(code, name) for code, name, _ in BRANCHES}
    practices = synthetic_practices() if source == "seed" else load_profiles(PROFILE_FILES[source], archive=None)
    return {(p["branch"], p["branchName"]) for p in practices if p["role"] == "sintetica"}


SOURCES = ["seed table", "seed", *PROFILE_FILES]


@pytest.mark.parametrize("source", SOURCES)
def test_every_branch_line_has_at_most_nineteen_characters(source: str) -> None:
    assert sorted(line for code, name in _branches(source) if len(line := f"{code} - {name}") > 19) == []


@pytest.mark.parametrize("source", SOURCES)
def test_every_branch_name_has_at_most_twelve_characters(source: str) -> None:
    assert sorted(name for _, name in _branches(source) if len(name) > 12) == []


@pytest.mark.parametrize("source", SOURCES)
def test_every_branch_code_has_two_to_four_digits(source: str) -> None:
    assert sorted(code for code, _ in _branches(source) if not (code.isdigit() and 2 <= len(code) <= 4)) == []


def test_branch_names_mix_one_two_and_three_words_like_the_real_ones() -> None:
    names = {name for source in SOURCES for _, name in _branches(source)}
    words = Counter(min(len(name.split()), 3) for name in names)
    real = sum(REAL_WORDS.values())
    assert [n for n, count in REAL_WORDS.items() if abs(words[n] / len(names) - count / real) > 0.12] == []
