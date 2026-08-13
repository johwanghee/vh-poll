from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CORE_IDS = {
    "age_bracket", "region", "urbanicity", "socioeconomic_band", "highest_education",
    "life_stage", "tech_savviness", "dominant_trait", "risk_tolerance", "decision_style",
    "values_priority", "economic_motivation", "media_diet",
}
FOOD_EXTRA_IDS = {
    "skill_cooking", "skill_baking", "topic_cooking", "topic_wine", "topic_coffee", "topic_tea",
    "topic_baking", "lstyle_diet_type", "lstyle_cooking_freq", "lstyle_coffee_ritual",
    "hob_bread_baking", "hob_home_brewing", "hob_winemaking", "hob_cheesemaking",
}
DOMAIN_CATEGORIES = {
    "decision-values": {"Risk & Decision", "Values & Motivation", "Personality: Character", "Personality: Big Five", "Behavior: Preferences"},
    "food": {"Interests: Food"},
    "lifestyle-hobbies": {"Behavior: Habits", "Interests: Hobbies", "Health: Lifestyle"},
    "culture-media": {"Interests: Culture", "Interests: Media"},
    "sports-outdoors": {"Interests: Sports", "Health: Fitness"},
}
CONSUMER_PATTERN = re.compile(r"travel|shopping|purchase|price|brand|fashion|transport|commut|home_|device|outdoor|environment", re.I)
SENSITIVE_PATTERN = re.compile(r"gender|race|ethnic|relig|politic|sexual|neurotype|disab|diagnos|disease|mental_health", re.I)
DESCRIPTIONS = {
    "core": "Basic breakdown fields and general decision traits; always available.",
    "decision-values": "Personality, values, risk, novelty, routine, spending, and decision preferences.",
    "food": "Cuisine, food, drink, and cooking interests for eating-related polls.",
    "lifestyle-hobbies": "Daily habits, home activities, hobbies, and leisure patterns.",
    "culture-media": "Books, film, music, games, arts, and media interests.",
    "sports-outdoors": "Sports, exercise, competition, and outdoor activities.",
    "consumer-adventure": "Travel, shopping, products, transport, devices, and environment-related preferences.",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("schema")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    domains: dict[str, dict[str, list[str]]] = {name: {} for name in DESCRIPTIONS}
    assigned: set[str] = set()
    for column in schema["columns"]:
        name = column["id"]
        if SENSITIVE_PATTERN.search(name):
            continue
        domain = None
        if name in CORE_IDS:
            domain = "core"
        elif name in FOOD_EXTRA_IDS:
            domain = "food"
        else:
            for candidate, categories in DOMAIN_CATEGORIES.items():
                if column["category"] in categories:
                    domain = candidate
                    break
            if domain is None and CONSUMER_PATTERN.search(name + " " + column["label"]):
                domain = "consumer-adventure"
        if domain and name not in assigned:
            domains[domain][name] = column["values"]
            assigned.add(name)
    index = {"source": "MatrAIx persona_codes.schema.json format_version 2", "attribute_count": len(assigned), "domains": {}}
    for name, attributes in domains.items():
        document = {"domain": name, "description": DESCRIPTIONS[name], "attributes": attributes}
        (output / f"{name}.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index["domains"][name] = {"file": f"attributes/{name}.json", "description": DESCRIPTIONS[name], "attribute_count": len(attributes)}
    (output.parent / "attribute-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"attribute_count": len(assigned), "domains": {name: len(values) for name, values in domains.items()}}, indent=2))


if __name__ == "__main__":
    main()
