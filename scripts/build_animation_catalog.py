"""Build a new immutable animation metadata snapshot from pinned local source files."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from huashi.animation_catalog import build_catalog
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args();print(json.dumps(build_catalog(a.source_root,a.output_root,a.dry_run),ensure_ascii=False,indent=2))
