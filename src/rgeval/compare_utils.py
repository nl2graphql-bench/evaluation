import os
import csv
import logging
from .pipeline.AST import process_queries
from .pipeline.normalizeAST import process_asts
from .pipeline.graphNet import get_graph_dict_from_ast
from .pipeline.cycles import process_graphs
from .pipeline import newRed
from .pipeline.compare_jsons import compare_leaf_nodes
from .pipeline.preProcessor import process_csv_from_preprocessed_file
import json
import pandas as pd

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def read_file_content(file_path):
    """Read and return file content as string with error handling."""
    try:
        with open(file_path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        logging.error(f"Error reading {file_path}: {e}")
        return "CONTENT_UNAVAILABLE"

def load_json(file_path):
    """ Load the JSON data from a file. """
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {e}")
        return None

def compare_query_evaluation(input_path):

    processed_files = process_csv_from_preprocessed_file(input_path)
    base, ext = os.path.splitext(os.path.basename(input_path))
    path = f"test_output_files/{base}/summary"
    os.makedirs(path, exist_ok=True)  
    summary_csv = os.path.join(path, "comparison_summary.csv")

    
    with open(summary_csv, "w", newline="") as summary_file:
        writer = csv.writer(summary_file)

        writer.writerow(["Cno", "Schema Content", "Query1 Content", "Query2 Content", "Equal", "Extra Fields", "Comments"])

        for Cno, row_dir, schema_file, query1_file, query2_file, variables_file, _ in processed_files:
            logger.info(f"\n Processing {row_dir}...")
            
            try:

                comments = ""

                schema_content = read_file_content(schema_file)
                query1_content = read_file_content(query1_file)
                query2_content = read_file_content(query2_file)
                

                variables_content = None
                if os.path.exists(variables_file):
                    variables_content = read_file_content(variables_file)

                q1_ast, q2_ast = process_queries(
                    schema_content,
                    query1_content,
                    query2_content,
                    variables_content
                )
                
                if q1_ast is None or q2_ast is None:
                    comments = f"Validation errors in queries for {row_dir}."
                    raise ValueError(comments)

                n1_ast, n2_ast = process_asts(q1_ast, q2_ast)
                if n1_ast is None or n2_ast is None:
                    comments = f"Error in AST normalization for {row_dir}."
                    raise ValueError(comments)

                graph1 = get_graph_dict_from_ast(n1_ast)
                graph2 = get_graph_dict_from_ast(n2_ast)
                if graph1 is None or graph2 is None:
                    comments = f"Error converting AST to graphs for {row_dir}."
                    raise ValueError(comments)

                graph1_cleaned, graph2_cleaned, g1_struct, g2_struct = process_graphs(graph1, graph2)
                if graph1_cleaned is None or graph2_cleaned is None:
                    comments = f"Error in cycle removal for {row_dir}."
                    raise ValueError(comments)

                if schema_content:
                    _ = newRed.optimize_queries(schema_content, g1_struct, g2_struct)

                is_equal = compare_leaf_nodes(graph1_cleaned, graph2_cleaned)

                writer.writerow([
                    Cno,
                    schema_content,
                    query1_content,
                    query2_content,
                    "Equal" if is_equal else "Unequal",
                    "N/A",
                    comments or "No Errors"
                ])

            except Exception as e:
                logger.error(f"Error processing {row_dir}: {e}")
                

                writer.writerow([
                    Cno,
                    schema_content if 'schema_content' in locals() else "N/A",
                    query1_content if 'query1_content' in locals() else "N/A",
                    query2_content if 'query2_content' in locals() else "N/A",
                    "N/A",
                    "N/A",
                    str(e)
                ])

    df_compare = pd.read_csv(summary_csv)
    logger.info(f"\n Comparison summary saved to: {summary_csv}")
    logger.info("\n All query sets processed successfully!")
    return df_compare

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m rgeval.compare_utils <predictions.csv>")
    compare_query_evaluation(sys.argv[1])