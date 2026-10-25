import json
import networkx as nx
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

def load_normalized_ast(input_file):
    """ Load a normalized AST from a JSON file. """
    try:
        logger.debug(f"Loading AST from file: {input_file}")
        with open(input_file, "r") as file:
            ast = json.load(file)
        logger.info(f"Successfully loaded AST from {input_file}")
        return ast
    except Exception as e:
        logger.error(f"Error loading normalized AST from {input_file}: {e}")
        raise ValueError(f"Error loading normalized AST from {input_file}: {e}")

def _stable_arg_value(arg_value):
    try:
        return json.dumps(arg_value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except TypeError:
        return str(arg_value)

def build_graph_from_ast(ast):
    """ Build a graph from a given AST where fields and arguments are separate nodes. """
    G = nx.DiGraph()

    def add_node_and_edges(parent_node, node):

        G.add_node(node['name'])
        if parent_node:
            G.add_edge(parent_node, node['name'])

        if 'arguments' in node:
            for arg_name, arg_value in node['arguments'].items():
                arg_node_name = f"argument:{arg_name}({_stable_arg_value(arg_value)})"
                G.add_node(arg_node_name)
                G.add_edge(node['name'], arg_node_name)
        

        if 'directives' in node and node['directives']:

            for directive in node['directives']:
                directive_name = directive.get('name', '')
                directive_args = directive.get('arguments', {})
                args_str = ",".join([f"{k}:{v}" for k, v in directive_args.items()])
                directive_node_name = f"directive:{directive_name}({args_str})"
                G.add_node(directive_node_name)
                G.add_edge(node['name'], directive_node_name)

        if 'fields' in node:
            for field in node['fields']:
                add_node_and_edges(node['name'], field)

    if 'operation' in ast:
        G.add_node(ast['name'])
        add_node_and_edges(None, ast)

    logger.debug("Graph construction completed.")
    return G

def save_graph_to_json(G, output_file):
    """ Save the graph to a JSON file. """
    try:
        graph_data = nx.readwrite.json_graph.node_link_data(G)
        with open(output_file, "w") as file:
            json.dump(graph_data, file, indent=2)
        logger.info(f"Graph saved to {output_file}")
    except Exception as e:
        logger.error(f"Error saving graph to {output_file}: {e}")

def visualize_graph(G, output_image):
    """ Visualize the graph and save it to an image. """
    try:
        logger.debug(f"Visualizing graph and saving to {output_image}")
        plt.figure(figsize=(10, 8))
        pos = nx.spring_layout(G, seed=42)
        nx.draw(G, pos, with_labels=True, node_size=3000, node_color="skyblue", font_size=12, font_weight="bold", width=2, edge_color="gray")
        plt.title("Graph Visualization of AST")
        plt.savefig(output_image, format="PNG", bbox_inches="tight")
        plt.close()
        logger.info(f"Graph saved to {output_image}")
    except Exception as e:
        logger.error(f"Error visualizing graph and saving to {output_image}: {e}")

def get_graph_dict_from_ast(ast):
    """ Build graph from AST and return the networkx node_link_data dict in memory. """
    try:
        G = build_graph_from_ast(ast)
        return nx.readwrite.json_graph.node_link_data(G)
    except Exception as e:
        logger.error(f"Error building graph dict: {e}")
        return None

