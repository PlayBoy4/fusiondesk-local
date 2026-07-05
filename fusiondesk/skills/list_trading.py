import json

with open("fusiondesk/skills/trading_registry.json") as f:
    skills = json.load(f)["skills"]

print("\n=== TRADEMASTER REGISTRY ===\n")

for s in skills:
    print(f"{s['name']}")
    print(f"  ID: {s['id']}")
    print(f"  Status: {s['status']}")
    print(f"  Capabilities: {', '.join(s['capabilities'])}")
    print()
