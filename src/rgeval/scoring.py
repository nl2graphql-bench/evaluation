"""The RGEval scoring call.

Every entry point in this package ran the same six stages inline. This module is
the one place that sequence lives, so a caller can score a pair of queries
without reimplementing it:

    from rgeval import score_pair
    score_pair(schema_sdl, gold_query, predicted_query)
"""
from __future__ import annotations

import logging

from .pipeline import newRed
from .pipeline.AST import process_queries
from .pipeline.compare_jsons import compare_leaf_nodes
from .pipeline.cycles import process_graphs
from .pipeline.graphNet import get_graph_dict_from_ast
from .pipeline.normalizeAST import process_asts

logger = logging.getLogger(__name__)

__all__ = ["score_pair", "strip_markdown"]


def strip_markdown(query: str) -> str:
    """Drop ``` fences from a model's output, keeping the query body."""
    if not isinstance(query, str):
        return ""
    lines = []
    for line in query.split("\n"):
        if line.strip().startswith("```"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def score_pair(schema: str, gold: str, predicted: str, variables: str = "{}") -> bool:
    """True if `predicted` is semantically equivalent to `gold` under `schema`.

    Both queries are parsed and validated against the schema, normalised,
    converted to graphs, reduced, and compared. Any stage failing means the
    prediction does not score: an unparseable or schema-invalid query is False,
    not an error.

    `variables` is the JSON variables object for the query, as a string.
    """
    try:
        gold_ast, pred_ast = process_queries(schema, gold, predicted, variables)
        if gold_ast is None or pred_ast is None:
            return False
        gold_norm, pred_norm = process_asts(gold_ast, pred_ast)
        if gold_norm is None or pred_norm is None:
            return False
        gold_graph = get_graph_dict_from_ast(gold_norm)
        pred_graph = get_graph_dict_from_ast(pred_norm)
        if gold_graph is None or pred_graph is None:
            return False
        gold_clean, pred_clean, gold_struct, pred_struct = process_graphs(
            gold_graph, pred_graph
        )
        if gold_clean is None or pred_clean is None:
            return False
        if schema:
            newRed.optimize_queries(schema, gold_struct, pred_struct)
        return bool(compare_leaf_nodes(gold_clean, pred_clean))
    except Exception as exc:                      # noqa: BLE001 - any failure is a 0
        logger.debug("scoring failed: %s", exc)
        return False
