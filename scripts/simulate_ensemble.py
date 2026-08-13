from __future__ import annotations

import argparse
import collections
import statistics
from pathlib import Path

import duckdb

from common import dump_json, load_attribute_catalog, load_json, normalized_seed, paths
from simulate_vote import calculate, identifier, literal
from validate_rule import validate


def selector_expression(selector: dict) -> str:
    values = ", ".join(literal(value) for value in selector["conditions"])
    return f"{identifier(selector['attribute'])} IN ({values})"


def validate_empirical_prior(document: dict, catalog: dict) -> set[str]:
    empirical = document.get("empirical_prior")
    if not empirical:
        return set()
    choice_ids = {choice["id"] for choice in document["choices"]}
    evidence = empirical.get("evidence", {})
    if set(evidence) != choice_ids:
        raise ValueError("empirical_prior evidence keys must exactly match choice ids")
    attributes = catalog["attributes"]
    used = set()
    for choice, selectors in evidence.items():
        if not 1 <= len(selectors) <= 3:
            raise ValueError(f"empirical_prior {choice} requires 1 to 3 evidence selectors")
        for selector in selectors:
            name = selector.get("attribute", "")
            if name not in attributes:
                raise ValueError(f"unknown empirical_prior attribute: {name}")
            conditions = selector.get("conditions", [])
            if not conditions:
                raise ValueError(f"empirical_prior selector requires conditions: {name}")
            invalid = sorted(set(conditions) - set(attributes[name]))
            if invalid:
                raise ValueError(f"invalid empirical_prior values for {name}: {invalid}")
            used.add(name)
    return used


def resolve_prior(document: dict, catalog: dict, demo: bool) -> tuple[dict[str, float], dict]:
    authored = {choice["id"]: float(document["base_scores"][choice["id"]]) for choice in document["choices"]}
    empirical = document.get("empirical_prior")
    if not empirical or demo:
        reason = "no_empirical_prior" if not empirical else "demo_mode_has_no_persona_observations"
        return authored, {"mode": "authored", "base_scores_used": authored, "reason": reason}

    processed = paths()["processed"] / "personas.parquet"
    if not processed.exists():
        raise SystemExit("processed Persona data missing; run setup_data.py status or pass --demo")
    evidence = empirical["evidence"]
    choice_ids = [choice["id"] for choice in document["choices"]]
    matched_expressions = []
    valid_expressions = []
    for choice in choice_ids:
        selectors = evidence[choice]
        matched_expressions.append("(" + " OR ".join(selector_expression(item) for item in selectors) + ")")
        valid_expressions.append("(" + " OR ".join(f"{identifier(item['attribute'])} IS NOT NULL" for item in selectors) + ")")
    projections = []
    for index, expression in enumerate(matched_expressions):
        projections.extend(
            [
                f"count(*) FILTER (WHERE {expression}) AS matched_{index}",
                f"count(*) FILTER (WHERE {valid_expressions[index]}) AS valid_{index}",
            ]
        )
    any_match = " OR ".join(matched_expressions)
    connection = duckdb.connect(":memory:")
    try:
        row = connection.execute(
            "SELECT count(*) AS total, " + ", ".join(projections) + f", count(*) FILTER (WHERE {any_match}) AS any_match FROM read_parquet(?)",
            [str(processed)],
        ).fetchone()
    finally:
        connection.close()
    total = row[0]
    matched = [row[1 + index * 2] for index in range(len(choice_ids))]
    valid = [row[2 + index * 2] for index in range(len(choice_ids))]
    matched_sum = sum(matched)
    if not matched_sum:
        return authored, {"mode": "authored", "base_scores_used": authored, "reason": "empirical_evidence_matched_zero_personas"}
    resolved = {choice: matched[index] / matched_sum for index, choice in enumerate(choice_ids)}
    observations = {
        choice: {
            "selectors": evidence[choice],
            "matched_personas": matched[index],
            "valid_personas": valid[index],
            "missing_personas": total - valid[index],
            "matched_percent_of_all": round(matched[index] * 100 / total, 2),
            "share_of_evidence_matches": round(resolved[choice] * 100, 2),
        }
        for index, choice in enumerate(choice_ids)
    }
    return resolved, {
        "mode": "empirical_direct",
        "base_scores_used": resolved,
        "authored_fallback": authored,
        "persona_count": total,
        "personas_with_any_match": row[-1],
        "any_match_percent": round(row[-1] * 100 / total, 2),
        "choices": observations,
        "method": "Normalize per-choice counts matching exact option-level selectors. A persona may match more than one choice; missing values do not count as matches.",
    }


