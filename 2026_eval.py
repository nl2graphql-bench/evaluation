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

def evaluate_2026_folder(input_folder: str):
    logger.info(f"Starting 2026 evaluation for folder: {input_folder}")
    
    input_dir = os.path.join("2026_input", input_folder)
    if not os.path.exists(input_dir):
        logger.error(f"Folder {input_dir} does not exist.")
        return
        
    jsonl_files = glob.glob(os.path.join(input_dir, "*.jsonl"))
    if not jsonl_files:
        logger.error(f"No jsonl files found in {input_dir}")
        return

    # Gold metadata is keyed by (split, DataID), NOT DataID alone: test_main uses
    # DataID 1..1845 and test_part2 uses 1..4558, so all 1845 test_main ids collide
    # with a part2 id. A single flat dict let whichever file glob() returned last win
    # for those ids, scoring test_main rows against part2 schemas, and glob() order is
    # filesystem-dependent so the result was not reproducible across machines.
    SPLIT_OF_XLSX = {"test_main": "test_main", "test_part2": "test_part2"}

    def split_of_xlsx(path):
        """test_main_clean.xlsx / test_part2_clean_backup.xlsx -> test_main / test_part2."""
        name = os.path.basename(path)
        for stem, split in SPLIT_OF_XLSX.items():
            if name.startswith(stem):
                return split
        return None

    def split_of_pred(path):
        """<split>_predictions.jsonl -> <split> (the harvest naming convention)."""
        name = os.path.basename(path)
        for stem, split in SPLIT_OF_XLSX.items():
            if name.startswith(stem):
                return split
        return None

    # Prefer the CLEAN testset for each split. The 2026_evals README asks users to add
    # the clean xlsx to this folder, which leaves the pre-clean file beside it; the clean
    # gold is the authoritative one (it makes every gold query validate against its
    # schema, where the pre-clean gold failed on 438/1845 test_main and 763/4558 part2).
    def rank(path):
        name = os.path.basename(path)
        if "_clean_backup" in name:
            return 0          # a backup of the PRE-clean file, lowest priority
        if "_clean" in name:
            return 2          # the authoritative clean gold
        return 1              # the original

    excel_data = {}
    chosen = {}
    for excel_path in sorted(glob.glob("2026_evals/*.xlsx")):
        split = split_of_xlsx(excel_path)
        if split is None:
            logger.warning(f"Skipping {excel_path}: cannot tell which split it holds.")
            continue
        if split in chosen and rank(chosen[split]) >= rank(excel_path):
            continue
        chosen[split] = excel_path
    for split, excel_path in sorted(chosen.items()):
        logger.info(f"Gold for {split}: {excel_path}")
        df_excel = pd.read_excel(excel_path)
        for _, row in df_excel.iterrows():
            schema = row.get("CleanSchema", "")
            if pd.isna(schema): schema = ""
            excel_data[(split, row["DataID"])] = {
                "CleanSchema": schema,
                "GraphQLQueryVariables": row.get("GraphQLQueryVariables", ""),
                "QueryCategory": row.get("QueryCategory", "Unknown")
            }
    if not excel_data:
        logger.error("No usable testset xlsx in 2026_evals/. See 2026_evals/README.md.")
        return

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
        
        pred_split = split_of_pred(jsonl_path)
        if pred_split is None:
            logger.error(f"Skipping {jsonl_path}: name must start with "
                         f"{' or '.join(sorted(SPLIT_OF_XLSX))} so its split is known.")
            continue

        for pred in predictions:
            pred_id = pred.get("id")
            if (pred_split, pred_id) not in excel_data:
                logger.warning(f"ID {pred_id} not found in {pred_split} gold.")
                continue

            meta = excel_data[(pred_split, pred_id)]
            category = meta["QueryCategory"]
            if pd.isna(category): category = "Unknown"
            else: category = str(category).strip()
            
            for pk in pred_keys:
                init_category(results[pk], category)
            
            for pk in pred_keys:
                results[pk][category]["total"] += 1
                
                schema_content = str(meta["CleanSchema"])
                var_content = meta["GraphQLQueryVariables"]
                if pd.isna(var_content) or not str(var_content).strip():
                    var_content = "{}"
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
    
    output_dir = os.path.join("2026_results", input_folder)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "results.json")
    
    with open(output_path, "w") as f:
        json.dump(combined_results, f, indent=4)
        
    logger.info(f"Evaluation complete. Results saved to {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate 2026 predictions")
    parser.add_argument("--input_folder", type=str, required=True, help="Folder name inside 2026_input")
    args = parser.parse_args()
    evaluate_2026_folder(args.input_folder)
