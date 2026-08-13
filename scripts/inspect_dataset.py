from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from common import dump_json, paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file")
    parser.add_argument("--output")
    args = parser.parse_args()
    candidates = [Path(args.file).resolve()] if args.file else sorted(paths()["raw"].glob("data/*.parquet"))
    if not candidates:
        raise SystemExit("no raw Parquet shard found")
    connection = duckdb.connect(":memory:")
    try:
        schema = connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(candidates[0])]).fetchall()
        rows = connection.execute("SELECT count(*) FROM read_parquet(?)", [str(candidates[0])]).fetchone()[0]
    finally:
        connection.close()
    dump_json({"file": str(candidates[0]), "rows": rows, "schema": [{"name": row[0], "type": row[1]} for row in schema]}, args.output)


if __name__ == "__main__":
    main()

