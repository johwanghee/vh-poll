---
name: vh-poll
description: Run playful, deterministic virtual-human balance polls using the MatrAIx Persona 1M public release. Use when a user invokes $vh-poll, asks virtual personas to choose between two to four options, requests a rerun with a new seed, or asks why a prior virtual poll produced its result. Never present the output as a real survey or population forecast.
---

# Virtual Human Poll

Turn a light question into a validated rule, calculate votes locally, and present a compact Korean result. Use the LLM only to analyze the question and write the final playful summary; never generate or execute question-specific code.

## Run the workflow

Before using `uv`, set `UV_PROJECT_ENVIRONMENT` to `<resolved-data-directory>/venv` so dependencies are installed outside the skill folder. Keep `UV_CACHE_DIR` under the same data directory when practical.

1. Run `uv run --project <skill-directory> python scripts/setup_data.py status`.
2. If processed data exists, continue. If only raw shards exist, run `uv run --project <skill-directory> python scripts/preprocess_personas.py`.
3. If data is absent, report the exact manifest size and resolved cache path, then obtain explicit user consent before running `uv run --project <skill-directory> python scripts/setup_data.py download`. Never infer consent from the original poll request.
4. If downloading or local data access is impossible, use `uv run --project <skill-directory> python scripts/simulate_vote.py --rule <rule.json> --demo`; label the result as an LLM-designed demo, not a Persona 1M aggregation.
5. Read `references/attribute-index.json` and `references/attributes/core.json`. Select at most two relevant domain files listed below and read them completely. Choose one comparison mode. When every choice has an exact option-level catalog attribute, add `empirical_prior.evidence` for all choices using symmetric positive-interest values. When only some choices have direct attributes, add `hybrid_sensitivity`: list every asymmetric direct attribute under `excluded_direct_attributes`, define three to five disclosed familiarity-prior scenarios, identify one equal-score `fit_only_prior_id`, and identify the most defensible `central_prior_id`. When no choice has direct evidence, omit both and use neutral or explicitly justified fallback `base_scores`. Create three independent perspectives using only shared fit dimensions: context, behavior/personality, and values/lifestyle. Never reuse excluded or empirical-prior attributes as factors. Write JSON only; do not embed the question in a shell command.
6. Run `uv run --project <skill-directory> python scripts/simulate_ensemble.py --ensemble <ensemble.json> --mode expected --output <result.json>`. Use the single-rule validator and simulator only for diagnostics or when explicitly requested. Use `sampled` only when requested.
8. Render a short result and always end with: `AI 가상인류 시뮬레이션이며 실제 설문 결과가 아닙니다.`

For “다시 돌려줘” or “다른 결과로”, preserve the rule and pass a fresh string with `--seed`. Otherwise omit it so normalized question text yields the same result.

## Analyze the question

- Preserve explicit choices; otherwise create two to four concise choices without changing the premise.
- Assign fallback base scores totaling 1. Treat them as authored assumptions, not observed popularity.
- Use `empirical_prior` only when each choice maps cleanly to its own direct catalog attribute. Provide one to three selectors per choice, use symmetric value criteria, and omit it for incomplete or proxy-only mappings. The engine normalizes observed match counts into the shared prior and reports match coverage and missingness.
- Use `hybrid_sensitivity` for asymmetric direct coverage. Exclude all option-specific direct attributes from every perspective. Include an equal-score fit-only scenario plus at least two plausible familiarity scenarios. Name the central scenario `현실 인지도 포함` and the equal-score scenario `취향만 비교`; keep stronger stress cases internal. In each rationale, explain the scores as choice probabilities before Persona traits are applied. Do not present them as observations or tune them to force a desired winner. The engine treats margins below 1 percentage point as `near_tie` and reports `stable` only when every scenario has the same non-tied winner; otherwise it reports `assumption_sensitive`.
- Select three to eight directly relevant factors when the catalog supports them. Prefer domain-specific attributes over broad proxies, and omit weakly related factors rather than filling a quota.
- Create exactly three perspectives by default, with two to six factors each. Do not reuse an empirical-prior attribute in any perspective. Do not reuse other attributes across perspectives unless independently central; repeated support then becomes a robust signal.
- Keep one shared base score map and comparable effect magnitudes across perspectives. Do not change them to force agreement or a more dramatic result.
- Use demographic attributes primarily for result breakdowns, not choice effects.
- Keep each effect within -0.25 to 0.25 and interactions within -0.15 to 0.15.
- Do not connect protected traits to crime, intelligence, morality, or other harmful stereotypes. Avoid political, religious, racial, or gender essentialism.
- If no relevant attribute exists, use base scores plus deterministic personal variation.
- Request `region` and `age_bracket` result groups unless the question makes them inappropriate.

