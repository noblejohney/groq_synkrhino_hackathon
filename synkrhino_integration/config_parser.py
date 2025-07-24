import json

def parse_mapping_file(path):
    with open(path) as f:
        return json.load(f)

def extract_table_columns(mapping_json):
    return [(entry['source_table'], entry['source_column']) for entry in mapping_json['columns']]
