# Flower Collaborative Hackathon: Reference

The organizers' brief, arranged for quick lookup. Captured 2026-09-29; the brief may be revised later.
Slack: **#hackathon_stanford_2026** (organizers post updates here during the day).

---

## The challenge: Flower Agent Harness

**Goal:** Show how Flower Agents collaborate on **SuperGrid**. Use the existing SuperGrid infrastructure to show several Flower Agents working together. They should solve problems, coordinate tasks, and achieve more than one agent could on its own.

**Suggested shapes:**
- **Agent chain:** several agents each add to a single result.
- **Multiple `AgentApp`s** that **share context** and **hand work** between agents.

**Bonus points:** use Flower's recently released **Endeavor** model.

---

## Support during the day

- Mentors are available all day for setup, ideas and technical questions.
- Ask in Slack (#hackathon_stanford_2026) or talk to any Flower Labs team member in person.

---

## Starting templates

| Template | What it gives you |
|---|---|
| **Flower AgentApp** | Receives the current prompt plus the conversation's previous user and assistant messages. |
| **Flower Collaborative AgentApp** | Comes with **Grid tools** enabled. Agents can **sample other agents** in a federation, **send messages** to them and **retrieve their responses**. |

*Our read (not from the brief):* the Collaborative AgentApp is the natural base for this challenge because its Grid tools handle the agent-to-agent part.

A GitHub repo explains how to run it across Flower SuperNodes (see [Links](#links-to-fill-in)).

---

## Configuring a SuperNode's model endpoint

A SuperNode needs these environment variables to reach a model provider.

### Option A: models served via Flower AI

```bash
export FLWR_MODEL_API_KEY="<YOUR-FLOWER-API-KEY>"
```

- Get the key on flower.ai under **Profile → Settings → API Keys**.
- Model names use the **OpenRouter format**, e.g. `openai/gpt-5.6-sol`.
- The brief lists only the key here and no endpoint variable.

### Option B: models served via the Nebius Token Factory

```bash
export FLWR_MODEL_API_ENDPOINT="https://api.tokenfactory.tf-ca1.nebius.com/v1/responses"
export FLWR_MODEL_API_KEY="<NEBIUS-API-KEY>"
```

- Organizers will share `<NEBIUS-API-KEY>` in the Slack channel during the hackathon.

> **Key hygiene (our note, not from the brief):** keep real keys in a local `.env` (or your shell) and never commit them.
> The root `.gitignore` covers `.env`, key files, `.venv/` and `*.fab`.

---

## Links to fill in

The original brief linked these items, but the URLs were lost when it was copied. Fill them in from the organizers' page or Slack:

- [ ] GitHub repo: running the Flower Collaborative AgentApp across Flower SuperNodes: `<URL>`
- [ ] Spinning up a Flower SuperNode on a Nebius Serverless AI endpoint: `<URL>`
- [ ] Nebius Token Factory available endpoints: `<URL>`

Related links found since (not from the brief):

- Collab agent recipe on Flower Hub: https://flower.ai/apps/flwrlabs/hackathon-collab-agent-recipe (notes: [collab-agent-recipe.md](collab-agent-recipe.md))
- Collaborative AgentApp (Grid tools enabled) on Flower Hub: https://flower.ai/apps/flwrlabs/collaborative-agent (notes: [collaborative-agent.md](collaborative-agent.md))
- Minimal AgentApp on Flower Hub: https://flower.ai/apps/flwrlabs/agent (notes: [flwrlabs-agent.md](flwrlabs-agent.md))
- **Robot-parts supplier dataset** (8 stores, 95 items, captured 2026-09-29; candidate supplier catalogues): [robot-parts-stores/](robot-parts-stores/README.md) · open `robot-parts-stores/index.html` locally
- **What a SuperNode can be** (28 Hub apps studied: roles, hardware, data platforms, privacy): [supernode-scope/](supernode-scope/README.md)
- **Flower Concept Map** (App vs Agent vs SuperNode vs Federation, interactive): https://claude.ai/artifact/Eyr5RcuZdx2yj6MQ57BtyC
- **SuperGrid setup** (federation, invites, SuperNodes, running the master): [supergrid-setup.md](supergrid-setup.md)
- **AgentApp API reference** (team dev reference, read from flwr 1.39.0): [agentapp-api-reference.md](agentapp-api-reference.md) · artifact: https://claude.ai/artifact/VBUJjr3bLg9HD4BCupWUtp
- **AgentApp Trace Explorer** (animated walkthrough of the three apps): https://claude.ai/artifact/JdSfEoJszLETaSR14tuP8Y
- **Head Office & Stores** (3D explainer for non-technical audiences): https://claude.ai/artifact/ECUTCW4bZEcUaYPMwCXRLa
- All artifacts are private until shared from their page's Share menu.
- Collaborative agent tutorial (linked from the recipe README; **404 as of 2026-09-29**): https://flower.ai/docs/agent/tutorials/build-a-collaborative-agent.html
- AgentApp runtime explainer (live): https://flower.ai/docs/agent/explanations/agentapp-runtime.html

---

## Open questions to ask mentors

- What is the exact model identifier for **Endeavor**, and is it served via Flower AI, Nebius or both?
- Which Nebius Token Factory models work well for multi-agent / tool-calling use?
