"""RGEval: semantic-equivalence scoring for generated GraphQL queries.

Compares a generated query against a reference by normalising both against the
schema and comparing them as graphs, so a query that is correct but written
differently is not scored wrong.
"""
try:
    # Written at build time by hatch-vcs from the git tag.
    from ._version import __version__
except ImportError:                      # running from a source tree, not installed
    __version__ = "0.0.0.dev0"

from .scoring import score_pair

__all__ = ["score_pair", "__version__"]
