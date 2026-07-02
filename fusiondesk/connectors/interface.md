# FusionDesk Connector Interface

Every connector exposes the same high-level contract.

## Required Connector Methods

```json
{
  "health": {
    "description": "Return connector availability and missing configuration.",
    "input": {},
    "output": {
      "ok": true,
      "status": "ready",
      "missing_config": []
    }
  },
  "capabilities": {
    "description": "Return supported capabilities and actions.",
    "input": {},
    "output": {
      "capabilities": []
    }
  },
  "invoke": {
    "description": "Run one connector capability through a normalized request envelope.",
    "input": {
      "capability": "string",
      "action": "string",
      "input": {},
      "context": {}
    },
    "output": {
      "ok": true,
      "data": {},
      "evidence": [],
      "warnings": [],
      "cost": {}
    }
  }
}
```

## Engine Boundary

The orchestration engine must call connectors through `invoke`. It should not call provider SDKs, repo scripts, browser tooling, filesystem commands, or hosted APIs directly.

## Connector Response Rules

- `ok` reports whether the connector action completed successfully.
- `data` contains normalized results.
- `evidence` contains source URLs, local file paths, timestamps, IDs, or logs used to support the result.
- `warnings` contains risk, missing-auth, rate-limit, partial-result, or unsupported-source notes.
- `cost` contains token, credit, request, runtime, or cloud spend estimates when available.

