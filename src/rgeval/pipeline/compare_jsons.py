import json

def load_json(file_path):
    """Load the JSON data from a file."""
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading file {file_path}: {e}")
        return None

def create_adjacency_matrix(graph):
    """Create an adjacency matrix from a graph JSON, ensuring consistent node order."""
    nodes = graph.get('nodes', [])
    links = graph.get('links', [])

    nodes.sort(key=lambda x: x['id'])

    node_to_index = {node['id']: idx for idx, node in enumerate(nodes)}
    
    adj_matrix = [[0 for _ in range(len(nodes))] for _ in range(len(nodes))]

    for link in links:
        source_idx = node_to_index.get(link['source'])
        target_idx = node_to_index.get(link['target'])
        
        if source_idx is not None and target_idx is not None:
            adj_matrix[source_idx][target_idx] = 1

    return adj_matrix

def transitive_closure_from_node(adj_matrix, start_node_idx):
    """Compute the transitive closure from a given start node using Floyd-Warshall algorithm."""
    n = len(adj_matrix)

    transitive_closure = [row[:] for row in adj_matrix]

    for k in range(n):
        for i in range(n):
            for j in range(n):
                if transitive_closure[i][k] and transitive_closure[k][j]:
                    transitive_closure[i][j] = 1

    return transitive_closure

def compare_transitive_closures(graph1, graph2, start_node="query"):
    """Compare the transitive closures of two graphs starting from the 'start_node'."""

    matrix1 = create_adjacency_matrix(graph1)
    matrix2 = create_adjacency_matrix(graph2)

    node_list1 = sorted([node['id'] for node in graph1['nodes']])
    node_list2 = sorted([node['id'] for node in graph2['nodes']])

    if start_node not in node_list1 or start_node not in node_list2:
        print(f"Error: '{start_node}' node not found in one or both graphs.")
        return False

    start_node_idx1 = node_list1.index(start_node)
    start_node_idx2 = node_list2.index(start_node)

    tc1 = transitive_closure_from_node(matrix1, start_node_idx1)
    tc2 = transitive_closure_from_node(matrix2, start_node_idx2)

    reachable1 = {node_list1[i] for i in range(len(node_list1)) if tc1[start_node_idx1][i]}
    reachable2 = {node_list2[i] for i in range(len(node_list2)) if tc2[start_node_idx2][i]}

    return reachable1 == reachable2

def _extract_node_ids(nodes):
    ids = set()
    for node in nodes:
        if isinstance(node, dict):
            node_id = node.get("id") or node.get("name")
            if node_id is not None:
                ids.add(node_id)
        else:
            ids.add(node)
    return ids

def leaf_nodes(graph):
    """Return leaf node IDs (no outgoing edges) from a graph JSON."""
    nodes = _extract_node_ids(graph.get("nodes", []))
    sources = set()
    for link in graph.get("links", []):
        if isinstance(link, dict):
            source = link.get("source")
        else:
            source = link[0] if link else None
        if source is not None:
            sources.add(source)
    leaves = nodes - sources
    leaves.discard("query")
    return leaves

def compare_leaf_nodes(graph1, graph2):
    """Compare two graphs by their leaf node sets."""
    return leaf_nodes(graph1) == leaf_nodes(graph2)
