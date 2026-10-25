from collections import defaultdict, deque
import re
from graphql import build_schema, print_schema
import pandas as pd
import logging
import os
import yaml
import os
from datetime import datetime

def setup_logger(log_file):
    """Set up the logger with a specific log file."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    

    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    

    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    return logger

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def balance_brackets(text):
    if pd.isnull(text):
        return text
    

    balance = 0
    in_string = False
    in_comment = False
    escape = False
    stack = []
    last_char = ''
    
    for char in text:
        if escape:
            escape = False
            continue
        
        if char == '\\':
            escape = True
            continue
            
        if in_comment:
            if char == '\n':
                in_comment = False
            continue
            
        if in_string:
            if char == '"' and last_char != '\\':
                in_string = False
            continue
            
        if char == '"':
            in_string = True
        elif char == '#':
            in_comment = True
        elif char == '{':
            balance += 1
            stack.append(char)
        elif char == '}':
            if balance > 0:
                balance -= 1
                if stack:
                    stack.pop()
            else:

                continue
                
        last_char = char
    

    if balance > 0:
        text += '\n' + '}' * balance
    
    return text

def extract_graphql_blocks(text):
    if pd.isnull(text):
        return None
    
    def find_balanced_braces(text, start_pos):
        """Find the position of the matching closing brace."""
        depth = 0
        i = start_pos
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return -1
    

    operation_pattern = r"\b(query|mutation|subscription)\b\s*(?:\w+\s*)?(?:\([^)]*\))?\s*\{"
    match = re.search(operation_pattern, text, re.IGNORECASE)
    
    result_parts = []
    
    if match:
        start_pos = match.end() - 1
        end_pos = find_balanced_braces(text, start_pos)
        if end_pos != -1:
            operation_text = text[match.start():end_pos + 1]
            result_parts.append(operation_text)

            remaining_text = text[end_pos + 1:].strip()

            fragment_pattern = r"fragment\s+\w+\s+on\s+\w+\s*\{"
            fragment_match = re.search(fragment_pattern, remaining_text, re.IGNORECASE)
            while fragment_match:
                frag_start = fragment_match.start()
                frag_brace_pos = remaining_text.find('{', fragment_match.end() - 1)
                if frag_brace_pos != -1:
                    frag_end = find_balanced_braces(remaining_text, frag_brace_pos)
                    if frag_end != -1:
                        fragment_text = remaining_text[frag_start:frag_end + 1]
                        result_parts.append(fragment_text)
                        remaining_text = remaining_text[frag_end + 1:].strip()
                        fragment_match = re.search(fragment_pattern, remaining_text, re.IGNORECASE)
                    else:
                        break
                else:
                    break
            
            if result_parts:
                return ' '.join(result_parts)
    

    field_pattern = r"(\w+\s*(?:\([^)]*\))?\s*\{)"
    match = re.search(field_pattern, text)
    if match:
        start_pos = match.end() - 1
        end_pos = find_balanced_braces(text, start_pos)
        if end_pos != -1:
            field_block = text[match.start():end_pos + 1]
            return f"query {{\n{field_block}\n}}"
    
    return None

def strip_operation_name(query):
    if pd.isnull(query):
        return query

    return re.sub(
        r'\b(query|mutation|subscription)\b\s+\w+\s*(?:\([^)]*\))?\s*{',
        r'\1 {',
        query,
        flags=re.IGNORECASE
    )

def reorder_schema(schema: str) -> str:
    if pd.isnull(schema):
        return schema
        

    schema = balance_brackets(schema)
    
    blocks = []
    current_block = []
    for line in schema.split('\n'):
        stripped = line.strip()
        if not stripped:
            if current_block:
                blocks.append('\n'.join(current_block))
            current_block = []
            continue
        if stripped.startswith(('type ', 'interface ', 'input ', 'extend type ')):
            if current_block:
                blocks.append('\n'.join(current_block))
            current_block = [line]
        else:
            current_block.append(line)
    if current_block:
        blocks.append('\n'.join(current_block))

    scalar_types = {'String', 'Int', 'Float', 'Boolean', 'ID'}
    type_info = {}
    base_blocks = {}
    for block in blocks:
        if not block.startswith(('type ', 'interface ', 'input ')):
            continue
        lines = block.split('\n')
        first_line = lines[0].strip()
        type_kw = first_line.split()[0]
        name = first_line.split('{', 1)[0].split()[-1]
        dependencies = []
        if type_kw == 'type' and 'implements' in first_line:
            implements_part = first_line.split('implements', 1)[1].split('{', 1)[0]
            dependencies.extend([i.strip() for i in implements_part.split('&')])
        for line in lines[1:]:
            line = line.strip().rstrip('}')
            if not line or ':' not in line:
                continue
            field_type = line.split(':', 1)[1].strip()
            field_type = field_type.split('!')[0].split('[')[0].split(']')[-1]
            if field_type not in scalar_types:
                dependencies.append(field_type)
        type_info[name] = list(set(dependencies))
        base_blocks[name] = block

    adj = defaultdict(list)
    in_degree = defaultdict(int)
    all_types = set(type_info.keys())
    for name, deps in type_info.items():
        for dep in deps:
            if dep in all_types:
                adj[dep].append(name)
                in_degree[name] += 1
    queue = deque([t for t in all_types if in_degree[t] == 0])
    sorted_types = []
    while queue:
        node = queue.popleft()
        sorted_types.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    sorted_types += [t for t in all_types if t not in sorted_types]

    extensions = defaultdict(list)
    other_blocks = []
    for block in blocks:
        if block.startswith('extend type '):
            type_name = block.split('{', 1)[0].split()[-1]
            extensions[type_name].append(block)
        elif block not in base_blocks.values():
            other_blocks.append(block)

    ordered_schema = []
    seen_types = set()
    for t in sorted_types:
        if t in base_blocks:
            ordered_schema.append(base_blocks[t])
            seen_types.add(t)
        if t in extensions:
            ordered_schema.extend(extensions[t])

    for type_name, ext_blocks in extensions.items():
        if type_name not in seen_types:
            ordered_schema.extend(ext_blocks)
    for block in other_blocks:
        if block not in ordered_schema:
            ordered_schema.append(block)
    return '\n\n'.join(ordered_schema)

def preprocess_stepzen_schema(schema: str) -> str:
    if pd.isnull(schema):
        return schema
        
    stepzen_scalars = {
        'Date': 'scalar Date',
        'DateTime': 'scalar DateTime',
        'JSON': 'scalar JSON',
        'Secret': 'scalar Secret'
    }
    scalar_pattern = r'\b(Date|DateTime|JSON|Secret)\b'
    used_scalars = set(re.findall(scalar_pattern, schema))
    existing_scalars = set(re.findall(r'^scalar\s+(\w+)', schema, re.MULTILINE))
    missing_definitions = [
        stepzen_scalars[s] for s in used_scalars
        if s in stepzen_scalars and s not in existing_scalars
    ]
    cleaned_schema = re.sub(r'@\w+\(.*?\)', '', schema)
    cleaned_schema = re.sub(r'\n{3,}', '\n\n', cleaned_schema).strip()
    if missing_definitions:
        return '\n'.join(missing_definitions) + '\n\n' + cleaned_schema
    return cleaned_schema

def update_schema(schema_str: str) -> str:
    if pd.isnull(schema_str):
        return schema_str
        
    try:
        import re
        

        extend_map = {}

        i = 0
        while i < len(schema_str):
            extend_match = re.search(r'extend\s+type\s+(\w+)\s*\{', schema_str[i:], re.IGNORECASE)
            if not extend_match:
                break
            
            start = i + extend_match.start()
            type_name = extend_match.group(1)
            brace_start = i + extend_match.end() - 1
            

            brace_count = 1
            j = brace_start + 1
            while j < len(schema_str) and brace_count > 0:
                if schema_str[j] == '{':
                    brace_count += 1
                elif schema_str[j] == '}':
                    brace_count -= 1
                j += 1
            
            if brace_count == 0:
                extend_content = schema_str[brace_start+1:j-1].strip()
                if type_name not in extend_map:
                    extend_map[type_name] = []
                extend_map[type_name].append(extend_content)
                i = j
            else:
                break
        

        schema = build_schema(schema_str)
        

        for type_name, type_def in schema.type_map.items():
            if hasattr(type_def, 'interfaces'):
                for interface in type_def.interfaces:
                    for field_name, field_def in interface.fields.items():
                        if field_name not in type_def.fields:
                            type_def.fields[field_name] = field_def
        

        printed = print_schema(schema)
        

        if extend_map:
            for type_name, field_contents in extend_map.items():
                if type_name in schema.type_map:

                    type_pattern = rf'(type\s+{re.escape(type_name)}\s+(?:implements\s+[^{{]+)?\{{)([^}}]*?)(\}})'
                    type_match = re.search(type_pattern, printed, re.IGNORECASE | re.DOTALL)
                    if not type_match:

                        type_pattern = rf'(type\s+{re.escape(type_name)}\s+\{{)([^}}]*?)(\}})'
                        type_match = re.search(type_pattern, printed, re.IGNORECASE | re.DOTALL)
                    if type_match:
                        type_start = type_match.group(1)
                        type_fields = type_match.group(2)
                        type_end = type_match.group(3)
                        

                        extend_field_lines = []

                        existing_fields = set()
                        for line in type_fields.split('\n'):
                            line = line.strip()
                            if ':' in line:
                                field_name = line.split(':', 1)[0].strip()
                                if field_name:
                                    existing_fields.add(field_name)
                        
                        for field_content in field_contents:
                            for line in field_content.split('\n'):
                                line = line.strip()
                                if line and ':' in line and not line.startswith('#'):
                                    field_name = line.split(':', 1)[0].strip()

                                    if field_name and field_name not in existing_fields:
                                        extend_field_lines.append(line)
                                        existing_fields.add(field_name)
                        
                        if extend_field_lines:

                            fields_to_add = '\n  '.join(extend_field_lines)
                            if type_fields.strip():
                                new_fields = type_fields.rstrip() + '\n  ' + fields_to_add
                            else:
                                new_fields = fields_to_add
                            replacement = type_start + '\n  ' + new_fields + '\n' + type_end
                            printed = printed.replace(type_match.group(0), replacement, 1)
        
        return printed
    except Exception as e:
        logger.warning(f"Error in update_schema: {e}")
        return schema_str

def preProcess(schema):
    if pd.isnull(schema):
        return schema
        
    try:
        logger.info("Starting schema processing...")
        schema1 = balance_brackets(schema)
        schema2 = reorder_schema(schema1)
        logger.info("Schema reordered..")
        schema3 = preprocess_stepzen_schema(schema2)
        logger.info("scalar preprocessing done")
        schema4 = update_schema(schema3)
        logger.info("interface merging done")
        return schema4
    except Exception as e:
        logger.warning(f"Error processing schema: {e}")
        return schema

def preprocess_graphql_file(input_path: str, output_path: str = None):

    ext_in = os.path.splitext(input_path)[1].lower()
    if ext_in == ".csv":
        df = pd.read_csv(input_path)
    elif ext_in in [".xls", ".xlsx"]:
        df = pd.read_excel(input_path)
    else:
        raise ValueError(f"Unsupported input file format: {ext_in}")

    df = df.reset_index().rename(columns={'index': 'Cno'})

    required_columns = ['CleanSchema', 'GraphQLQuery', 'LLMQuery']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}. Available columns: {list(df.columns)}")

    df['extracted_graphql'] = df['LLMQuery'].apply(extract_graphql_blocks)

    df['extracted_graphql'] = df.apply(
        lambda row: extract_graphql_blocks(row['LLMQuery']) 
        if pd.isnull(row['extracted_graphql']) else row['extracted_graphql'],
        axis=1
    )

    df['extracted_graphql'] = df['extracted_graphql'].apply(balance_brackets)

    df['extracted_graphql'] = df['extracted_graphql'].apply(strip_operation_name)

    df['final_Schema'] = df['CleanSchema'].apply(preProcess)

    df['GT_GQL'] = df['GraphQLQuery'].apply(strip_operation_name)
    df['extracted_graphql'] = df['extracted_graphql'].apply(strip_operation_name)

    df['final_Schema'] = df['final_Schema'].apply(balance_brackets)
    df['GT_GQL'] = df['GT_GQL'].apply(balance_brackets)
    df['extracted_graphql'] = df['extracted_graphql'].apply(balance_brackets)

    if output_path is None:
        base, ext = os.path.splitext(os.path.basename(input_path))
        os.makedirs(f"test_output_files/{base}", exist_ok=True)  
        output_path = os.path.join("test_output_files", base, f"{base}_processed{ext}")

    ext_out = os.path.splitext(output_path)[1].lower()
    if ext_out == ".csv":
        df.to_csv(output_path, index=False)
    elif ext_out in [".xls", ".xlsx"]:
        df.to_excel(output_path, index=False)
    else:
        raise ValueError(f"Unsupported output file format: {ext_out}")

    print(f"✅ Preprocessed file saved to: {output_path}")
    return df

def process_csv_from_preprocessed_file(input_path, threshold: int = 0, output_dir: str = None):

    logger = setup_logger("readcsv_processing.log")
    df = preprocess_graphql_file(input_path)

    if output_dir == None:
        base, ext = os.path.splitext(os.path.basename(input_path))
        os.makedirs(f"test_output_files/{base}", exist_ok=True)  
        output_dir = os.path.join("test_output_files", base, "results")

    os.makedirs(output_dir, exist_ok=True)

    def clean_string(value):
        """Remove leading and trailing quotes from strings."""
        if isinstance(value, str):
            return value.strip('"')
        return str(value)

    processed_files = []

    for index, row in df.iterrows():

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        row_dir = os.path.join(output_dir, f"row_{index + 1}_{timestamp}")
        os.makedirs(row_dir, exist_ok=True)

        schema_str = clean_string(row["final_Schema"])
        query1_str = clean_string(row["GT_GQL"])
        query2_str = clean_string(row["extracted_graphql"])

        schema_file = os.path.join(row_dir, "schema.graphql")
        query1_file = os.path.join(row_dir, "query1.graphql")
        query2_file = os.path.join(row_dir, "query2.graphql")
        variables_file = os.path.join(row_dir, "variables.json")

        try:
            with open(schema_file, "w") as f:
                f.write(schema_str)
            with open(query1_file, "w") as f:
                f.write(query1_str)
            with open(query2_file, "w") as f:
                f.write(query2_str)

            variables_str = ""
            if "GraphQLQueryVariables" in row and not pd.isnull(row["GraphQLQueryVariables"]):
                variables_str = clean_string(row["GraphQLQueryVariables"])
            if variables_str.strip():
                with open(variables_file, "w") as f:
                    f.write(variables_str)
            else:
                variables_file = None
            logger.info(f"Processed files for row {index + 1} saved successfully.")
        except Exception as e:
            logger.error(f"Error saving files for row {index + 1}: {e}")

        processed_files.append((row['Cno'], row_dir, schema_file, query1_file, query2_file, variables_file, threshold))

    logger.info(f"✅ Processed {len(processed_files)} rows from CSV.")
    return processed_files

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m rgeval.pipeline.preProcessor <predictions.csv|.xlsx>")
    input_file = sys.argv[1]

    temp = process_csv_from_preprocessed_file(input_file)
    print(temp)