def validate_ensemble(document: dict) -> list[tuple[dict, dict]]:
    perspectives = document.get("perspectives", [])
    if not 3 <= len(perspectives) <= 5:
        raise ValueError("ensemble requires 3 to 5 perspectives")
    ids = [item.get("id") for item in perspectives]
    if len(ids) != len(set(ids)):
        raise ValueError("perspective ids must be unique")
    seed = normalized_seed(document["question"], document.get("seed"))
    validated = []
    for perspective in perspectives:
        if not 2 <= len(perspective.get("factors", [])) <= 6:
            raise ValueError(f"perspective {perspective.get('id')} requires 2 to 6 factors")
        rule = validate(
            {
                "question": document["question"],
                "choices": document["choices"],
                "base_scores": document["base_scores"],
                "factors": perspective["factors"],
                "result_groups": document.get("result_groups", ["region", "age_bracket"]),
                "seed": seed,
            }
        )
        validated.append((perspective, rule))
    return validated


def direction_for(factor: dict, choice_ids: list[str]) -> str | None:
    effects = {choice: float(factor["effects"].get(choice, 0)) for choice in choice_ids}
    maximum = max(effects.values())
    winners = [choice for choice, value in effects.items() if value == maximum]
    return winners[0] if len(winners) == 1 and maximum > min(effects.values()) else None


def factor_observations(validated: list[tuple[dict, dict]], persona_count: int, demo: bool) -> dict[tuple[str, tuple[str, ...]], dict]:
    if demo:
        return {}
    unique = {}
    for _, rule in validated:
        for factor in rule["factors"]:
            unique[(factor["attribute"], tuple(factor["conditions"]))] = factor
    processed = paths()["processed"] / "personas.parquet"
    expressions = []
    keys = list(unique)
    for index, (attribute, conditions) in enumerate(keys):
        values = ", ".join(literal(value) for value in conditions)
        expressions.extend(
            [
                f"count({identifier(attribute)}) AS valid_{index}",
                f"sum(CASE WHEN {identifier(attribute)} IN ({values}) THEN 1 ELSE 0 END) AS matched_{index}",
            ]
        )
    connection = duckdb.connect(":memory:")
    try:
        row = connection.execute("SELECT " + ", ".join(expressions) + " FROM read_parquet(?)", [str(processed)]).fetchone()
    finally:
        connection.close()
    observations = {}
    for index, key in enumerate(keys):
        valid, matched = row[index * 2], row[index * 2 + 1]
        observations[key] = {
            "valid_personas": valid,
            "missing_personas": persona_count - valid,
            "matched_personas": matched,
            "matched_percent_of_all": round(matched * 100 / persona_count, 2),
            "matched_percent_of_valid": round(matched * 100 / valid, 2) if valid else 0.0,
        }
    return observations


