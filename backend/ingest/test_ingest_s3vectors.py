"""Live ingestion smoke: supply an attributed document; invokes AWS services."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from research_chain import ingest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, required=True,
                        help="JSON document with text, research_id, topic and captured sources; see backend/research/README.md")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
    result = ingest(json.loads(args.document.read_text(encoding="utf-8-sig")))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
