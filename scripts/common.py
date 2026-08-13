from __future__ import annotations

import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any

DATASET_ID = "MatrAIx2026/MatrAIx_Persona_1M_Public_Release"
HF_BASE = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/main"
OFFICIAL_BYTES = 4_167_729_762
OFFICIAL_ROWS = 999_847


def data_root() -> Path:
    value = os.environ.get("VIRTUAL_HUMAN_POLL_DATA_DIR")
    return Path(value).expanduser().resolve() if value else (Path.home() / ".cache" / "vh-poll").resolve()


def paths() -> dict[str, Path]:
    root = data_root()
    return {"root": root, "raw": root / "raw", "processed": root / "processed", "metadata": root / "metadata"}


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_attribute_catalog() -> dict[str, Any]:
    reference_root = skill_root() / "references"
    index = load_json(reference_root / "attribute-index.json")
    attributes: dict[str, list[str]] = {}
    domains: dict[str, list[str]] = {}
    for domain, metadata in index["domains"].items():
        document = load_json(reference_root / metadata["file"])
        domains[domain] = list(document["attributes"])
        for name, values in document["attributes"].items():
            if name in attributes:
                raise ValueError(f"duplicate catalog attribute: {name}")
            attributes[name] = values
    return {
        "attributes": attributes,
        "domains": domains,
        "sensitive_for_effects": [],
        "preferred_breakdowns": ["region", "age_bracket", "urbanicity"],
        "preference_group_attributes": sorted(name for name in attributes if name not in {"region", "age_bracket", "urbanicity", "socioeconomic_band", "highest_education", "life_stage"}),
    }


def dump_json(value: Any, output: str | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(target)
    else:
        sys.stdout.write(text)


def normalized_seed(question: str, override: str | None = None) -> str:
    text = override if override is not None else " ".join(unicodedata.normalize("NFKC", question).casefold().split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_unit(seed: str, identity: str) -> float:
    digest = hashlib.blake2b(f"{seed}\0{identity}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64
