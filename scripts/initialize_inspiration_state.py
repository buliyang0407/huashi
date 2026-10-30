"""Explicit maintenance initialization; never called from a normal GET."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from huashi.inspiration_state import initialize_state
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--path',type=Path,required=True);args=p.parse_args();initialize_state(args.path);print('Initialized independent inspiration state:',args.path)