Route questions with these catalog files:

- Food and drink: `references/attributes/food.json` plus `references/attributes/decision-values.json`
- Habits, home, and leisure: `references/attributes/lifestyle-hobbies.json` plus `references/attributes/decision-values.json`
- Books, music, film, games, and arts: `references/attributes/culture-media.json` plus `references/attributes/decision-values.json`
- Sports and outdoor choices: `references/attributes/sports-outdoors.json` plus `references/attributes/decision-values.json`
- Travel, shopping, products, transport, and devices: `references/attributes/consumer-adventure.json` plus `references/attributes/decision-values.json`
- Abstract dilemmas: `references/attributes/decision-values.json`; add one other domain only when clearly relevant.

## Present results

Keep the default answer playful and under 180 Korean words. Lead with an apt emoji and the two-to-four headline percentages. Mention `persona_count_per_perspective` once as `가상 페르소나 N명`; never multiply it by perspective count. Follow with two or three plain-language sentences explaining what drove the result, one clearly fictional witty line, and the required disclaimer.

For `hybrid_sensitivity`, use this order:

1. `현실 인지도까지 넣으면` followed by the central scenario percentages.
2. `이름표를 가리고 취향만 보면` followed by the fit-only percentages and `사실상 동률` when its verdict is `near_tie`.
3. If sensitivity is `stable`, say the lead survived every tested assumption. If `assumption_sensitive`, say plainly how the conclusion changes, such as `취향은 접전이고 인지도 가정이 승부를 갈랐습니다`.
4. Add one short trust note: name excluded direct attributes in friendly language and say the familiarity starting point was an explicit scenario assumption, not a Persona observation.

Do not show the terms `prior`, `central`, `moderate`, `strong`, `hybrid_sensitivity`, `assumption_sensitive`, scenario IDs, engine names, full sensitivity ranges, effect coefficients, or internal evidence labels in the default answer. Do not print every scenario. Reveal these details only when the user asks for methodology, full evidence, or debugging. When explaining a starting score, call it `Persona 성향을 적용하기 전의 출발 확률` and give its exact numbers.

For `empirical_direct`, briefly show observed match share and coverage before the playful interpretation. For authored fallback, say the starting point was a scenario assumption. In `expected` mode, show `count` only if useful and label it `확률 합계 환산`; never call it people who cast votes. Show perspective ranges, group breakdowns, and robust signals only when they materially explain the result or the user asks. Never call a hybrid result observed popularity.

When explaining a result, separate evidence into three labels:

- **Calculated from Persona data:** empirical-prior matches and coverage, percentages, ranges, group counts, lifts, missing counts, and `observed_coverage`.
- **Scenario assumption:** why an attribute supports a choice and the assigned effect size.
- **Robustness judgment:** stable/contested winner and signals repeated across perspectives.

Never describe factor directions as learned correlations, causal effects, or survey findings. Describe preference-group lifts as discoveries inside the declared simulation rules, not claims about real people.

## Data guarantees

Resolve data under `VIRTUAL_HUMAN_POLL_DATA_DIR` or `~/.cache/vh-poll`. Keep raw, processed, metadata, dependency environments, and tool caches outside the skill folder. Store processed personas as ZSTD-compressed Parquet. Query and aggregate that Parquet directly with `duckdb.connect(":memory:")`; never create a DuckDB database file. Keep direct Python dependencies limited to `duckdb` and `huggingface-hub`. Verify official manifest byte sizes and SHA-256 hashes. Never delete raw data unless the user explicitly requests deletion and confirms the exact resolved path.

Read `DATA_LICENSE_NOTICE.md` before downloading or redistributing dataset-derived material. Do not describe the combined Persona release as MIT, CC-BY, or another single license; the official release keeps source-specific licenses and terms in force.

The official encoding is 645 packed bytes for 1,290 fields. Decode the low nibble for even field indexes and high nibble for odd indexes, apply the null bitmap, then apply sparse overrides. The preprocessing CLI implements this order and refuses incompatible schemas.
