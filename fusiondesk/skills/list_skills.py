import json

with open("fusiondesk/skills/registry.json") as f:
    skills = json.load(f)["skills"]

print("\n=== FUSIONDESK SKILLS ===\n")

for s in skills:
    print(f"{s['name']}")
    print(f"  ID: {s['id']}")
    print(f"  Category: {s['category']}")
    print(f"  Status: {s['status']}")
    print(f"  Capabilities: {', '.join(s['capabilities'])}")
    print()
