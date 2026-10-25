import logging
from graphql import parse, build_schema, validate, TypeInfo, visit
from graphql.utilities import TypeInfoVisitor, ast_from_value
from graphql.language.visitor import Visitor
import json
import sys
import os

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)



def _inline_variables(schema, query_ast, variable_values):
    """
    Inline variable usages with concrete values from GraphQLVariables payload.
    This is done before AST normalization so comparison logic sees argument values
    rather than unresolved variable nodes.
    """
    if not variable_values:
        return query_ast

    type_info = TypeInfo(schema)

    class VariableInliner(Visitor):
        def enter_variable(self, node, key, parent, path, ancestors):

            if getattr(parent, "kind", None) == "variable_definition":
                return node

            var_name = node.name.value
            if var_name not in variable_values:
                return node

            expected_type = type_info.get_input_type()
            if expected_type is None:
                return node

            value_node = ast_from_value(variable_values[var_name], expected_type)
            if value_node is None:
                raise ValueError(
                    f"Variable '${var_name}' value cannot be coerced to expected type '{expected_type}'."
                )
            return value_node

    return visit(query_ast, TypeInfoVisitor(type_info, VariableInliner()))

def validate_and_parse_query(schema_content, query_content, variables_content=None):
    """Validate and parse a GraphQL query."""
    logging.info("Validating and parsing query...")
    schema = build_schema(schema_content)
    query_ast = parse(query_content)
    variable_values = {}
    if variables_content and str(variables_content).strip():
        parsed_variables = json.loads(variables_content)
        if not isinstance(parsed_variables, dict):
            raise ValueError("GraphQL variables payload must be a JSON object.")
        variable_values = parsed_variables

    inlined_ast = _inline_variables(schema, query_ast, variable_values)

    validation_errors = validate(schema, query_ast)
    ast_for_output = inlined_ast

    if validation_errors and variable_values:
        fallback_errors = validate(schema, inlined_ast)
        if not fallback_errors:
            validation_errors = []
        else:
            validation_errors = fallback_errors

    if validation_errors:
        logging.error("Validation errors detected:")
        for error in validation_errors:
            logging.error(f"   - {error.message}")
            logging.error("Continuing to next set of queries despite validation errors.")
        return None

    logging.info("Query successfully validated and parsed.")
    return ast_for_output.to_dict()

def normalize_aliases(node):
    """Normalize aliases in the query AST."""
    if node["kind"] == "field" and node.get("alias"):
        node["alias"] = None
    if "selection_set" in node and node["selection_set"]:
        for selection in node["selection_set"]["selections"]:
            normalize_aliases(selection)

def resolve_fragments(node, fragments):
    """Resolve fragments in the query AST."""
    if node["kind"] == "fragment_spread":

        if "value" not in node["name"]:
            logging.error(f"Missing 'value' key in fragment spread: {node}")
            raise ValueError(f"Fragment spread missing 'value' in {node}")
        
        fragment_name = node["name"]["value"]
        if fragment_name in fragments:
            return fragments[fragment_name]["selection_set"]
        else:
            logging.error(f"Fragment '{fragment_name}' not found in fragments.")
            raise ValueError(f"Fragment {fragment_name} not found.")
    elif "selection_set" in node and node["selection_set"]:
        resolved_selections = []
        for selection in node["selection_set"]["selections"]:
            if selection["kind"] == "fragment_spread":
                fragment_selections = resolve_fragments(selection, fragments)
                resolved_selections.extend(fragment_selections["selections"])
            else:
                resolved_selections.append(selection)
        node["selection_set"]["selections"] = resolved_selections
    return node



def process_queries(schema_content, query1_content, query2_content, variables_content=None):
    """Process queries and validate ASTs in memory."""
    try:
        query1_ast = validate_and_parse_query(schema_content, query1_content, variables_content)
        if query1_ast is None:
            logging.error(f"Skipping Query 1 due to validation errors.")
            return None, None
        
        query2_ast = validate_and_parse_query(schema_content, query2_content, variables_content)
        if query2_ast is None:
            logging.error(f"Skipping Query 2 due to validation errors.")
            return None, None

        return query1_ast, query2_ast

    except ValueError as e:
        logging.error(f"Error: {e}")
        return None, None
