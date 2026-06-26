import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.story_eval import load_golden_dataset, validate_golden_dataset


def main() -> int:
    cases = load_golden_dataset()
    result = validate_golden_dataset(cases)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
