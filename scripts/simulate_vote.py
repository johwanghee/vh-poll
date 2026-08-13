from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import duckdb

from common import dump_json, load_attribute_catalog, load_json, normalized_seed, paths
from validate_rule import validate


UINT64_SCALE = 18_446_744_073_709_551_616.0


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def unit(seed: str, suffix: str) -> str:
    return f"md5_number_lower({literal(seed + ':')} || persona_id || {literal(':' + suffix)})::DOUBLE / {UINT64_SCALE}"


def source_sql(rule: dict, catalog: dict[str, list[str]], demo: bool, demo_size: int) -> tuple[str, list]:
    needed = sorted({*rule["result_groups"], *(factor["attribute"] for factor in rule["factors"])})
    if not demo:
        columns = ", ".join(identifier(name) for name in needed)
        processed = paths()["processed"] / "personas.parquet"
        if not processed.exists():
            raise SystemExit("processed Persona data missing; run setup_data.py status or pass --demo")
        return f"SELECT persona_id{', ' if columns else ''}{columns} FROM read_parquet(?)", [str(processed)]
    projections = []
    for name in needed:
        values = ", ".join(literal(value) for value in catalog[name])
        position = f"((md5_number_lower(persona_id || {literal(':' + name)}) % {len(catalog[name])}) + 1)::BIGINT"
        projections.append(f"list_extract([{values}], {position}) AS {identifier(name)}")
    suffix = ", " + ", ".join(projections) if projections else ""
    return f"SELECT 'demo-' || i::VARCHAR AS persona_id{suffix} FROM range(?) AS generated(i)", [demo_size]


def score_expression(rule: dict, choice: str) -> str:
    score = f"ln({max(float(rule['base_scores'][choice]), 1e-9)})"
    for factor in rule["factors"]:
        conditions = ", ".join(literal(value) for value in factor["conditions"])
        effect = float(factor["effects"].get(choice, 0))
        if effect:
            score += f" + CASE WHEN {identifier(factor['attribute'])} IN ({conditions}) THEN {effect} ELSE 0 END"
    score += f" + ({unit(rule['seed'], choice)} - 0.5) * 0.08"
    return score


def create_votes(connection, rule: dict, source: str, parameters: list, mode: str) -> None:
    choices = [choice["id"] for choice in rule["choices"]]
    scores = [f"{score_expression(rule, choice)} AS s{index}" for index, choice in enumerate(choices)]
    greatest = "greatest(" + ", ".join(f"s{index}" for index in range(len(choices))) + ")"
    weights = [f"exp(s{index} - {greatest}) AS w{index}" for index in range(len(choices))]
    denominator = " + ".join(f"w{index}" for index in range(len(choices)))
    probabilities = [f"w{index} / ({denominator}) AS p{index}" for index in range(len(choices))]
    retained_names = sorted({*rule["result_groups"], *(factor["attribute"] for factor in rule["factors"])})
    retained_columns = ", ".join(identifier(name) for name in retained_names)
    prefix = retained_columns + ", " if retained_columns else ""
    if mode == "expected":
        final = ", ".join(f"p{index}" for index in range(len(choices)))
    else:
        draw = unit(rule["seed"], "sample")
        cumulative = []
        for index in range(len(choices)):
            cumulative.append(" + ".join(f"p{part}" for part in range(index + 1)))
        selected = f"CASE " + " ".join(f"WHEN {draw} < ({limit}) THEN {index}" for index, limit in enumerate(cumulative[:-1])) + f" ELSE {len(choices) - 1} END"
        final = ", ".join(f"CASE WHEN selected = {index} THEN 1.0 ELSE 0.0 END AS p{index}" for index in range(len(choices)))
    sampled_cte = f", selected AS (SELECT *, {selected} AS selected FROM probabilities)" if mode == "sampled" else ""
    final_source = "selected" if mode == "sampled" else "probabilities"
    query = f"""
        CREATE TEMP TABLE vote_rows AS
        WITH personas AS ({source}),
        scores AS (SELECT *, {', '.join(scores)} FROM personas),
        weights AS (SELECT *, {', '.join(weights)} FROM scores),
        probabilities AS (SELECT *, {', '.join(probabilities)} FROM weights)
        {sampled_cte}
        SELECT {prefix}{final} FROM {final_source}
    """
    connection.execute(query, parameters)


