"""Read all material originals; stream additive thumbnails and index as tar, never overwrite sources."""
from pathlib import Path
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageOps
import io,json,hashlib,sys,tarfile,time,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from huashi.portrait_studio import PortraitStudio
def write_bundle(app_root,output):
    app_root=Path(app_root)
    rows=json.loads((app_root/'web/portrait-materials.json').read_text());old={m['id']:m for m in PortraitStudio(app_root/'promptscreation').scan_materials()}
    def build(m):
     u=unquote(m['image'])
     if u.startswith('/api/portrait/material-image/'):p=(app_root/'promptscreation')/old[u.rsplit('/',1)[-1]]['rel_path']
     elif u.startswith('/pose-files/'):p=(app_root/'pose')/u.removeprefix('/pose-files/')
     elif u.startswith('/face-files/'):p=(app_root/'data/faces')/u.removeprefix('/face-files/')
     else:raise ValueError(u)
     with Image.open(p) as im:
      im=ImageOps.exif_transpose(im);im.thumbnail((480,480));b=io.BytesIO();im.convert('RGB').save(b,'WEBP',quality=76,method=3)
     data=b.getvalue();name=hashlib.sha256(data).hexdigest()+'.webp';m={**m,'thumbnail':'/portrait-thumbs/'+name}
     return m,data,p.stat().st_size
    original_bytes=thumb_bytes=0;out=[];seen=set();start=time.monotonic()
    with tarfile.open(fileobj=output,mode='w|') as tar:
     def add(name,b):
      info=tarfile.TarInfo(name);info.size=len(b);info.mode=0o644;tar.addfile(info,io.BytesIO(b))
     with ThreadPoolExecutor(max_workers=2) as pool:
      for i,(m,b,size) in enumerate(pool.map(build,rows),1):
       if m['thumbnail'] not in seen:add(m['thumbnail'].lstrip('/'),b);seen.add(m['thumbnail'])
       out.append(m);original_bytes+=size;thumb_bytes+=len(b)
       if i%1000==0:print('thumbnails '+str(i)+'/'+str(len(rows)),file=sys.stderr,flush=True)
     add('portrait-materials.json',json.dumps(out,ensure_ascii=False).encode())
     report={'count':len(out),'unique_thumbnails':len(seen),'original_bytes':original_bytes,'thumbnail_bytes':thumb_bytes,'seconds':round(time.monotonic()-start,2)}
     add('thumbnail-report.json',json.dumps(report).encode())
    
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--app-root",type=Path,default=Path("/app"));args=parser.parse_args();write_bundle(args.app_root,sys.stdout.buffer)
