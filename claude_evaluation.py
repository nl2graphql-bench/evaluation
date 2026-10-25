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

def evaluate_claude_model():
    model_name = "claude"
    logger.info(f"Starting evaluation for model: {model_name}")
    model_dir = os.path.join("emnlp_inputs", model_name)
    
    files_to_process = [
        ("test_main_predictions.jsonl", "test_main.xlsx"),
        ("test_part2_predictions.jsonl", "test_part2.xlsx")
    ]
    
    # Store results
    results = {
        "pred_claude": {}
    }
    
    def init_category(results_dict, category):
        if category not in results_dict:
            results_dict[category] = {"correct": 0, "total": 0}

    for jsonl_name, excel_name in files_to_process:
        jsonl_path = os.path.join(model_dir, jsonl_name)
        excel_path = excel_name
        
        if not os.path.exists(jsonl_path) or not os.path.exists(excel_path):
            logger.warning(f"Missing {jsonl_path} or {excel_path}. Skipping this pair.")
            continue
            
        logger.info(f"Processing {jsonl_name} with {excel_name}")
        df_excel = pd.read_excel(excel_path)
        predictions = load_jsonl(jsonl_path)
        
        # Build dictionary from excel for fast lookup
        excel_data = {}
        for _, row in df_excel.iterrows():
            schema = row.get("CleanSchema", "")
            if pd.isna(schema):
                schema = ""
            excel_data[row["DataID"]] = {
                "CleanSchema": schema,
                "GraphQLQueryVariables": row.get("GraphQLQueryVariables", ""),
                "QueryCategory": row.get("QueryCategory", "Unknown")
            }
            
        
        for pred in predictions:
            pred_id = pred.get("id")
            if pred_id not in excel_data:
                logger.warning(f"ID {pred_id} from {jsonl_name} not found in {excel_name}")
                continue
                
            meta = excel_data[pred_id]
            category = meta["QueryCategory"]
            if pd.isna(category):
                category = "Unknown"
            else:
                category = str(category).strip()
                
            init_category(results["pred_claude"], category)
            
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
                    return False
            
            # Evaluate claude
            results["pred_claude"][category]["total"] += 1
            if run_pipeline(pred.get("gold", ""), pred.get("pred_claude", ""), "claude"):
                results["pred_claude"][category]["correct"] += 1

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

    combined_results = {
        "pred_claude": format_results(results["pred_claude"])
    }
    
    output_dir = os.path.join("emnlp_outputs", model_name)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "results.json")
    
    with open(output_path, "w") as f:
        json.dump(combined_results, f, indent=4)
        
    logger.info(f"Evaluation complete for {model_name}. Results saved to {output_path}")

if __name__ == "__main__":
    evaluate_claude_model()
