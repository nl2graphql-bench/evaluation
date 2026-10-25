import os
import shutil
import sys
import re
from typing import List, Set

import pandas as pd
from graphql import build_schema


ALLOWED_DIRECTIVES: Set[str] = {
    "deprecated",
    "include",
    "skip",
    "specifiedBy",
}


def clean_schema(raw: str) -> str:
    """
    Take a raw SDL-ish string (which may contain directives, SQL, and junk)
    and return a GraphQL SDL-compliant schema string that can be passed to
    graphql.build_schema.
    """
    if pd.isna(raw) or raw is None:
        return ""

    text = str(raw)
    if not text.strip():
        return ""

    lines: List[str] = text.splitlines()
    cleaned_lines: List[str] = []

    in_triple_quotes = False
    in_removed_directive_block = False

    directive_pattern = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)(\s*\([^)]*\))?")

    for line in lines:
        original_line = line
        stripped = line.strip()

        if '"""' in stripped:
            quote_count = stripped.count('"""')
            for _ in range(quote_count):
                in_triple_quotes = not in_triple_quotes
            continue
        if in_triple_quotes:
            continue

        if in_removed_directive_block:
            if ")" in stripped:
                in_removed_directive_block = False
            continue

        if stripped.startswith("@"):
            m = re.match(r"@([A-Za-z_][A-Za-z0-9_]*)", stripped)
            if m:
                name = m.group(1)
                if name not in ALLOWED_DIRECTIVES:
                    if ")" not in stripped:
                        in_removed_directive_block = True
                    continue

        lower = stripped.lower()
        sql_keywords = (
            "select ",
            "update ",
            "insert ",
            "delete ",
            " from ",
            " where ",
            " returning ",
            " limit ",
            " offset ",
            " coalesce(",
        )
        config_keywords = (
            "configuration:",
            "schema:",
            "table:",
            "dml:",
            "query:",
        )
        if any(k in lower for k in sql_keywords) or any(
            k in lower for k in config_keywords
        ):
            continue

        if stripped.startswith(","):
            continue

        def _strip_directive(match: re.Match) -> str:
            name = match.group(1)
            if name in ALLOWED_DIRECTIVES:
                return match.group(0)
            return ""

        line = directive_pattern.sub(_strip_directive, original_line)
        line = re.sub(r'^Scalar\s+', 'scalar ', line, flags=re.IGNORECASE)

        if not line.strip():
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    
    has_date_scalar = re.search(r'scalar\s+Date\b', cleaned, re.IGNORECASE)
    has_datetime_scalar = re.search(r'scalar\s+DateTime\b', cleaned, re.IGNORECASE)
    
    uses_date = re.search(r'\bDate\b(?!Time)', cleaned) and not has_date_scalar
    uses_datetime = re.search(r'\bDateTime\b', cleaned) and not has_datetime_scalar
    
    scalar_definitions = []
    if uses_date:
        scalar_definitions.append("scalar Date")
    if uses_datetime:
        scalar_definitions.append("scalar DateTime")
    
    if scalar_definitions:
        cleaned = "\n".join(scalar_definitions) + "\n\n" + cleaned
    
    return cleaned

def load_schema_from_file(schema_name: str, schemas_dir: str) -> str:
    schema_folder = os.path.join(schemas_dir, schema_name)
    schema_file = os.path.join(schema_folder, "index.graphql")
    
    if os.path.isfile(schema_file):
        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return ""
    else:
        return ""

def replace_refined_schemas_with_index_files(df: pd.DataFrame, schemas_dir: str) -> pd.DataFrame:
    if "GraphQLSchemaName" not in df.columns:
        raise KeyError("GraphQLSchemaName not found")
    
    schema_cache = {}
    
    for idx, row in df.iterrows():
        schema_name = row.get('GraphQLSchemaName')
        if pd.isna(schema_name) or not str(schema_name).strip():
            continue
        
        schema_name_str = str(schema_name).strip()
        if schema_name_str not in schema_cache:
            schema_content = load_schema_from_file(schema_name_str, schemas_dir)
            if schema_content:
                schema_cache[schema_name_str] = schema_content
        
        if schema_name_str in schema_cache:
            df.at[idx, 'RefinedGraphQLSchema'] = schema_cache[schema_name_str]
    
    return df

def process_file(input_path: str, schemas_dir: str):
    df = pd.read_excel(input_path)

    df = replace_refined_schemas_with_index_files(df, schemas_dir)
    
    if "RefinedGraphQLSchema" not in df.columns:
        raise KeyError("RefinedGraphQLSchema not found in dataframe")
        
    cleaned_schemas = []
    validation_errors = []
    
    for idx, raw in df["RefinedGraphQLSchema"].items():
        cleaned = clean_schema(raw)
        try:
            if cleaned:
                build_schema(cleaned)
        except Exception as e:
            validation_errors.append((idx, str(e)))
        cleaned_schemas.append(cleaned)
        
    print(f"Total rows processed: {len(cleaned_schemas)}")
    print(f"Validation errors: {len(validation_errors)}")
    if validation_errors:
        print("First 10 errors:", validation_errors[:10])

    if "CleanSchema" in df.columns:
        df = df.drop(columns=["CleanSchema"])

    refined_col_idx = df.columns.get_loc("RefinedGraphQLSchema")
    df.insert(refined_col_idx + 1, "CleanSchema", cleaned_schemas)
    
    df.to_excel(input_path, index=False)
    print("Done writing back to excel.")

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Add a CleanSchema column to a dataset xlsx, in place.")
    ap.add_argument("input", help="dataset .xlsx to rewrite")
    ap.add_argument("--schemas-dir", required=True,
                    help="directory of <schema_name>/index.graphql files, used to "
                         "replace RefinedGraphQLSchema with the untruncated SDL")
    args = ap.parse_args()
    process_file(args.input, args.schemas_dir)
