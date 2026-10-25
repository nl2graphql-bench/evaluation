import json
import os
from typing import List, Dict, Set
import graphql 

def simplify_filter(ast):
    """Simplify GraphQL filter arguments by extracting direct equality conditions (eq) where possible."""

    def simplify_field(field):
        """Modify field arguments to extract direct equality conditions (eq)."""
        if "arguments" not in field:
            return field

        new_args = []
        for arg in field["arguments"]:
            if arg["name"]["value"] == "filter":
                filter_value = arg["value"]
                if filter_value["kind"] == "object_value":
                    new_object_fields = []
                    for field_item in filter_value["fields"]:
                        field_name = field_item["name"]["value"]
                        field_value = field_item["value"]

                        if field_value["kind"] == "object_value":
                            eq_field = next((f for f in field_value["fields"] if f["name"]["value"] == "eq"), None)
                            if eq_field:

                                new_args.append({
                                    "kind": "argument",
                                    "name": {"kind": "name", "value": field_name},
                                    "value": eq_field["value"]
                                })
                            else:
                                new_object_fields.append(field_item)
                        else:
                            new_object_fields.append(field_item)

                    if new_object_fields:
                        new_args.append({
                            "kind": "argument",
                            "name": arg["name"],
                            "value": {"kind": "object_value", "fields": new_object_fields}
                        })
                else:
                    new_args.append(arg)
            else:
                new_args.append(arg)

        field["arguments"] = new_args
        return field

    for definition in ast["definitions"]:
        if "selection_set" in definition:
            new_selections = []
            for selection in definition["selection_set"]["selections"]:
                if selection["kind"] == "field":
                    new_selections.append(simplify_field(selection))
                else:
                    new_selections.append(selection)
            definition["selection_set"]["selections"] = new_selections

    return ast

class CircularFragmentError(ValueError):
    pass


def inline_fragments(ast: Dict, max_depth: int = 20) -> Dict:
    """Simplify fragments in queries by recursively inlining fragment spreads and flattening inline fragments."""
    definitions = ast["definitions"]

    fragment_map = {
        definition["name"]["value"]: definition["selection_set"]["selections"]
        for definition in definitions
        if definition["kind"] == "fragment_definition"
    }

    def process_selections(selections: List[Dict], current_fragments: Set[str] = None, depth: int = 0) -> List[Dict]:
        """Recursively process selections, inline fragment spreads, and flatten inline fragments."""
        current_fragments = current_fragments or set()
        processed = []
        if depth > max_depth:
            raise CircularFragmentError(f"Maximum expansion depth {max_depth} exceeded")
        for selection in selections:
            if selection["kind"] == "fragment_spread":
                fragment_name = selection["name"]["value"]
                if fragment_name in current_fragments:
                    raise CircularFragmentError(f"Circular fragment reference detected: {fragment_name}")
                if fragment_name in fragment_map:
                    new_fragments = current_fragments | {fragment_name}
                    processed.extend(process_selections(fragment_map[fragment_name], new_fragments, depth + 1))
                else:
                    print(f"Warning: Fragment definition for '{fragment_name}' not found!")
            elif selection["kind"] == "inline_fragment":

                if "selection_set" in selection and selection["selection_set"]:
                    inline_selections = process_selections(selection["selection_set"]["selections"], current_fragments, depth)
                    processed.extend(inline_selections)
            elif "selection_set" in selection and selection["selection_set"]:

                selection["selection_set"]["selections"] = process_selections(
                    selection["selection_set"]["selections"], current_fragments, depth
                )
                processed.append(selection)
            else:
                processed.append(selection)
        return processed

    new_definitions = []
    for definition in definitions:
        if definition["kind"] != "fragment_definition":
            if "selection_set" in definition and definition["selection_set"]:
                try:
                    definition["selection_set"]["selections"] = process_selections(definition["selection_set"]["selections"])
                except CircularFragmentError as e:
                    raise ValueError(f"Error in operation {definition.get('name', {}).get('value', 'unknown')}: {str(e)}") from e
            new_definitions.append(definition)
    ast["definitions"] = new_definitions
    return ast

def get_argument_value(value_node):
    """
    Recursively convert a GraphQL value node into its corresponding Python value.
    Handles scalar, object, list, and name types.
    """
    kind = value_node.get("kind")
    if kind == "object_value":

        result = {}
        for field in value_node.get("fields", []):
            field_name = field.get("name", {}).get("value")
            if field_name is not None:
                result[field_name] = get_argument_value(field.get("value"))
        return result
    elif kind in ["int_value", "float_value", "string_value", "boolean_value", "enum_value"]:
        return value_node.get("value")
    elif kind == "list_value":

        return [get_argument_value(item) for item in value_node.get("values", [])]
    elif kind == "name":
        return value_node.get("value")
    else:

        return value_node.get("value")

def further_normalize_ast(node):
    """Normalize AST structure with safe access patterns."""
    normalized = {
        "operation": node.get("operation", "query"),
        "name": (node.get("name") or {}).get("value", "query"),
        "arguments": {

            arg.get("name", {}).get("value"): get_argument_value(arg.get("value"))
            for arg in node.get("arguments", [])
        },
        "directives": []
    }
    

    if "directives" in node:
        for directive in node["directives"]:
            directive_name = directive.get("name", {}).get("value", "")
            directive_args = {}
            if "arguments" in directive:
                for arg in directive["arguments"]:
                    arg_name = arg.get("name", {}).get("value", "")
                    arg_value = get_argument_value(arg.get("value"))
                    directive_args[arg_name] = arg_value
            normalized["directives"].append({
                "name": directive_name,
                "arguments": directive_args
            })
    
    normalized["fields"] = []
    if "selection_set" in node and node["selection_set"]:
        normalized["fields"] = [
            further_normalize_ast(sel)
            for sel in node["selection_set"].get("selections", [])
        ]
    return normalized

def process_asts(query1_ast, query2_ast):
    """Process ASTs, inline fragments (including flattening inline fragments), and normalize them."""
    try:
        query1_ast_data = simplify_filter(query1_ast)
        query2_ast_data = simplify_filter(query2_ast)

        query1_ast_data = inline_fragments(query1_ast_data)
        query2_ast_data = inline_fragments(query2_ast_data)

        normalized_query1_ast = further_normalize_ast(query1_ast_data["definitions"][0])
        normalized_query2_ast = further_normalize_ast(query2_ast_data["definitions"][0])

        return normalized_query1_ast, normalized_query2_ast
    except ValueError as e:
        print(f"Error: {e}")
        return None, None

if __name__ == "__main__":
    print("normalizeAST module - use process_asts(query1_ast_dict, query2_ast_dict) for in-memory processing.")
