"""Tests for emnlp_evaluation.

Focus: RGEval must not count a broken test item (a gold query that fails GraphQL
validation under its schema, e.g. a malformed schema) as a wrong prediction. Such
an item is UNSCOREABLE and is excluded from the accuracy denominator.

Run:
    .venv-local/bin/python -m pytest test_emnlp_evaluation.py -v
or without pytest:
    .venv-local/bin/python test_emnlp_evaluation.py
"""
import os
import json
import logging
import tempfile
import shutil

import pandas as pd

import emnlp_evaluation as ev

# The pipeline is chatty at INFO; keep test output readable.
logging.getLogger().setLevel(logging.ERROR)

# --- fixtures -----------------------------------------------------------------

VALID_SCHEMA = """
type Query { city(id: Int!): City }
type City { id: Int! name: String population: Float }
"""

# Mirrors the real NL2GQL_Testset defect: City claims to implement an interface
# but does not provide the interface's required field, so the schema fails to
# build and EVERY query on it (gold included) fails validation.
BROKEN_SCHEMA = """
interface census_details { population: Float }
type City implements census_details { id: Int! name: String }
type Query { city(id: Int!): City }
"""

GOLD = "query { city(id: 1) { name population } }"
SAME_AS_GOLD = "query { city(id: 1) { population name } }"   # reordered, equivalent
DIFFERENT = "query { city(id: 1) { name } }"                 # missing a field
GOLD_ON_BROKEN = "query { city(id: 1) { name } }"


# --- compare_pair unit tests --------------------------------------------------

def test_compare_pair_identical_is_true():
    assert ev.compare_pair(VALID_SCHEMA, GOLD, GOLD) is True

def test_compare_pair_equivalent_is_true():
    # Field order should not matter for graph equivalence.
    assert ev.compare_pair(VALID_SCHEMA, GOLD, SAME_AS_GOLD) is True

def test_compare_pair_different_is_false():
    assert ev.compare_pair(VALID_SCHEMA, GOLD, DIFFERENT) is False

def test_compare_pair_broken_schema_is_none():
    # A malformed schema cannot be evaluated -> None (NOT False).
    assert ev.compare_pair(BROKEN_SCHEMA, GOLD_ON_BROKEN, GOLD_ON_BROKEN) is None

def test_compare_pair_none_is_distinct_from_false():
    # The whole point of the fix: unscoreable (None) must be distinguishable
    # from a genuine mismatch (False).
    broken = ev.compare_pair(BROKEN_SCHEMA, GOLD_ON_BROKEN, GOLD_ON_BROKEN)
    mismatch = ev.compare_pair(VALID_SCHEMA, GOLD, DIFFERENT)
    assert broken is None
    assert mismatch is False
    assert broken is not mismatch


# --- end-to-end evaluate_emnlp_file test --------------------------------------

def _write_dataset(workdir):
    """Build a tiny synthetic test_emnlp dataset: 3 rows.

    Row 1 (Sno 1): valid schema, prediction CORRECT   -> scoreable, correct
    Row 2 (Sno 2): valid schema, prediction WRONG      -> scoreable, incorrect
    Row 3 (Sno 3): broken schema (unscoreable gold)    -> invalid, excluded
    """
    every = os.path.join(workdir, "every_prediction")
    os.makedirs(every, exist_ok=True)

    df = pd.DataFrame([
        {"Sno": 1, "CleanSchema": VALID_SCHEMA,  "GT_GQL": GOLD,
         "frag": "No", "mtype": "No", "filter": "No", "alias": "No"},
        {"Sno": 2, "CleanSchema": VALID_SCHEMA,  "GT_GQL": GOLD,
         "frag": "No", "mtype": "No", "filter": "No", "alias": "No"},
        # Row 3: an external-fragment style row on the broken schema.
        {"Sno": 3, "CleanSchema": BROKEN_SCHEMA, "GT_GQL": GOLD_ON_BROKEN,
         "frag": "No", "mtype": "No", "filter": "No", "alias": "No"},
    ])
    # evaluate_emnlp_file hard-codes this filename for the new dataset.
    df.to_excel(os.path.join(every, "NL2GQL_Testset_V20.1 (1).xlsx"), index=False)

    preds = [
        {"id": 1, "gold": GOLD,           "pred_model": SAME_AS_GOLD},   # correct
        {"id": 2, "gold": GOLD,           "pred_model": DIFFERENT},      # wrong
        {"id": 3, "gold": GOLD_ON_BROKEN, "pred_model": GOLD_ON_BROKEN}, # gold==pred but unscoreable
    ]
    # filename must contain "test_emnlp" so is_new_dataset triggers.
    input_file = "synthetic_test_emnlp_predictions.jsonl"
    with open(os.path.join(every, input_file), "w") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    return input_file


def _run_eval_in(workdir, input_file):
    """Run evaluate_emnlp_file with cwd set to workdir; return parsed results."""
    prev = os.getcwd()
    os.chdir(workdir)
    try:
        ev.evaluate_emnlp_file(input_file)
        out = os.path.join(workdir, "review_evals", input_file, "results.json")
        with open(out) as f:
            return json.load(f)
    finally:
        os.chdir(prev)


def test_end_to_end_excludes_invalid_item():
    workdir = tempfile.mkdtemp(prefix="rgeval_test_")
    try:
        input_file = _write_dataset(workdir)
        res = _run_eval_in(workdir, input_file)

        assert "pred_model" in res, "pred_ key not detected"
        overall = res["pred_model"]["Overall"]

        # 3 items seen, 1 unscoreable (broken schema), 2 scoreable.
        assert overall["total"] == 3, overall
        assert overall["invalid"] == 1, overall
        assert overall["scoreable"] == 2, overall
        # 1 of the 2 scoreable predictions is correct.
        assert overall["correct"] == 1, overall

        # Primary accuracy uses the scoreable denominator: 1/2 = 50.0,
        # NOT 1/3 = 33.33 (which is what counting the broken item as wrong gives).
        assert overall["accuracy_percent"] == 50.0, overall
        # Legacy accuracy (invalid counted as wrong) is preserved for comparison.
        assert overall["accuracy_percent_legacy"] == 33.33, overall
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_end_to_end_broken_item_not_scored_wrong():
    """The unscoreable item's prediction equals its gold; under the old code it
    scored 0 (wrong). It must now be excluded, never counted as correct or wrong."""
    workdir = tempfile.mkdtemp(prefix="rgeval_test_")
    try:
        input_file = _write_dataset(workdir)
        res = _run_eval_in(workdir, input_file)
        # The broken row is a 'selections' category item (frag/mtype/... all No,
        # no '@', no pagination keys). Find whichever category holds it.
        model = res["pred_model"]
        # Sum invalid across categories == 1, and that item contributed to
        # neither correct nor scoreable.
        total_invalid = sum(v["invalid"] for k, v in model.items() if k != "Overall")
        total_correct = sum(v["correct"] for k, v in model.items() if k != "Overall")
        total_scoreable = sum(v["scoreable"] for k, v in model.items() if k != "Overall")
        assert total_invalid == 1
        assert total_correct == 1
        assert total_scoreable == 2
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --- allow running without pytest ---------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    raise SystemExit(1 if failed else 0)
