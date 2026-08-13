from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

from common import dump_json, load_attribute_catalog, paths


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def decoded_expression(name: str, index: int, values: list[str]) -> str:
    byte_index = index // 2
    nibble_position = byte_index * 2 + (2 if index % 2 == 0 else 1)
    bitmap_byte = index // 8
    bitmap_high = bitmap_byte * 2 + 1
    bitmap_low = bitmap_byte * 2 + 2
    bit_mask = 1 << (index % 8)
    override = (
        "list_extract(list_transform(list_filter(attribute_overrides, "
        f"x -> x.field_index = {index}), x -> x.value), 1)"
    )
    code = f"strpos('0123456789ABCDEF', substr(attr_hex, {nibble_position}, 1)) - 1"
    bitmap_value = (
        f"((strpos('0123456789ABCDEF', substr(null_hex, {bitmap_high}, 1)) - 1) * 16 + "
        f"(strpos('0123456789ABCDEF', substr(null_hex, {bitmap_low}, 1)) - 1))"
    )
    choices = ", ".join(sql_string(value) for value in values)
    return (
        f"CASE WHEN {override} IS NOT NULL THEN {override} "
        f"WHEN null_hex IS NOT NULL AND ({bitmap_value} & {bit_mask}) != 0 THEN NULL "
        f"ELSE list_extract([{choices}], {code} + 1) END AS \"{name}\""
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    location = paths()
    schema_path = location["metadata"] / "persona_codes.schema.json"
    shards = sorted(location["raw"].glob("data/*.parquet"))
    if not schema_path.exists() or not shards:
        raise SystemExit("raw data or official schema missing; run setup_data.py status")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("packing") != "nibble" or schema.get("row_bytes") != 645 or len(schema.get("columns", [])) != 1290:
        raise SystemExit("unsupported official encoding")
    catalog = load_attribute_catalog()["attributes"]
    selected = {column["id"]: (position, column["values"]) for position, column in enumerate(schema["columns"]) if column["id"] in catalog}
    missing = set(catalog) - set(selected)
    if missing:
        raise SystemExit(f"selected attributes absent from official schema: {sorted(missing)}")
    output = Path(args.output).expanduser().resolve() if args.output else location["processed"] / "personas.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.part")
    temporary.unlink(missing_ok=True)
    projections = ",\n        ".join(decoded_expression(name, index, values) for name, (index, values) in selected.items())
    shard_list = ", ".join(sql_string(str(path)) for path in shards)
    query = f"""
        COPY (
            WITH packed AS (
                SELECT
                    coalesce(source_record_id, source || ':' || source_row_index::VARCHAR) AS persona_id,
                    hex(attributes) AS attr_hex,
                    CASE WHEN null_bitmap IS NULL THEN NULL ELSE hex(null_bitmap) END AS null_hex,
                    attribute_overrides
                FROM read_parquet([{shard_list}])
            )
            SELECT persona_id, {projections}
            FROM packed
        ) TO {sql_string(str(temporary))}
        (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
    """
    print(f"processing {len(shards)} shards with embedded DuckDB", file=sys.stderr)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(query)
        rows = connection.execute("SELECT count(*) FROM read_parquet(?)", [str(temporary)]).fetchone()[0]
    finally:
        connection.close()
    temporary.replace(output)
    dump_json({"output": str(output), "rows": rows, "attributes": sorted(selected), "format": "parquet", "compression": "zstd", "engine": "duckdb"}, str(location["processed"] / "manifest.json"))
    print(f"processed {rows} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
