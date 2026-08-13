from __future__ import annotations

import argparse
import difflib
from pathlib import Path

from common import dump_json, load_attribute_catalog, load_json, normalized_seed


def validate(rule: dict) -> dict:
    catalog = load_attribute_catalog()
    attributes = catalog["attributes"]
    choices = rule.get("choices", [])
    if not 2 <= len(choices) <= 4:
        raise ValueError("choices must contain 2 to 4 items")
    ids = [choice["id"] for choice in choices]
    if len(ids) != len(set(ids)):
        raise ValueError("choice ids must be unique")
    if set(rule.get("base_scores", {})) != set(ids):
        raise ValueError("base_scores keys must exactly match choice ids")
    total = sum(float(value) for value in rule["base_scores"].values())
    if not 0.999 <= total <= 1.001:
        raise ValueError("base_scores must sum to 1")
    for factor in rule.get("factors", []):
        name = factor.get("attribute", "")
        if name not in attributes:
            match = difflib.get_close_matches(name, attributes, n=1, cutoff=0.82)
            if match:
                factor["attribute"] = name = match[0]
            else:
                raise ValueError(f"unknown attribute: {name}")
        invalid = sorted(set(factor.get("conditions", [])) - set(attributes[name]))
        if invalid:
            raise ValueError(f"invalid values for {name}: {invalid}")
        if set(factor.get("effects", {})) - set(ids):
            raise ValueError(f"factor effects reference unknown choice: {name}")
        if any(abs(float(value)) > 0.25 for value in factor["effects"].values()):
            raise ValueError(f"factor effect exceeds 0.25: {name}")
        if name in catalog.get("sensitive_for_effects", []):
            raise ValueError(f"sensitive attribute cannot drive choices: {name}")
    rule.setdefault("interactions", [])
    if rule["interactions"]:
        raise ValueError("interactions are reserved until a stricter validator is implemented")
    rule.setdefault("result_groups", ["region", "age_bracket"])
    if set(rule["result_groups"]) - set(catalog["preferred_breakdowns"]):
        raise ValueError("unsupported result group")
    rule["seed"] = normalized_seed(rule["question"], rule.get("seed"))
    return rule


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rule")
    parser.add_argument("--output")
    args = parser.parse_args()
    dump_json(validate(load_json(Path(args.rule).resolve())), args.output)


if __name__ == "__main__":
    main()
