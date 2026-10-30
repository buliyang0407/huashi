"""Verify every declared animation file, then atomically activate the snapshot."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from huashi.animation_catalog import activate_snapshot
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--animation-root',type=Path,required=True);p.add_argument('--snapshot-id',required=True);p.add_argument('--state-path',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args();print(json.dumps(activate_snapshot(a.animation_root,a.snapshot_id,a.state_path,a.dry_run),ensure_ascii=False,indent=2))
