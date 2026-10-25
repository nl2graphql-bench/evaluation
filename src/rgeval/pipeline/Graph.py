import json
import networkx as nx
import matplotlib.pyplot as plt
import os
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)


def _stable_arg_value(arg_value):
    try:
        return json.dumps(arg_value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except TypeError:
        return str(arg_value)

def ast_to_graph_json(ast):
    """ Convert the normalized AST into a graph structure with arguments and directives as separate nodes. """
    def build_graph(node):
        logging.debug(f"Processing node: {node['name']}")
        graph_node = {
            "name": node["name"]
        }

        if "arguments" in node:
            graph_node["arguments"] = {}
            for arg_name, arg_value in node["arguments"].items():
                logging.debug(f"Adding argument: {arg_name} = {arg_value} for node: {node['name']}")

                argument_node_name = f"argument:{arg_name}({_stable_arg_value(arg_value)})"
                graph_node["arguments"][arg_name] = {
                    "name": argument_node_name,
                    "value": arg_value
                }
        

        if "directives" in node and node["directives"]:
            graph_node["directives"] = {}
            for directive in node["directives"]:
                directive_name = directive.get("name", "")
                directive_args = directive.get("arguments", {})

                args_str = ",".join([f"{k}:{v}" for k, v in directive_args.items()])
                directive_node_name = f"directive:{directive_name}({args_str})"
                graph_node["directives"][directive_name] = {
                    "name": directive_node_name,
                    "arguments": directive_args
                }

        if "fields" in node:
            graph_node["children"] = [build_graph(child) for child in node["fields"]]
        
        logging.debug(f"Finished processing node: {node['name']}")
        return graph_node

    logging.info(f"Starting AST to graph conversion for: {ast['name']}")
    graph = build_graph(ast)
    logging.info(f"AST to graph conversion completed for: {ast['name']}")
    return graph

def process_normalized_asts(normalized_query1_ast, normalized_query2_ast):
    """Processes ASTs and converts them into graphs."""
    try:
        graph1 = ast_to_graph_json(normalized_query1_ast)
        graph2 = ast_to_graph_json(normalized_query2_ast)
        return graph1, graph2
    except ValueError as e:
        logging.error(f"Error processing normalized ASTs: {e}")
        return None, None
