import json
from pathlib import Path

REGISTRY = Path(__file__).with_name("registry.json")


def load_nodes():
    return json.loads(REGISTRY.read_text())["nodes"]


def main():
    print("\n=== FusionDesk Node Registry ===\n")

    for node in load_nodes():
        print(f"Node:         {node['name']}")
        print(f"ID:           {node['id']}")
        print(f"Role:         {node['role']}")
        print(f"Status:       {node['status']}")
        print(f"Online:       {node['online']}")
        print(f"Location:     {node['location']}")
        print(f"Connection:   {node['connection']}")
        print(f"GPU:          {node['gpu']}")
        print(f"Cost/hr:      ${node['cost_per_hour']}")
        print(f"Capabilities: {', '.join(node['capabilities'])}")
        print()


if __name__ == "__main__":
    main()