def discover_preference_groups(connection, rule: dict, catalog_document: dict, choices: list[str], totals: list[float], count: int) -> dict:
    catalog = catalog_document["attributes"]
    allowed = set(catalog_document.get("preference_group_attributes", []))
    factor_attributes = sorted({factor["attribute"] for factor in rule["factors"] if factor["attribute"] in allowed})
    candidates = [[] for _ in choices]
    minimum_count = max(1000, count // 100)
    dimensions = [(name,) for name in factor_attributes]
    dimensions.extend(itertools.combinations(factor_attributes, 2))
    for names in dimensions:
        columns = ", ".join(identifier(name) for name in names)
        validity = " AND ".join(
            f"{identifier(name)} IN ({', '.join(literal(value) for value in catalog[name])})" for name in names
        )
        query = (
            f"SELECT {columns}, count(*), "
            + ", ".join(f"sum(p{index})" for index in range(len(choices)))
            + f" FROM vote_rows WHERE {validity} GROUP BY {columns} HAVING count(*) >= ?"
        )
        for row in connection.execute(query, [minimum_count]).fetchall():
            size = row[len(names)]
            for index, choice in enumerate(choices):
                percent = row[len(names) + 1 + index] * 100 / size
                lift = percent - totals[index] * 100 / count
                candidates[index].append(
                    {
                        "choice": choice,
                        "attributes": list(names),
                        "values": list(row[: len(names)]),
                        "count": size,
                        "percent": round(percent, 2),
                        "lift_pp": round(lift, 2),
                    }
                )
    return {
        choice: max(candidates[index], key=lambda item: (item["lift_pp"], item["count"]), default=None)
        for index, choice in enumerate(choices)
    }


def calculate(rule: dict, mode: str, demo: bool, demo_size: int, catalog_document: dict) -> dict:
    catalog = catalog_document["attributes"]
    choices = [choice["id"] for choice in rule["choices"]]
    labels = {choice["id"]: choice["label"] for choice in rule["choices"]}
    connection = duckdb.connect(":memory:")
    try:
        source, parameters = source_sql(rule, catalog, demo, demo_size)
        create_votes(connection, rule, source, parameters, mode)
        aggregate = connection.execute("SELECT count(*), " + ", ".join(f"sum(p{i})" for i in range(len(choices))) + " FROM vote_rows").fetchone()
        count = aggregate[0]
        totals = list(aggregate[1:])
        results = [{"id": choice, "label": labels[choice], "votes": round(totals[index]), "percent": round(totals[index] * 100 / count, 2)} for index, choice in enumerate(choices)]
        difference = count - sum(result["votes"] for result in results)
        results[max(range(len(results)), key=lambda index: results[index]["votes"])]["votes"] += difference
        preference_groups = discover_preference_groups(connection, rule, catalog_document, choices, totals, count)
        groups = {}
        for name in rule["result_groups"]:
            valid = ", ".join(literal(value) for value in catalog[name])
            key = f"CASE WHEN {identifier(name)} IN ({valid}) THEN {identifier(name)} ELSE 'Unknown' END"
            rows = connection.execute(f"SELECT {key} AS group_name, count(*), " + ", ".join(f"sum(p{i})" for i in range(len(choices))) + " FROM vote_rows GROUP BY group_name ORDER BY count(*) DESC").fetchall()
            groups[name] = [{"group": row[0], "count": row[1], "percentages": {choice: round(row[index + 2] * 100 / row[1], 2) for index, choice in enumerate(choices)}} for row in rows]
        if rule["factors"]:
            missing_sql = " + ".join(f"sum(CASE WHEN {identifier(factor['attribute'])} IS NULL THEN 1 ELSE 0 END)" for factor in rule["factors"])
            missing = connection.execute(f"SELECT {missing_sql} FROM vote_rows").fetchone()[0]
        else:
            missing = 0
    finally:
        connection.close()
    return {"question": rule["question"], "mode": mode, "demo": demo, "engine": "duckdb-memory", "persona_count": count, "choices": results, "preference_groups": preference_groups, "groups": groups, "top_factors": sorted(rule["factors"], key=lambda factor: max(abs(float(value)) for value in factor["effects"].values()), reverse=True)[:3], "missing_factor_value_count": missing, "disclaimer": "AI 가상인류 시뮬레이션이며 실제 설문 결과가 아닙니다."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule", required=True)
    parser.add_argument("--mode", choices=("expected", "sampled"), default="expected")
    parser.add_argument("--seed")
    parser.add_argument("--output")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--demo-size", type=int, default=10000)
    args = parser.parse_args()
    rule = validate(load_json(Path(args.rule).resolve()))
    if args.seed is not None:
        rule["seed"] = normalized_seed(rule["question"], args.seed)
    catalog_document = load_attribute_catalog()
    dump_json(calculate(rule, args.mode, args.demo, args.demo_size, catalog_document), args.output)


if __name__ == "__main__":
    main()
