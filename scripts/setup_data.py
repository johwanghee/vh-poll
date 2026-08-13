from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

from common import DATASET_ID, OFFICIAL_BYTES, OFFICIAL_ROWS, dump_json, load_attribute_catalog, paths


def verified(path: Path, size: int, expected_hash: str) -> bool:
    if not path.is_file() or path.stat().st_size != size:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest() == expected_hash


def status() -> dict:
    location = paths()
    manifest_path = location["metadata"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    files = manifest.get("files", []) if manifest else []
    complete = bool(files) and all((location["raw"] / item["path"]).is_file() and (location["raw"] / item["path"]).stat().st_size == item["bytes"] for item in files)
    processed = location["processed"] / "personas.parquet"
    processed_manifest_path = location["processed"] / "manifest.json"
    processed_manifest = json.loads(processed_manifest_path.read_text(encoding="utf-8")) if processed_manifest_path.exists() else {}
    expected_attributes = set(load_attribute_catalog()["attributes"])
    processed_ready = processed.is_file() and set(processed_manifest.get("attributes", [])) == expected_attributes
    return {"data_dir": str(location["root"]), "raw_complete": complete, "processed_ready": processed_ready, "processed_attribute_count": len(processed_manifest.get("attributes", [])), "expected_attribute_count": len(expected_attributes), "official_rows": OFFICIAL_ROWS, "download_bytes": OFFICIAL_BYTES, "download_gib": round(OFFICIAL_BYTES / 2**30, 2)}


def fetch(filename: str, destination: Path) -> None:
    cached = Path(hf_hub_download(repo_id=DATASET_ID, repo_type="dataset", filename=filename, local_dir=str(paths()["raw"])))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if cached.resolve() == destination.resolve():
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    shutil.copyfile(cached, temporary)
    temporary.replace(destination)
    cached.unlink(missing_ok=True)


def verify_all() -> None:
    location = paths()
    manifest_path = location["metadata"] / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("files", []):
        print(f"verifying {item['path']}", file=sys.stderr)
        if not verified(location["raw"] / item["path"], item["bytes"], item["sha256"]):
            raise SystemExit(f"manifest verification failed: {item['path']}")
    print("All raw files match the manifest.", file=sys.stderr)


def download() -> None:
    location = paths()
    for directory in location.values():
        directory.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {OFFICIAL_BYTES} bytes to {location['root']}", file=sys.stderr)
    for name in ("manifest.json", "persona_codes.schema.json", "README.md"):
        fetch(name, location["metadata"] / name)
    manifest = json.loads((location["metadata"] / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("bytes") != OFFICIAL_BYTES:
        raise RuntimeError("official manifest changed; inspect it before continuing")
    for item in manifest["files"]:
        destination = location["raw"] / item["path"]
        if verified(destination, item["bytes"], item["sha256"]):
            continue
        print(f"{item['path']} ({item['bytes']} bytes)", file=sys.stderr)
        fetch(item["path"], destination)
        if not verified(destination, item["bytes"], item["sha256"]):
            raise RuntimeError(f"manifest verification failed: {item['path']}")
    print("Download and checksum verification complete.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "download", "verify"))
    args = parser.parse_args()
    if args.command == "status":
        dump_json(status(), None)
    elif args.command == "download":
        download()
    else:
        verify_all()


if __name__ == "__main__":
    main()
