"""Stream only manifest-approved animation resources, including byte-range video reads."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit,unquote

class InspirationMedia:
    def __init__(self,root):self.root=Path(root).absolute();self.cache={}
    def resolve(self,raw):
        path=unquote(urlsplit(raw).path)
        match=re.fullmatch(r'/inspiration-media/([A-Za-z0-9_-]{1,80})/(posters|previews)/([A-Za-z0-9_-][A-Za-z0-9_.-]{0,160})',path)
        if not match or '%' in path:return None
        snapshot,folder,name=match.groups();relative=folder+'/'+name;snap=self.root/'snapshots'/snapshot;manifest=snap/'manifest.json';target=snap/relative
        if any(p.is_symlink() for p in [target,manifest,*target.parents,*manifest.parents]):return None
        try:
            s=manifest.stat();stamp=(s.st_mtime_ns,s.st_size);cached=self.cache.get(snapshot)
            if cached is None or cached[0]!=stamp:
                data=json.loads(manifest.read_text())
                if data.get('snapshot_id')!=snapshot:return None
                approved={r['path']:r for r in data.get('resources',[]) if isinstance(r,dict) and isinstance(r.get('path'),str)};cached=(stamp,approved);self.cache[snapshot]=cached
            resource=cached[1].get(relative)
            if resource is None or resource.get('mime') not in {'video/mp4','image/webp','image/png','image/jpeg','image/avif'} or not target.is_file() or target.stat().st_size!=resource['bytes']:return None
            return target,resource
        except (OSError,KeyError,ValueError,TypeError):return None
    def handle(self,h):
        if not urlsplit(h.path).path.startswith('/inspiration-media/'):return False
        found=self.resolve(h.path)
        if found is None:
            h.send_response(404);h.send_header('Content-Length','0');h.end_headers();return True
        path,resource=found;size=resource['bytes'];start=0;end=size-1;partial=False;header=h.headers.get('Range','')
        if header.startswith('bytes=') and ',' not in header:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
            try:
                if not match or not any(match.groups()) or size==0:raise ValueError()
                a,b=match.groups()
                if a:start=int(a);end=min(int(b),size-1) if b else size-1
                else:
                    suffix=int(b)
                    if suffix<=0:raise ValueError()
                    start=max(0,size-suffix);end=size-1
                if start>=size or start>end:raise ValueError()
                partial=True
            except ValueError:
                h.send_response(416);h.send_header('Accept-Ranges','bytes');h.send_header('Content-Range',f'bytes */{size}');h.send_header('Content-Length','0');h.end_headers();return True
        try:
            with path.open('rb') as source:
                h.send_response(206 if partial else 200);h.send_header('Content-Type',resource['mime']);h.send_header('Content-Length',str(max(0,end-start+1)));h.send_header('Accept-Ranges','bytes');h.send_header('Cache-Control','public, max-age=3600');h.send_header('X-Content-Type-Options','nosniff')
                if partial:h.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                h.end_headers()
                if h.command=='HEAD':return True
                source.seek(start);remaining=max(0,end-start+1)
                while remaining:
                    data=source.read(min(256*1024,remaining))
                    if not data:break
                    h.wfile.write(data);remaining-=len(data)
        except (BrokenPipeError,ConnectionResetError):pass
        return True
