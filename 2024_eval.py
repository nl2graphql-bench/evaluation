import os
import json
import logging
import pandas as pd
import glob
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

def strip_markdown(query: str) -> str:
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

def evaluate_2024_folder(input_folder: str):
    logger.info(f"Starting 2024 evaluation for folder: {input_folder}")
    
    input_dir = os.path.join("2024_input", input_folder)
    if not os.path.exists(input_dir):
        logger.error(f"Folder {input_dir} does not exist.")
        return
        
    jsonl_files = glob.glob(os.path.join(input_dir, "*.jsonl"))
    if not jsonl_files:
        logger.error(f"No jsonl files found in {input_dir}")
        return

    excel_path = "2024_evals/NL2GQL_Testset_Clean.xlsx"
    if not os.path.exists(excel_path):
        logger.error(f"Excel file {excel_path} not found.")
        return
        
    df_excel = pd.read_excel(excel_path)
    excel_data = {}
    for _, row in df_excel.iterrows():
        schema = row.get("CleanSchema", "")
        if pd.isna(schema): schema = ""
        gt = str(row.get('GT_GQL', ''))
        
        category = 'selections'
        if '@' in gt: category = 'directives'
        elif row.get('mtype') == 'Yes': category = 'mutations'
        elif row.get('frag') == 'Yes':
            if 'fragment ' in gt: category = 'external_fragments'
            else: category = 'inline_fragments'
        elif row.get('filter') == 'Yes': category = 'filters'
        elif row.get('alias') == 'Yes': category = 'aliases'
        elif any(k in gt for k in ['first:', 'last:', 'after:', 'before:']): category = 'pagination'
            
        excel_data[row["Sno"]] = {
            "CleanSchema": schema,
            "GraphQLQueryVariables": "{}",
            "QueryCategory": category
        }

    results = {}
    
    def init_category(results_dict, category):
        if category not in results_dict:
            results_dict[category] = {"correct": 0, "total": 0}

    for jsonl_path in jsonl_files:
        logger.info(f"Processing {jsonl_path}")
        predictions = load_jsonl(jsonl_path)
        if not predictions:
            continue
            
        pred_keys = [k for k in predictions[0].keys() if k.startswith("pred_")]
        for pk in pred_keys:
            if pk not in results:
                results[pk] = {}
        
        for pred in predictions:
            pred_id = pred.get("id")
            if pred_id not in excel_data:
                logger.warning(f"ID {pred_id} not found in excel.")
                continue
                
            meta = excel_data[pred_id]
            category = meta["QueryCategory"]
            
            for pk in pred_keys:
                init_category(results[pk], category)
            
            for pk in pred_keys:
                results[pk][category]["total"] += 1
                
                schema_content = str(meta["CleanSchema"])
                var_content = meta["GraphQLQueryVariables"]
                gold_query = pred.get("gold", "")
                pred_query = pred.get(pk, "")
                
                try:
                    q1_ast, q2_ast = process_queries(
                        schema_content, strip_markdown(gold_query), strip_markdown(pred_query), var_content
                    )
                    if q1_ast is None or q2_ast is None:
                        continue
                    n1_ast, n2_ast = process_asts(q1_ast, q2_ast)
                    if n1_ast is None or n2_ast is None: continue
                    graph1 = get_graph_dict_from_ast(n1_ast)
                    graph2 = get_graph_dict_from_ast(n2_ast)
                    if graph1 is None or graph2 is None: continue
                    graph1_cleaned, graph2_cleaned, g1_struct, g2_struct = process_graphs(graph1, graph2)
                    if graph1_cleaned is None or graph2_cleaned is None: continue
                    if schema_content:
                        _ = newRed.optimize_queries(schema_content, g1_struct, g2_struct)
                    
                    is_equal = compare_leaf_nodes(graph1_cleaned, graph2_cleaned)
                    if is_equal:
                        results[pk][category]["correct"] += 1
                except Exception as e:
                    logger.error(f"Pipeline error for {pk} ID {pred_id}: {e}")

    def format_results(res_dict):
        final_res = {}
        overall_correct = 0
        overall_total = 0
        for cat, stats in res_dict.items():
            correct = stats["correct"]
            total = stats["total"]
            accuracy = (correct / total * 100) if total > 0 else 0
            final_res[cat] = {
                "correct": correct, "total": total, "accuracy_percent": round(accuracy, 2)
            }
            overall_correct += correct
            overall_total += total
        overall_acc = (overall_correct / overall_total * 100) if overall_total > 0 else 0
        final_res["Overall"] = {
            "correct": overall_correct, "total": overall_total, "accuracy_percent": round(overall_acc, 2)
        }
        return final_res

    combined_results = {pk: format_results(results[pk]) for pk in results.keys()}
    
    output_dir = os.path.join("2024_results", input_folder)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "results.json")
    
    with open(output_path, "w") as f:
        json.dump(combined_results, f, indent=4)
        
    logger.info(f"Evaluation complete. Results saved to {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate 2024 predictions")
    parser.add_argument("--input_folder", type=str, required=True, help="Folder name inside 2024_input")
    args = parser.parse_args()
    evaluate_2024_folder(args.input_folder)
