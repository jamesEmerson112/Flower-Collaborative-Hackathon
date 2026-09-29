---
tags: [agentapp, research, connectors]
dataset: []
framework: [flower]
---

# Collaborative Flower Agent

A Flower `AgentApp` that researches public sources using `web_search` and
`web_fetch`. It uses the OpenAI SDK through Flower's runtime endpoint, keeps
conversation context, limits tool use to two rounds by default, and uses
`openai/gpt-5.6-sol`.

## Setup

Requirements: Python 3.11+, `uv`, and a SuperGrid account with Flower Agent
access.

Flower injects the runtime URL and credential when the AgentApp starts, so no
model-provider API key needs to be added to this project.

```shell
cd collaborative-agent
uv sync
uv run flwr build
uv run flwr login supergrid
```

## Run

```shell
uv run flwr run . supergrid --stream
```

Override the prompt for one run:

```shell
uv run flwr run . supergrid \
  --run-config 'agent.input="Compare two recent explanations of federated AI."' \
  --stream
```

Defaults are defined in `pyproject.toml`. You can also override `agent.model`
or `agent.max-tool-turns`; the tool-turn value must be between 0 and 10.

If a run fails, inspect it with:

```shell
uv run flwr list supergrid
uv run flwr log <run-id> supergrid --show
```

For more details please read the
[collaborative agent tutorial](https://flower.ai/docs/agent/tutorials/build-a-collaborative-agent.html).
