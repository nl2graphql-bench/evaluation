# rgeval

Semantic-equivalence scoring for generated GraphQL queries. The scorer behind
the [NL2GraphQL Bench leaderboard](https://nl2graphql-bench.github.io/).

A generated GraphQL query can be correct without matching the reference text:
field order varies, aliases rename things, fragments can be inlined. RGEval
parses and validates both queries against the schema, normalises them, and
compares them as graphs, so it scores meaning rather than string equality.

## Install

```bash
pip install rgeval
```

Reading the benchmark `.xlsx` files needs the extra:

```bash
pip install "rgeval[datasets]"
```

## Use as a library

```python
from rgeval import score_pair

schema = """
type Query { city(id: Int!): City }
type City { id: Int! name: String population: Float }
"""
gold = 'query { city(id: 1) { name population } }'
pred = 'query { city(id: 1) { population name } }'   # different field order

score_pair(schema, gold, pred)        # True
```

`score_pair` returns `False` rather than raising for a query that cannot be
parsed or does not validate against the schema: an invalid prediction scores 0.

```python
score_pair(schema, gold, pred, variables='{"cityId": 1}')
```

## Score the public benchmark

Get the data from
[nl2graphql-bench/datasets](https://github.com/nl2graphql-bench/datasets):

```bash
gunzip -k test_data.jsonl.gz
```

Use the `CleanSchema` field. `OriginalGraphQLSchema` and
`RefinedGraphQLSchema` are truncated at 32,767 characters in some rows and will
not build.

Predictions are JSONL, one object per instance, with the model output in a field
starting with `pred_`:

```json
{"id": 1, "gold": "query { ... }", "pred_mymodel": "query { ... }"}
```

```bash
mkdir -p 2026_input/myrun
cp predictions.jsonl 2026_input/myrun/test_main_predictions.jsonl
rgeval-score-2026 --input_folder myrun
```

Results land in `2026_results/myrun/results.json` with an overall score and a
per-category breakdown.

Name prediction files `test_main_*` or `test_part2_*`. The scorer reads the part
from the filename, because the two parts of the public benchmark number their
rows from 1 each and a `DataID` alone does not say which part a row is from.

## How scoring works

| stage | module |
|---|---|
| parse and validate against the schema | `rgeval.pipeline.AST` |
| AST normalisation | `rgeval.pipeline.normalizeAST` |
| graph construction | `rgeval.pipeline.graphNet` |
| cycle handling | `rgeval.pipeline.cycles` |
| reduction | `rgeval.pipeline.newRed` |
| comparison | `rgeval.pipeline.compare_jsons` |

`rgeval.score_pair` runs all six in order. Import a stage directly only to
inspect or replace it.

## Requirements

Python 3.9+. `networkx` is pinned below 3.0: the graph code uses APIs removed in
3.x.

## What is not here

No datasets and no model predictions. Datasets are in
[nl2graphql-bench/datasets](https://github.com/nl2graphql-bench/datasets);
predictions are an input you supply.

The 2,100-instance hidden benchmark is not published anywhere. It is what
submissions are scored against, so if it were public a model could be tuned on
it and the score would mean nothing.

## Citation

AutoGraphQL: A Bring-Your-Own-Schema Framework for Adapting Open-Weight LLMs to
GraphQL APIs. EMNLP 2026, Industry Track.
<https://openreview.net/forum?id=NcuPXBFKAO>

## License

MIT, see `LICENSE`. `NOTICE` records why: the source repository carried
CC BY-NC-ND 4.0, which is not an OSI-approved open-source license and bars both
commercial use and derivative works, neither of which suits a package people
install and extend. The other NL2GraphQL Bench components and the upstream
StepZen dataset are all MIT.
