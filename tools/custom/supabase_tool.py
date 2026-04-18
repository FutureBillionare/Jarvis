"""
Tool: supabase_tool
Description: Interact with a Supabase project — query, insert, update, delete rows and call RPCs.
Requires: SUPABASE_URL and SUPABASE_KEY environment variables.
"""
import os, json

def _client():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY environment variables.")
    return create_client(url, key)


def run_query(params):
    table   = params["table"]
    filters = params.get("filters", {})
    columns = params.get("columns", "*")
    limit   = params.get("limit", 50)
    c = _client()
    q = c.table(table).select(columns)
    for col, val in filters.items():
        q = q.eq(col, val)
    q = q.limit(limit)
    res = q.execute()
    return json.dumps(res.data, indent=2, default=str)


def run_insert(params):
    table = params["table"]
    data  = params["data"]
    c = _client()
    res = c.table(table).insert(data).execute()
    return f"Inserted {len(res.data)} row(s) into {table}."


def run_update(params):
    table   = params["table"]
    data    = params["data"]
    filters = params["filters"]
    c = _client()
    q = c.table(table).update(data)
    for col, val in filters.items():
        q = q.eq(col, val)
    res = q.execute()
    return f"Updated {len(res.data)} row(s) in {table}."


def run_delete(params):
    table   = params["table"]
    filters = params["filters"]
    c = _client()
    q = c.table(table).delete()
    for col, val in filters.items():
        q = q.eq(col, val)
    res = q.execute()
    return f"Deleted {len(res.data)} row(s) from {table}."


def run_rpc(params):
    fn     = params["function"]
    args   = params.get("args", {})
    c = _client()
    res = c.rpc(fn, args).execute()
    return json.dumps(res.data, indent=2, default=str)


TOOLS = [
    ({"name": "supabase_query",
      "description": "Query rows from a Supabase table with optional filters.",
      "input_schema": {"type": "object", "properties": {
          "table":   {"type": "string"},
          "filters": {"type": "object",  "description": "Column:value pairs to filter by"},
          "columns": {"type": "string",  "description": "Columns to select, default '*'"},
          "limit":   {"type": "integer", "description": "Max rows, default 50"},
      }, "required": ["table"]}}, run_query),

    ({"name": "supabase_insert",
      "description": "Insert one or more rows into a Supabase table.",
      "input_schema": {"type": "object", "properties": {
          "table": {"type": "string"},
          "data":  {"description": "Row dict or list of row dicts"},
      }, "required": ["table", "data"]}}, run_insert),

    ({"name": "supabase_update",
      "description": "Update rows in a Supabase table matching filters.",
      "input_schema": {"type": "object", "properties": {
          "table":   {"type": "string"},
          "data":    {"type": "object", "description": "Fields to update"},
          "filters": {"type": "object", "description": "Column:value filter pairs"},
      }, "required": ["table", "data", "filters"]}}, run_update),

    ({"name": "supabase_delete",
      "description": "Delete rows from a Supabase table matching filters.",
      "input_schema": {"type": "object", "properties": {
          "table":   {"type": "string"},
          "filters": {"type": "object"},
      }, "required": ["table", "filters"]}}, run_delete),

    ({"name": "supabase_rpc",
      "description": "Call a Supabase stored procedure / RPC function.",
      "input_schema": {"type": "object", "properties": {
          "function": {"type": "string"},
          "args":     {"type": "object", "description": "Arguments to pass"},
      }, "required": ["function"]}}, run_rpc),
]
