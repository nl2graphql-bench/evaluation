import json
import re
import os
import yaml
import logging
from graphql import build_schema

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)



def normalize_field_name(field_name):
    """Remove arguments from field names for comparison."""
    return re.sub(r"\(.*?\)", "", field_name)

def normalize_type(type_str):
    """
    Normalize a GraphQL type string by removing list notation and non-null markers.
    This way, 'Users', 'Users!', and '[Users]' all normalize to 'Users'.
    """
    return type_str.replace('[', '').replace(']', '').replace('!', '').strip()

def extract_query_types(schema):
    """Extract all query field names and their return types from the schema."""
    query_type = schema.get_type("Query")
    query_fields = query_type.fields
    return {normalize_field_name(field_name): str(query_fields[field_name].type)
            for field_name in query_fields}

def extract_all_field_names(graph):
    """Recursively extract all field names from a query JSON structure."""
    field_names = set()
    def traverse(node):
        normalized_name = normalize_field_name(node["name"])
        field_names.add(normalized_name)
        if "fields" in node and node["fields"]:
            for child in node["fields"]:
                traverse(child)
    for entry in graph.get("fields", []):
        traverse(entry)
    return field_names

def find_equivalent_endpoints(schema, query1_fields, query2_fields):
    """
    Find redundant endpoints in query2 that reference the same base type as an endpoint in query1.
    For example, if "users" returns Users! and "usersFilterList" returns [Users],
    both will normalize to "Users" and be considered equivalent.
    """
    query_types = extract_query_types(schema)
    replacements = {}
    for q2_endpoint in query2_fields:
        q2_type = query_types.get(q2_endpoint)
        for q1_endpoint in query1_fields:
            q1_type = query_types.get(q1_endpoint)
            if q1_type and q2_type and normalize_type(q1_type) == normalize_type(q2_type):

                replacements[q2_endpoint] = q1_endpoint
                logging.info(f"Found equivalent endpoints: {q2_endpoint} → {q1_endpoint}")
    return replacements

def replace_redundant_endpoints(graph, replacements):
    """Replace redundant fields in query2 based on schema-verified equivalence."""
    def traverse(node):
        normalized_name = normalize_field_name(node["name"])
        if normalized_name in replacements:
            logging.info(f"Replacing {node['name']} → {replacements[normalized_name]}")
            node["name"] = replacements[normalized_name]
        if "fields" in node and node["fields"]:
            for child in node["fields"]:
                traverse(child)
    for entry in graph.get("fields", []):
        traverse(entry)
    return graph



def convert_to_graph_structure(optimized_query):
    nodes = []
    links = []
    node_ids = set()

    def add_node(node_id):
        if node_id not in node_ids:
            nodes.append({"id": node_id})
            node_ids.add(node_id)

    def traverse_fields(parent, fields):
        for field in fields:
            field_name = field["name"]

            if field_name.startswith("argument:"):
                clean_name = field_name.replace("argument:", "argument_")
                clean_name = re.sub(r'_([a-zA-Z]+)\(', r':\1(', clean_name)
            elif field_name.startswith("directive:"):

                clean_name = field_name
            else:
                clean_name = re.sub(r'\(.*?\)', '', field_name)
            add_node(clean_name)
            links.append({"source": parent, "target": clean_name})
            if field.get("fields"):
                traverse_fields(clean_name, field["fields"])
    add_node("query")
    if "fields" in optimized_query:
        for top_field in optimized_query["fields"]:
            if top_field["name"] == "query":
                traverse_fields("query", top_field.get("fields", []))
    return {"nodes": nodes, "links": links}

def optimize_queries(schema_content, query1_graph, query2_graph):
    """
    Optimize Query 2 using schema validation. The optimization replaces any redundant endpoints
    (e.g., users and usersFilterList if they return equivalent base types) in the query.
    """
    if not schema_content:
        return query2_graph
        
    schema = build_schema(schema_content)
    if schema is None:
        logging.error(f"Skipping query optimization due to missing schema.")
        return query2_graph

    if query1_graph is None or query2_graph is None:
        logging.error(f"Skipping query optimization due to missing query JSON.")
        return query2_graph

    query1_fields = extract_all_field_names(query1_graph)
    query2_fields = extract_all_field_names(query2_graph)

    replacements = find_equivalent_endpoints(schema, query1_fields, query2_fields)
    if not replacements:
        logging.info("No redundant endpoints found. Returning unmodified Query 2.")
        optimized_query2 = query2_graph
    else:
        optimized_query2 = replace_redundant_endpoints(query2_graph, replacements)

    return optimized_query2
