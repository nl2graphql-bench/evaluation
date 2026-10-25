# NL2GraphQL Bench: evaluation

RGEval, the scorer behind the [NL2GraphQL Bench
leaderboard](https://nl2graphql-bench.github.io/).

A generated GraphQL query can be correct without matching the reference string:
field order varies, aliases rename things, fragments can be inlined. RGEval
compares the two queries as graphs after normalising them against the schema, so
it scores semantic equivalence rather than text.

## How scoring works

Each query is parsed and validated against its schema, normalised, converted to
a graph, reduced, and then compared. A query that fails any stage scores 0.

| stage | module |
|---|---|
| parse + validate against the schema | `pipeline/AST.py` |
| AST normalisation | `pipeline/normalizeAST.py` |
| graph construction | `pipeline/graphNet.py` |
| cycle handling | `pipeline/cycles.py` |
| reduction | `pipeline/newRed.py` |
| comparison | `pipeline/compare_jsons.py` |

## Install

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`networkx` must stay below 3.0: the graph code uses APIs removed in 3.x.

## Scoring the public benchmark

Get the data from
[nl2graphql-bench/datasets](https://github.com/nl2graphql-bench/datasets):

```bash
gunzip -k test_data.jsonl.gz
```

Each row carries the schema (`CleanSchema`), the reference query
(`GraphQLQuery`), its variables, and category labels. Use `CleanSchema`:
`OriginalGraphQLSchema` and `RefinedGraphQLSchema` are truncated at 32,767
characters in some rows and will not build.

Predictions are JSONL, one object per instance, keyed by `DataID`, with the
model output in a field starting with `pred_`:

```json
{"id": 1, "gold": "query { ... }", "pred_mymodel": "query { ... }"}
```

Then:

```bash
mkdir -p 2026_input/myrun && cp predictions.jsonl 2026_input/myrun/test_main_predictions.jsonl
PYTHONPATH=. .venv/bin/python 2026_eval.py --input_folder myrun
```

Results land in `2026_results/myrun/results.json` with an overall score and a
per-category breakdown.

Name prediction files `test_main_*` or `test_part2_*`. The scorer reads the part
from the filename, because the two parts number their rows from 1 each and a
`DataID` alone does not say which part a row belongs to.

## Entry points

| script | purpose |
|---|---|
| `2026_eval.py` | score the public benchmark (`test_main`, `test_part2`) |
| `2024_eval.py` | score the external benchmark (Kesarwani et al., 2024) |
| `emnlp_evaluation.py` | per-model scoring over a predictions folder |
| `claude_evaluation.py` | scoring an API model's output |
| `clean_new_dataset.py` | repair SDL that `graphql-core` cannot build |
| `add_clean_schema.py` | add a `CleanSchema` column to a dataset |
| `app.py` | local UI for inspecting a scored run |

## Tests

```bash
EVALS_DIR=2026_evals PYTHONPATH=. .venv/bin/python test_2026_eval_split_keying.py
```

Checks that each part is scored against its own schema. Needs
`test_main_clean.xlsx` and `test_part2_clean.xlsx` in `2026_evals/`.

## What is not here

No datasets and no model predictions: datasets are in
[nl2graphql-bench/datasets](https://github.com/nl2graphql-bench/datasets), and
predictions are an input you supply.

The 2,100-instance hidden benchmark is not published anywhere. It is what
submissions are scored against, so if it were public a model could be tuned on
it and the score would mean nothing.

## Links

- Leaderboard: https://nl2graphql-bench.github.io/
- Datasets: https://github.com/nl2graphql-bench/datasets
- Generation framework: https://github.com/nl2graphql-bench/generation
- All components: https://github.com/nl2graphql-bench/index
