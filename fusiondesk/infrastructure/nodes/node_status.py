import json
from pathlib import Path

REGISTRY = Path(__file__).with_name("registry.json")

def load_nodes():
    return json.loads(REGISTRY.read_text())["nodes"]

def main():
    for node in load_nodes():
        print(f"{node['id']} | {node['status']} | {node['role']}")

if __name__ == "__main__":
    main()
