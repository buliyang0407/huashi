"""Create a new offline editorial snapshot; never fetch video or change the active pointer."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from huashi.animation_cards import prepare_cards

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-snapshot', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--curation', type=Path, default=Path(__file__).resolve().parents[1] / 'huashi/animation-card-curation.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare_cards(args.base_snapshot, args.output_root, json.loads(args.curation.read_text()), args.dry_run), ensure_ascii=False, indent=2))
