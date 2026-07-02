# FusionDesk AI Architecture

FusionDesk AI is organized around two extension points:

- Skills: plugin-style capability definitions that can be selected by intent.
- Connectors: tool adapters that expose external systems through one common interface.

The orchestration engine should only depend on these contracts. It should not import or hardcode TradeMaster, OpenRouter, Polygon.io, RunPod, Agent Reach, or any other external tool directly.

## Layout

- `skills/skill.schema.json`: required fields for every callable skill.
- `skills/registry.json`: initial FusionDesk skill registry.
- `core/registry.py`: loader for skills and connector manifests.
- `core/connectors.py`: Python protocol for connector implementations.
- `core/seats.py`: dynamic model-seat assignment engine.
- `models/profiles.json`: model capability profiles used by the seat selector.
- `connectors/interface.md`: connector contract for the core engine.
- `connectors/registry.json`: initial connector manifest.
- `modules/trademaster/manifest.json`: TradeMaster module metadata. This keeps trading workflows plugin-scoped.
- `modules/social_studio/manifest.json`: Social Studio module metadata for social strategy, content, approval, scheduling, publishing, and analytics workflows.
- `references/tool-notes.json`: notes for repos and tools discussed so far.

## Core Rule

The core engine asks for capabilities by skill and connector contracts:

```text
user intent -> skill registry lookup -> orchestration mode -> connector capability calls -> final response
```

That means new modules such as Business, Marketing, Development, Research, TradeMaster, Social Studio, and AI Arbitrage can be added without changing core orchestration logic.

## Validation

Run:

```bash
python3 scripts/validate_fusiondesk_registry.py
```

Expected output:

```text
FusionDesk registry OK: 60 skills, 13 connectors, 9 model profiles
```

Phase 5 adds dynamic seat assignment. The selector takes a task, skill, execution mode, available models, connector needs, cost preference, and quality preference, then returns structured JSON with selected seats, models, reasons, connectors, estimated cost tier, and confidence.