def aggregate(document: dict, mode: str, demo: bool, demo_size: int) -> dict:
    catalog = load_attribute_catalog()
    empirical_attributes = validate_empirical_prior(document, catalog)
    resolved_scores, prior_evidence = resolve_prior(document, catalog, demo)
    document = {**document, "base_scores": resolved_scores}
    choice_ids = [choice["id"] for choice in document["choices"]]
    labels = {choice["id"]: choice["label"] for choice in document["choices"]}
    perspective_results = []
    persona_count = None
    signal_counter: dict[tuple[str, tuple[str, ...], str], list[str]] = collections.defaultdict(list)
    validated = validate_ensemble(document)
    for perspective, rule in validated:
        repeated = sorted({factor["attribute"] for factor in rule["factors"]} & empirical_attributes)
        if repeated:
            raise ValueError(f"empirical prior evidence cannot be reused as perspective effects: {repeated}")
        result = calculate(rule, mode, demo, demo_size, catalog)
        if persona_count is None:
            persona_count = result["persona_count"]
        elif persona_count != result["persona_count"]:
            raise ValueError("perspectives produced different persona counts")
        percentages = {item["id"]: item["percent"] for item in result["choices"]}
        winner = max(choice_ids, key=percentages.get)
        perspective_results.append(
            {
                "id": perspective["id"],
                "label": perspective["label"],
                "rationale": perspective["rationale"],
                "winner": winner,
                "percentages": percentages,
                "preference_groups": result["preference_groups"],
                "factor_assumptions": perspective["factors"],
                "missing_factor_attribute_cells": result["missing_factor_attribute_cells"],
            }
        )
        for factor in perspective["factors"]:
            direction = direction_for(factor, choice_ids)
            if direction:
                signal_counter[(factor["attribute"], tuple(factor["conditions"]), direction)].append(perspective["id"])
    observations = factor_observations(validated, persona_count, demo)
    for result in perspective_results:
        for factor in result["factor_assumptions"]:
            factor["observed_coverage"] = observations.get((factor["attribute"], tuple(factor["conditions"])))
    count = len(perspective_results)
    choices = []
    for choice in choice_ids:
        values = [result["percentages"][choice] for result in perspective_results]
        mean = statistics.mean(values)
        choices.append(
            {
                "id": choice,
                "label": labels[choice],
                "percent": round(mean, 2),
                "count": round(mean * persona_count / 100),
                "range": {"min": min(values), "max": max(values), "width_pp": round(max(values) - min(values), 2)},
            }
        )
    count_difference = persona_count - sum(choice["count"] for choice in choices)
    choices[max(range(len(choices)), key=lambda index: choices[index]["count"])]["count"] += count_difference
    winner_counts = collections.Counter(result["winner"] for result in perspective_results)
    top_winner, top_count = winner_counts.most_common(1)[0]
    winner_stability = "stable" if top_count == count else "contested"
    robust_signals = [
        {"attribute": key[0], "conditions": list(key[1]), "supports": key[2], "perspective_count": len(perspectives), "perspectives": perspectives}
        for key, perspectives in signal_counter.items()
        if len(perspectives) >= 2
    ]
    return {
        "question": document["question"],
        "mode": mode,
        "demo": demo,
        "engine": "duckdb-memory-ensemble",
        "count_type": "expected_probability_sum" if mode == "expected" else "sampled_vote_count",
        "persona_count_per_perspective": persona_count,
        "perspective_count": count,
        "choices": choices,
        "winner_assessment": {"status": winner_stability, "winner": top_winner if winner_stability == "stable" else None, "wins": dict(winner_counts)},
        "perspectives": perspective_results,
        "robust_signals": robust_signals,
        "prior_evidence": prior_evidence,
        "evidence_note": {
            "computed": "Empirical-prior matches, coverage, percentages, ranges, group sizes, and lifts are deterministic aggregations over the processed Persona rows.",
            "assumed": "Perspective selection, factor-to-choice direction, and effect sizes are LLM-authored scenario assumptions, not relationships learned or validated from survey outcomes.",
            "interpretation": "A stable winner means all scenario perspectives agreed; contested means the winner changed when reasonable assumptions changed.",
            "sample_scope": "Each perspective re-evaluates the same Persona rows. Perspective count does not multiply the number of unique personas.",
            "count_interpretation": "expected_probability_sum is a sum of choice probabilities, not a count of personas who cast hard votes.",
        },
        "disclaimer": "AI 가상인류 시뮬레이션이며 실제 설문 결과가 아닙니다.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensemble", required=True)
    parser.add_argument("--mode", choices=("expected", "sampled"), default="expected")
    parser.add_argument("--output")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--demo-size", type=int, default=10000)
    args = parser.parse_args()
    document = load_json(Path(args.ensemble).resolve())
    dump_json(aggregate(document, args.mode, args.demo, args.demo_size), args.output)


if __name__ == "__main__":
    main()
