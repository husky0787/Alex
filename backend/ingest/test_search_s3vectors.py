"""Live attributed-research search smoke; invokes AWS services."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from research_chain import search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="market outlook")
    parser.add_argument("--expected-id", help="Fail unless this known research ID is retrieved")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
    results = search(args.query)
    print(json.dumps({"status": "available" if results else "unavailable", "results": results}, indent=2))
    if not results or (args.expected_id and not any(r["id"] == args.expected_id for r in results)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
