import pandas as pd
import json
import os
from .compare_utils import compare_query_evaluation

def evaluate_graphql_accuracy(input_file: str, output_dir: str = "test_output_files") -> dict:
   
    os.makedirs(output_dir, exist_ok=True)

    base, ext = os.path.splitext(os.path.basename(input_file))
    output_path = os.path.join(output_dir,base,f"{base}_accuracy.json")

    compared_df = compare_query_evaluation(input_file)
    if ext == '.csv':
        actual_df = pd.read_csv(input_file).reset_index().rename(columns={'index': 'Cno'})
    else:
        actual_df = pd.read_excel(input_file).reset_index().rename(columns={'index': 'Cno'})

    final_df = pd.merge(actual_df, compared_df, on='Cno')

    if 'QueryCategoryList' not in final_df.columns:
        raise ValueError("Missing required column 'QueryCategoryList' in input file. Available columns: " + str(list(final_df.columns)))

    def parse_category_list(category_list_str):
        """Parse comma-separated category list and return a list of normalized categories."""
        if pd.isna(category_list_str) or category_list_str is None:
            return []
        

        categories_str = str(category_list_str).strip()
        if not categories_str:
            return []
        

        categories = [cat.strip() for cat in categories_str.split(',')]

        categories = [cat for cat in categories if cat]
        return categories

    final_df['category_list'] = final_df['QueryCategoryList'].apply(parse_category_list)
    

    all_categories = set()
    for category_list in final_df['category_list']:
        all_categories.update(category_list)
    

    categories = sorted(list(all_categories))
    
    if not categories:
        print("⚠️  Warning: No categories found in QueryCategoryList column. Using empty category list.")

    def calculate_category_metrics(category_name):
        """Calculate metrics for a specific category. A row is included if it contains this category."""

        category_rows = final_df[final_df['category_list'].apply(lambda cats: category_name in cats)]
        total = len(category_rows)
        
        if total == 0:
            return {
                'accuracy': 0.0,
                'correct': 0,
                'total': 0
            }
        

        correct = len(category_rows[category_rows['Equal'] == 'Equal'])
        accuracy = round((correct / total) * 100, 2) if total > 0 else 0.0
        
        return {
            'accuracy': accuracy,
            'correct': int(correct),
            'total': int(total)
        }

    metrics = {}
    for category in categories:
        metrics[category] = calculate_category_metrics(category)

    total_rows = len(final_df)
    overall_correct = len(final_df[final_df['Equal'] == 'Equal'])
    overall_accuracy = round((overall_correct / total_rows) * 100, 2) if total_rows > 0 else 0.0

    metrics['overall'] = {
        'accuracy': overall_accuracy,
        'correct': int(overall_correct),
        'total': int(total_rows)
    }

    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=4)

    print(f"✅ Accuracy evaluation saved to {output_path}")
    print(f"\n📊 Summary:")
    print(f"   Overall: {overall_accuracy}% ({overall_correct}/{total_rows})")
    for category in categories:
        cat_metrics = metrics[category]
        if cat_metrics['total'] > 0:
            print(f"   {category}: {cat_metrics['accuracy']}% ({cat_metrics['correct']}/{cat_metrics['total']})")
    
    return metrics

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m rgeval.evalExec <predictions.xlsx|.csv>")
    path = sys.argv[1]
    evaluate_graphql_accuracy(path)