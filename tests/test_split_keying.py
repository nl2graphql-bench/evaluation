"""The public benchmark's two parts must not be scored against each other's schema.

test_main numbers its rows DataID 1..1845 and test_part2 numbers its 1..4558, so
all 1845 test_main ids collide with a part2 id. A loader keyed on DataID alone
lets whichever file it reads last win for those ids, and glob() order is
filesystem-dependent, so scores are not even reproducible across machines.

This test needs the two gold xlsx, which are not in this repository: get them
from https://github.com/nl2graphql-bench/datasets and point EVALS_DIR at them.
It skips when they are absent.
"""
import glob
import os

import pytest

pd = pytest.importorskip("pandas", reason="needs the [datasets] extra")

EVALS_DIR = os.environ.get("EVALS_DIR", "2026_evals")
MAIN = os.path.join(EVALS_DIR, "test_main_clean.xlsx")
PART2 = os.path.join(EVALS_DIR, "test_part2_clean.xlsx")

pytestmark = pytest.mark.skipif(
    not (os.path.exists(MAIN) and os.path.exists(PART2)),
    reason=f"gold xlsx not found under {EVALS_DIR}; see the module docstring",
)

SPLITS = {"test_main": "test_main", "test_part2": "test_part2"}


def _split_of(path):
    name = os.path.basename(path)
    for stem, split in SPLITS.items():
        if name.startswith(stem):
            return split
    return None


def _rank(path):
    name = os.path.basename(path)
    if "_clean_backup" in name:
        return 0          # a backup of the PRE-clean file despite the name
    if "_clean" in name:
        return 2
    return 1


def _load_split_aware():
    """One gold file per split, preferring the clean testset."""
    chosen = {}
    for path in sorted(glob.glob(os.path.join(EVALS_DIR, "*.xlsx"))):
        split = _split_of(path)
        if split is None:
            continue
        if split in chosen and _rank(chosen[split]) >= _rank(path):
            continue
        chosen[split] = path
    out = {}
    for split, path in chosen.items():
        for _, row in pd.read_excel(path).iterrows():
            out[(split, row["DataID"])] = str(row.get("CleanSchema", ""))
    return out, chosen


def _load_dataid_only():
    """The pre-fix loader: every xlsx into one dict keyed by DataID."""
    out = {}
    for path in sorted(glob.glob(os.path.join(EVALS_DIR, "*.xlsx"))):
        for _, row in pd.read_excel(path).iterrows():
            out[row["DataID"]] = str(row.get("CleanSchema", ""))
    return out


def _truth():
    return {row["DataID"]: str(row.get("CleanSchema", ""))
            for _, row in pd.read_excel(MAIN).iterrows()}


def test_the_id_spaces_really_do_collide():
    """If they ever stop overlapping, split-awareness is no longer load-bearing."""
    main_ids = set(_truth())
    part2_ids = {row["DataID"] for _, row in pd.read_excel(PART2).iterrows()}
    assert main_ids & part2_ids, "expected the two parts to share DataIDs"


def test_split_aware_loader_returns_each_part_s_own_schema():
    truth = _truth()
    aware, _ = _load_split_aware()
    wrong = [i for i in truth if aware.get(("test_main", i)) != truth[i]]
    assert not wrong, f"{len(wrong)} test_main ids got another part's schema"


def test_clean_testset_is_preferred_over_the_backup():
    _, chosen = _load_split_aware()
    for split, path in chosen.items():
        assert "_clean_backup" not in os.path.basename(path), (
            f"{split}: picked _clean_backup, which is the PRE-clean file")
        assert "_clean.xlsx" in os.path.basename(path), f"{split}: picked {path}"
