"""RGEval: semantic-equivalence scoring for generated GraphQL queries.

Compares a generated query against a reference by normalising both against the
schema and comparing them as graphs, so a query that is correct but written
differently is not scored wrong.
"""
__version__ = "0.1.0"

from .scoring import score_pair

__all__ = ["score_pair", "__version__"]
