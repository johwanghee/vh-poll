# vh-poll

MatrAIx Persona 1M을 로컬에서 집계해 두 개에서 네 개 선택지 사이의 가벼운 밸런스 투표를 만드는 이식 가능한 Agent Skill입니다. `SKILL.md`를 읽고 로컬 Python 명령을 실행할 수 있는 Codex, OpenClaw, Hermes Agent에서 사용할 수 있습니다.

> **AI 가상인류 시뮬레이션이며 실제 설문 결과가 아닙니다.**
> 결과를 여론조사, 모집단 추정치 또는 현실 사람들의 인과관계로 해석하면 안 됩니다.

## 무엇을 하나요?

- 공개 Persona 999,847개를 같은 질문의 세 관점으로 각각 평가합니다.
- 513개 속성 카탈로그에서 질문과 관련된 속성을 골라 사용합니다.
- 선택지마다 정확히 대응하는 속성이 있으면 실제 관측 매칭 수를 공통 출발점으로 사용합니다.
- 세 관점의 평균 득표율과 최솟값–최댓값 범위를 함께 보여줍니다.
- 관점이 바뀌어도 결과가 유지되는지 `stable` 또는 `contested`로 구분합니다.
- 같은 질문과 시드는 항상 같은 결과를 내며, 요청할 때만 새 시드로 다시 돌립니다.
- 전처리된 데이터는 ZSTD 압축 Parquet로 저장하고 embedded DuckDB의 인메모리 연결로 직접 조회합니다. 별도 DuckDB 데이터베이스 파일은 만들지 않습니다.

LLM은 질문을 해석하고 선언형 JSON 규칙과 설명을 작성합니다. 실제 집계는 저장소에 포함된 고정 스크립트가 수행하며, 질문별 코드를 생성하거나 실행하지 않습니다. 특정 LLM 제공자나 API에는 의존하지 않습니다.

## 설치

