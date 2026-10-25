import os
import json
import logging
import pandas as pd
from datetime import datetime
from pipeline.AST import process_queries
from pipeline.normalizeAST import process_asts
from pipeline.graphNet import get_graph_dict_from_ast
from pipeline.cycles import process_graphs
import pipeline.newRed as newRed
from pipeline.compare_jsons import compare_leaf_nodes

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_jsonl(file_path):
    with open(file_path, "r") as f:
        return [json.loads(line) for line in f]

def load_json(file_path):
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {e}")
        return None

def strip_markdown(query: str) -> str:
    """Removes markdown code block backticks (e.g. ```graphql ... ```)"""
    if not isinstance(query, str):
        return ""
    lines = query.split('\n')
    cleaned_lines = []
    in_code_block = False
    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()

def evaluate_emnlp_file(input_file: str):
    logger.info(f"Starting evaluation for file: {input_file}")
    
    jsonl_path = os.path.join("every_prediction", input_file)
    if not os.path.exists(jsonl_path):
        logger.error(f"File {jsonl_path} does not exist.")
        return
    
    def init_category(results_dict, category):
        if category not in results_dict:
            results_dict[category] = {"correct": 0, "total": 0}

    # Determine the excel dataset to load
    excel_data = {}
    is_new_dataset = "test_emnlp" in input_file or "NL2GQL_Testset" in input_file
    
    if is_new_dataset:
        excel_path = "every_prediction/NL2GQL_Testset_V20.1 (1).xlsx"
        if os.path.exists(excel_path):
            df_excel = pd.read_excel(excel_path)
            for _, row in df_excel.iterrows():
                schema = row.get("CleanSchema", "")
                if pd.isna(schema):
                    schema = ""
                gt = str(row.get('GT_GQL', ''))
                
                # Categorize based on columns
                category = 'selections'
                if '@' in gt:
                    category = 'directives'
                elif row.get('mtype') == 'Yes':
                    category = 'mutations'
                elif row.get('frag') == 'Yes':
                    if 'fragment ' in gt:
                        category = 'external_fragments'
                    else:
                        category = 'inline_fragments'
                elif row.get('filter') == 'Yes':
                    category = 'filters'
                elif row.get('alias') == 'Yes':
                    category = 'aliases'
                elif any(k in gt for k in ['first:', 'last:', 'after:', 'before:']):
                    category = 'pagination'
                    
                excel_data[row["Sno"]] = {
                    "CleanSchema": schema,
                    "GraphQLQueryVariables": "{}",
                    "QueryCategory": category
                }
    else:
        # Load test_main or test_part2 depending on filename
        excel_files = []
        if "test_main" in input_file:
            excel_files = ["test_main.xlsx"]
        elif "test_part2" in input_file:
            excel_files = ["test_part2.xlsx"]
        else:
            excel_files = ["test_main.xlsx", "test_part2.xlsx"]
            
        for excel_path in excel_files:
            if os.path.exists(excel_path):
                df_excel = pd.read_excel(excel_path)
                for _, row in df_excel.iterrows():
                    schema = row.get("CleanSchema", "")
                    if pd.isna(schema):
                        schema = ""
                    excel_data[row["DataID"]] = {
                        "CleanSchema": schema,
                        "GraphQLQueryVariables": row.get("GraphQLQueryVariables", ""),
                        "QueryCategory": row.get("QueryCategory", "Unknown")
                    }
    
    logger.info(f"Processing {input_file}")
    predictions = load_jsonl(jsonl_path)
    if not predictions:
        logger.error(f"No predictions found in {jsonl_path}")
        return
        
    pred_keys = [k for k in predictions[0].keys() if k.startswith("pred_")]
    results = {k: {} for k in pred_keys}
    
    for pred in predictions:
        pred_id = pred.get("id")
        if pred_id not in excel_data:
            logger.warning(f"ID {pred_id} from {input_file} not found in excel files")
            continue
            
        meta = excel_data[pred_id]
        category = meta["QueryCategory"]
        if pd.isna(category):
            category = "Unknown"
        else:
            category = str(category).strip()
            
        for pk in pred_keys:
            init_category(results[pk], category)
        
        # Helper to run pipeline for a pair
        def run_pipeline(gold_query, pred_query, suffix):
            schema_content = str(meta["CleanSchema"])
            var_content = meta["GraphQLQueryVariables"]
            if pd.isna(var_content) or not str(var_content).strip():
                var_content = "{}"
                
            try:
                q1_ast, q2_ast = process_queries(
                    schema_content, 
                    strip_markdown(gold_query), 
                    strip_markdown(pred_query), 
                    var_content
                )
                if q1_ast is None or q2_ast is None:
                    logger.error(f"Validation error for {suffix} ID {pred_id}")
                    return False
                    
                n1_ast, n2_ast = process_asts(q1_ast, q2_ast)
                if n1_ast is None or n2_ast is None:
                    return False
                    
                graph1 = get_graph_dict_from_ast(n1_ast)
                graph2 = get_graph_dict_from_ast(n2_ast)
                if graph1 is None or graph2 is None:
                    return False
                    
                graph1_cleaned, graph2_cleaned, g1_struct, g2_struct = process_graphs(graph1, graph2)
                if graph1_cleaned is None or graph2_cleaned is None:
                    return False
                    
                if schema_content:
                    _ = newRed.optimize_queries(schema_content, g1_struct, g2_struct)
                    
                is_equal = compare_leaf_nodes(graph1_cleaned, graph2_cleaned)
                return bool(is_equal)
            except Exception as e:
                logger.error(f"Pipeline error for {suffix} ID {pred_id}: {e}")
                return False
        
        for pk in pred_keys:
            results[pk][category]["total"] += 1
            if run_pipeline(pred.get("gold", ""), pred.get(pk, ""), pk):
                results[pk][category]["correct"] += 1

    # Format the results
    def format_results(res_dict):
        final_res = {}
        overall_correct = 0
        overall_total = 0
        
        for cat, stats in res_dict.items():
            correct = stats["correct"]
            total = stats["total"]
            accuracy = (correct / total * 100) if total > 0 else 0
            final_res[cat] = {
                "correct": correct,
                "total": total,
                "accuracy_percent": round(accuracy, 2)
            }
            overall_correct += correct
            overall_total += total
            
        overall_acc = (overall_correct / overall_total * 100) if overall_total > 0 else 0
        final_res["Overall"] = {
            "correct": overall_correct,
            "total": overall_total,
            "accuracy_percent": round(overall_acc, 2)
        }
        return final_res

    combined_results = {pk: format_results(results[pk]) for pk in pred_keys}
    
    output_dir = os.path.join("review_evals", input_file)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "results.json")
    
    with open(output_path, "w") as f:
        json.dump(combined_results, f, indent=4)
        
    logger.info(f"Evaluation complete for {input_file}. Results saved to {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate EMNLP predictions")
    parser.add_argument("--input_file", type=str, required=True, help="Input file name in every_prediction")
    args = parser.parse_args()
    
    evaluate_emnlp_file(args.input_file)
