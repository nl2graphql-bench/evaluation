import os
import shutil
import re
from typing import List, Set
import pandas as pd
from graphql import build_schema

ALLOWED_DIRECTIVES: Set[str] = {
    # Standard GraphQL directives we are willing to keep
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

    # Regex to find directives
    directive_pattern = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)(\s*\([^)]*\))?")

    for line in lines:
        original_line = line
        stripped = line.strip()

        # Handle triple-quoted blocks (remove them entirely)
        if '"""' in stripped:
            quote_count = stripped.count('"""')
            for _ in range(quote_count):
                in_triple_quotes = not in_triple_quotes
            continue
        if in_triple_quotes:
            continue

        # If we're inside a removed directive argument block, skip lines until we see a closing parenthesis
        if in_removed_directive_block:
            if ")" in stripped:
                in_removed_directive_block = False
            continue

        # If this line starts with a directive and it's not allowed, skip this entire block
        if stripped.startswith("@"):
            m = re.match(r"@([A-Za-z_][A-Za-z0-9_]*)", stripped)
            if m:
                name = m.group(1)
                if name not in ALLOWED_DIRECTIVES:
                    if ")" not in stripped:
                        in_removed_directive_block = True
                    continue

        # Skip obvious SQL/configuration lines
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

        # Drop dangling commas
        if stripped.startswith(","):
            continue

        # Strip unknown directives that might appear inline
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
    
    # Add missing scalar definitions if Date or DateTime is used but not defined
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

def process_new_dataset(file_path: str):
    print(f"Reading file: {file_path}")
    df = pd.read_excel(file_path)

    # Check if 'Refined_Schema' column is present
    if "Refined_Schema" not in df.columns:
        raise KeyError("Could not find 'Refined_Schema' column in the dataset.")

    # Check if 'CleanSchema' already exists. If so, drop it to prevent duplicate inserts.
    if "CleanSchema" in df.columns:
        print("Warning: 'CleanSchema' column already exists and will be overwritten.")
        df = df.drop(columns=["CleanSchema"])

    cleaned_schemas = []
    validation_errors = []

    print("Cleaning schemas and verifying compliance...")
    for idx, raw in df["Refined_Schema"].items():
        if pd.isna(raw) or not str(raw).strip():
            cleaned_schemas.append("")
            continue
            
        cleaned = clean_schema(raw)
        
        # Test compliance with graphql.build_schema
        try:
            build_schema(cleaned)
        except Exception as e:
            validation_errors.append((idx, str(e)))
            print(f"❌ Row {idx} validation failed: {e}")
            
        cleaned_schemas.append(cleaned)

    # Place CleanSchema right after the Refined_Schema column
    refined_col_idx = df.columns.get_loc("Refined_Schema")
    df.insert(refined_col_idx + 1, "CleanSchema", cleaned_schemas)

    # Assert all unique non-empty cleaned schemas compile correctly
    if validation_errors:
        print(f"\n❌ Validation check failed with {len(validation_errors)} errors.")
        print("Dataset will not be saved.")
        return False
    else:
        print("\n✅ Verification passed: All cleaned schemas are 100% GraphQL SDL-compliant!")

    # Write back to excel without modifying anything else
    backup_path = file_path + ".bak"
    shutil.copy2(file_path, backup_path)
    print(f"Backup created at: {backup_path}")

    df.to_excel(file_path, index=False)
    print(f"✅ Successfully wrote clean schemas back to {file_path}")
    
    # Remove backup upon success
    os.remove(backup_path)
    return True

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m rgeval.clean_new_dataset <dataset.xlsx>")
    target_file = sys.argv[1]
    if os.path.exists(target_file):
        process_new_dataset(target_file)
    else:
        print(f"Error: Target file not found at {target_file}")