필요한 환경은 Python 3.12 이상, [uv](https://docs.astral.sh/uv/), 그리고 셸·파일 도구를 사용할 수 있는 Agent 런타임입니다.

### Codex

PowerShell:

```powershell
$target = Join-Path $HOME '.codex\skills\vh-poll'
git clone https://github.com/johwanghee/vh-poll.git $target
```

### OpenClaw

[OpenClaw 공식 문서](https://docs.openclaw.ai/skills)의 로컬 설치 명령을 사용합니다.

```bash
git clone https://github.com/johwanghee/vh-poll.git
openclaw skills install ./vh-poll --global
```

직접 관리하려면 저장소를 `~/.openclaw/skills/vh-poll` 또는 여러 Agent가 공유하는 `~/.agents/skills/vh-poll`에 둘 수도 있습니다.

### Hermes Agent

Hermes의 사용자 스킬 디렉터리에 복제합니다.

```bash
git clone https://github.com/johwanghee/vh-poll.git ~/.hermes/skills/vh-poll
```

이미 `~/.agents/skills`를 공유하고 있다면 `~/.hermes/config.yaml`에서 외부 디렉터리로 등록할 수 있습니다.

```yaml
skills:
  external_dirs:
    - ~/.agents/skills
```

설치 후 새 Agent 세션을 시작합니다. 런타임이 명시적 스킬 호출을 지원하면 `$vh-poll` 또는 `/vh-poll`처럼 해당 런타임의 호출 문법을 사용하고, 그렇지 않으면 자연어로 요청하면 됩니다.

```text
$vh-poll 김치 vs 백김치
/vh-poll 김치 vs 백김치
가상 페르소나에게 김치와 백김치 중 하나를 골라 달라고 해줘
```

다른 예:

```text
$vh-poll 여름휴가: 바다, 산, 도시 중 어디로 갈까?
$vh-poll 방금 결과를 다른 시드로 다시 돌려줘
$vh-poll 왜 이런 결과가 나왔는지 근거를 설명해줘
```

## 버전과 업데이트

이 프로젝트는 [Semantic Versioning](https://semver.org/)을 따릅니다. GitHub Release의 `vX.Y.Z` 태그가 검증된 공개 버전이며 `main`은 다음 릴리스를 위한 최신 개발 상태일 수 있습니다.

- 패치(`v0.1.1`): 호환되는 버그·문서 수정
- 마이너(`v0.2.0`): 규칙 스키마, 집계 방식 또는 출력 기능 변경
- 메이저(`v1.0.0`): 안정화 이후 호환되지 않는 변경

설치된 Git 저장소를 최신 공개 버전으로 업데이트하려면 다음 명령을 사용합니다. `<skill-directory>`에는 실제 설치 경로를 넣습니다.

```bash
git -C <skill-directory> fetch --tags
git -C <skill-directory> switch --detach v0.2.1
```

예를 들어 공용 설치 경로를 사용한다면:

```bash
git -C ~/.agents/skills/vh-poll fetch --tags
git -C ~/.agents/skills/vh-poll switch --detach v0.2.1
```

`main`의 최신 변경을 추적하려는 개발자는 다음처럼 전환합니다.

```bash
git -C <skill-directory> switch main
git -C <skill-directory> pull --ff-only
```

업데이트 후 새 Agent 세션을 시작하세요. Persona 데이터는 스킬 저장소 밖의 캐시에 있으므로 일반적인 스킬 업데이트에서는 다시 다운로드하지 않습니다.

## 첫 실행과 데이터

첫 투표 때 데이터가 없다면 스킬은 다운로드 크기와 저장 경로를 먼저 알리고 명시적인 동의를 구합니다. 원본 공개 릴리스는 10개 Parquet 샤드, 4,167,729,762바이트(약 3.88 GiB)이며 다운로드 후 무결성을 검사합니다. 이후 999,847개 행과 선택된 513개 속성을 로컬 ZSTD Parquet로 전처리합니다.

기본 저장 위치는 저장소 밖의 `~/.cache/vh-poll`입니다. 다른 위치를 쓰려면 환경 변수를 설정합니다.

```powershell
$env:VIRTUAL_HUMAN_POLL_DATA_DIR = 'D:\vh-poll-data'
```

데이터, 가상환경, 도구 캐시는 Git에 포함되지 않습니다. 상태 확인과 수동 준비가 필요하면 저장소 루트에서 다음 명령을 사용할 수 있습니다.

```powershell
$dataDir = if ($env:VIRTUAL_HUMAN_POLL_DATA_DIR) {
    $env:VIRTUAL_HUMAN_POLL_DATA_DIR
} else {
    Join-Path $HOME '.cache\vh-poll'
}
$env:UV_PROJECT_ENVIRONMENT = Join-Path $dataDir 'venv'
$env:UV_CACHE_DIR = Join-Path $dataDir 'uv-cache'

uv run python scripts/setup_data.py status
uv run python scripts/setup_data.py download
uv run python scripts/preprocess_personas.py
uv run python scripts/setup_data.py verify
```

macOS/Linux:

```bash
data_dir="${VIRTUAL_HUMAN_POLL_DATA_DIR:-$HOME/.cache/vh-poll}"
export UV_PROJECT_ENVIRONMENT="$data_dir/venv"
export UV_CACHE_DIR="$data_dir/uv-cache"

uv run python scripts/setup_data.py status
uv run python scripts/setup_data.py download
uv run python scripts/preprocess_personas.py
uv run python scripts/setup_data.py verify
```

`download`는 약 3.88 GiB의 외부 데이터를 받으므로 저장 공간과 [데이터 이용 조건](DATA_LICENSE_NOTICE.md)을 먼저 확인하세요. 데이터를 사용할 수 없으면 작은 데모 모드로 실행할 수 있지만, 이 경우 Persona 1M 집계가 아닌 LLM 설계 데모라고 표시됩니다.

## 결과를 읽는 법

스킬은 근거를 세 층으로 나눕니다.

| 구분 | 의미 |
| --- | --- |
| Persona 데이터에서 계산 | 직접 속성 매칭 수와 coverage, 득표율, 관점별 범위, 그룹별 개수와 변화량, 결측치 |
| 시나리오 가정 | 어떤 속성이 어느 선택지를 지지한다고 본 방향과 효과 크기 |
| 강건성 판단 | 세 관점에서 승자가 유지되는지, 여러 관점에 반복된 신호가 있는지 |

선택지마다 `sport_soccer`와 `sport_basketball`처럼 정확히 대응하는 속성이 있으면, 엔진은 각 선택지의 긍정적인 관심 값이 관측된 수를 정규화해 empirical prior로 사용합니다. 같은 직접 속성을 관점 효과에서 다시 사용하는 것은 검증기가 차단합니다. 정확한 대응 속성이 없으면 LLM이 작성한 fallback base score를 사용하며 이를 시나리오 가정이라고 표시합니다.

일부 선택지에만 직접 속성이 있으면 `hybrid-sensitivity` 모드를 사용합니다. 비대칭 직접 속성은 양쪽 계산에서 모두 제외하고, 공통 취향 적합도를 동일 prior에서 계산한 결과와 여러 단계의 인지도 prior 결과를 함께 냅니다. 1%p 미만 격차는 `near-tie`로 처리하며 모든 prior에서 같은 비접전 승자가 유지될 때만 `stable`, 그 외에는 `assumption-sensitive`로 표시합니다. 인지도 prior는 Persona 관측값이 아니라 공개된 LLM 시나리오 가정입니다.

기본 응답은 내부 용어와 모든 민감도 표를 나열하지 않습니다. `현실 인지도까지 넣으면`과 `이름표를 가리고 취향만 보면`의 두 결과를 짧게 대비하고, 가정이 승부를 갈랐는지 한 문장으로 설명합니다. 전체 시나리오 수치, 출발 확률, 효과 계수와 내부 판정은 사용자가 근거나 방법론을 요청할 때만 펼쳐 보여줍니다.

```text
⚽ 현실 인지도까지 넣으면 축구 우세입니다.
하지만 이름표를 가리고 취향만 보면 사실상 동률이에요.
족구가 취향에서 밀렸다기보다, 아는 사람 수에서 밀린 셈입니다. 🦶
```

그 밖의 속성과 선택지 연결 방향은 데이터에서 학습한 상관관계나 인과효과가 아닙니다. LLM이 질문별로 만든 명시적인 시나리오 가정입니다. 표시된 비율과 범위는 선언된 prior와 규칙을 전체 Persona 데이터에 적용해 계산한 값입니다. `expected` 모드의 `count`는 실제로 표를 던진 사람 수가 아니라 각 Persona의 선택 확률을 더한 **확률 합계 환산**입니다.

## 처리 구조

```text
질문
  → 관련 속성 카탈로그 선택
  → 직접 대응 속성이 있으면 관측 매칭 수로 prior 계산
  → 직접 속성이 비대칭이면 fit-only + 인지도 prior 민감도 계산
  → 서로 다른 3개 관점의 JSON 규칙 생성·검증
  → ZSTD Parquet를 embedded DuckDB로 집계
  → 평균, 범위, 그룹 차이, 강건성 설명
```

주요 파일:

- [`SKILL.md`](SKILL.md): 호환 Agent가 따르는 전체 워크플로
- [`scripts/`](scripts): 다운로드, 전처리, 검증, 집계 코드
- [`references/`](references): 규칙 스키마와 속성 카탈로그
- [`DATA_LICENSE_NOTICE.md`](DATA_LICENSE_NOTICE.md): Persona 1M 데이터 이용 조건 안내

직접 Python 의존성은 `duckdb`와 `huggingface-hub` 두 개로 제한합니다.

## 한계와 책임

- Persona 1M은 대표성 있는 모집단 표본이 아닙니다.
- 사람 기반 또는 모델 추출 속성도 검증된 사실이라고 보장되지 않습니다.
- 희소 속성과 결측치는 질문별 관측 범위를 달라지게 합니다.
- 정치·종교·인종·성별 등의 속성을 범죄성, 지능, 도덕성과 연결하는 용도로 사용하지 않습니다.
- 재미와 탐색을 위한 시뮬레이션이며 의사결정, 정책, 마케팅 조사나 사람 평가의 근거로 사용하면 안 됩니다.

## 라이선스

이 저장소는 MatrAIx Persona 1M 데이터를 포함하거나 재배포하지 않습니다. 공개 릴리스에는 하나의 포괄 라이선스가 적용되는 것이 아니라 각 원천 데이터의 라이선스와 조건이 유지됩니다. 다운로드나 결과물 배포 전 [`DATA_LICENSE_NOTICE.md`](DATA_LICENSE_NOTICE.md)와 [공식 데이터셋 카드](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release)를 확인하세요.

현재 이 저장소의 소스 코드에는 별도의 오픈소스 라이선스가 부여되어 있지 않습니다.
