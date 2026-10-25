import json
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)


    
def detect_cycles(graph):
    """Detect cycles in the directed graph using DFS."""
    edges = graph["links"]
    adjacency_list = {}

    for edge in edges:
        source, target = edge["source"], edge["target"]
        if source not in adjacency_list:
            adjacency_list[source] = []
        adjacency_list[source].append(target)

    visited = set()
    stack = set()
    cycles = []

    def dfs(node, path):
        """Depth-First Search to detect cycles."""
        if node in stack:
            cycle_index = path.index(node)
            cycles.append(path[cycle_index:])
            logging.debug(f" Detected cycle: {path[cycle_index:]}")
            return

        if node in visited:
            return

        visited.add(node)
        stack.add(node)

        for neighbor in adjacency_list.get(node, []):
            dfs(neighbor, path + [neighbor])

        stack.remove(node)

    for node in adjacency_list:
        if node not in visited:
            dfs(node, [node])

    logging.info(f" Detected cycles: {len(cycles)} cycle(s) found.")
    return cycles

def _cycle_edges(cycles):
    """Convert cycle node lists into edge pairs."""
    edges = set()
    for cycle in cycles:
        if not cycle or len(cycle) < 2:
            continue
        for i in range(len(cycle) - 1):
            edges.add((cycle[i], cycle[i + 1]))
        if cycle[0] != cycle[-1]:
            edges.add((cycle[-1], cycle[0]))
    return edges

def _cycle_edge_list(cycle):
    edges = []
    if not cycle or len(cycle) < 2:
        return edges
    for i in range(len(cycle) - 1):
        edges.append((cycle[i], cycle[i + 1]))
    if cycle[0] != cycle[-1]:
        edges.append((cycle[-1], cycle[0]))
    return edges

def prune_cycles(graph):
    """Remove cycles by breaking all detected cycles."""
    removed_edges = []

    while True:
        cycles = detect_cycles(graph)
        if not cycles:
            break

        to_remove = set()
        for cycle in cycles:
            edges = _cycle_edge_list(cycle)
            if edges:
                to_remove.add(sorted(edges)[0])

        if not to_remove:
            break

        filtered_edges = []
        for edge in graph["links"]:
            edge_pair = (edge["source"], edge["target"])
            if edge_pair in to_remove:
                removed_edges.append(edge)
                continue
            filtered_edges.append(edge)

        graph["links"] = filtered_edges

    logging.info(f" Removed {len(removed_edges)} edges to break cycles.")
    return graph, removed_edges

def build_hierarchical_structure(graph):
    """Convert graph into a nested GraphQL-style structure."""
    node_map = {node["id"]: {"name": node["id"], "fields": []} for node in graph["nodes"]}

    for edge in graph["links"]:
        source, target = edge["source"], edge["target"]
        if "fields" not in node_map[source]:
            node_map[source]["fields"] = []
        node_map[source]["fields"].append(node_map[target])

    all_targets = {edge["target"] for edge in graph["links"]}
    root_nodes = [node_map[node["id"]] for node in graph["nodes"] if node["id"] not in all_targets]

    return {"name": "MyQuery", "fields": root_nodes}

def remove_cycles(graph1, graph2):
    """Detect and remove cycles in both graphs."""
    acyclic_graph1, removed_edges1 = prune_cycles(graph1)
    acyclic_graph2, removed_edges2 = prune_cycles(graph2)
    return acyclic_graph1, acyclic_graph2, removed_edges1, removed_edges2

def process_graphs(graph1, graph2):
    """Process both graphs to remove schema-redundant cycles and return cleaned versions."""
    if graph1 is None or graph2 is None:
        logging.error(" Error: One of the graphs is None.")
        return None, None, None, None

    graph1_cleaned, graph2_cleaned, removed_edges1, removed_edges2 = remove_cycles(
        graph1, graph2
    )

    graph1_structured = build_hierarchical_structure(graph1_cleaned)
    graph2_structured = build_hierarchical_structure(graph2_cleaned)

    return graph1_cleaned, graph2_cleaned, graph1_structured, graph2_structured
