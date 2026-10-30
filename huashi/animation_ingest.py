"""Poster-only maintenance; preserve archived videos. Source scripts are never executed."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,html,json,os,re,subprocess,threading,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from .animation_catalog import encoded

class MediaDownloader:
    def __init__(self,root,budget):
        self.root=Path(root).resolve();self.budget=budget;self.lock=threading.Lock();self.used=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
    def request(self,url,method='GET',headers=None):
        if not url.startswith(('https://','http://')):raise ValueError('Unsupported URL')
        return urlopen(Request(url,method=method,headers={'User-Agent':'Huashi-reference-archive/1.0',**(headers or {})}),timeout=35)
    def metadata(self,url,referer=''):
        headers={'Referer':referer} if referer else {}
        try:
            with self.request(url,'HEAD',headers) as r:
                size=r.headers.get('Content-Length')
                if size and int(size)>0:return {'bytes':int(size),'mime':r.headers.get('Content-Type'),'etag':r.headers.get('ETag'),'method':'head'}
        except (OSError,ValueError,HTTPError):pass
        with self.request(url,headers={**headers,'Range':'bytes=0-0'}) as r:
            match=re.search(r'/(\d+)$',r.headers.get('Content-Range',''));size=int(match[1]) if match else int(r.headers.get('Content-Length') or 0);r.read(1)
            return {'bytes':size or None,'mime':r.headers.get('Content-Type'),'etag':r.headers.get('ETag'),'method':'range'}
    def fetch(self,url,path,expected=None,known_sha=None,max_file=134217728,referer='',required_content_prefix=None):
        path=Path(path).absolute()
        if not path.is_relative_to(self.root) or any(p.is_symlink() for p in [path,*path.parents]):raise ValueError('Unsafe destination')
        if path.exists():
            if known_sha and hashlib.sha256(path.read_bytes()).hexdigest()==known_sha:return {'status':'verified-existing','bytes':path.stat().st_size,'sha256':known_sha}
            raise FileExistsError('Unknown file already exists')
        if expected and (expected>max_file or expected+self.used>self.budget):raise ValueError('File or total budget exceeded')
        path.parent.mkdir(parents=True,exist_ok=True);part=Path(str(path)+'.part');written=0;start=time.monotonic()
        if part.exists():
            with self.lock:self.used-=part.stat().st_size
            part.unlink()  # Restart safely rather than concatenate potentially changed remote versions.
        try:
            with self.request(url,headers={'Referer':referer} if referer else {}) as r,part.open('xb') as f:
                content_type=r.headers.get('Content-Type','');h=hashlib.sha256()
                if required_content_prefix and not content_type.lower().startswith(required_content_prefix):raise ValueError('Refuse non-image response before reading body')
                for chunk in iter(lambda:r.read(256*1024),b''):
                    if time.monotonic()-start>180:raise TimeoutError('File download deadline exceeded')
                    with self.lock:
                        if self.used+len(chunk)>self.budget or written+len(chunk)>max_file:raise ValueError('File or total budget exceeded')
                        self.used+=len(chunk);written+=len(chunk)
                    f.write(chunk);h.update(chunk)
                if not written or expected and written!=expected:raise ValueError('Downloaded length does not match metadata')
            os.replace(part,path);return {'status':'downloaded','bytes':written,'sha256':h.hexdigest(),'content_type':content_type}
        except Exception:
            if part.exists():part.unlink()
            with self.lock:self.used-=written
            raise


def inspect_asset(path,kind):
    if kind=='poster':
        from PIL import Image
        try:
            with Image.open(path) as image:
                image.load();w,h=image.size
                if min(w,h)<16 or max(w,h)>12000:raise ValueError('Poster dimensions indicate placeholder')
                rgb=image.convert('RGB');extrema=rgb.getextrema()
                if all(high-low<4 for low,high in extrema):raise ValueError('Uniform placeholder poster')
                mime=Image.MIME.get(image.format,'')
                if mime not in {'image/jpeg','image/png','image/webp','image/avif'}:raise ValueError('Unsupported poster type')
                return {'mime':mime,'width':w,'height':h}
        except Exception as e:raise ValueError('Invalid or placeholder poster: '+str(e)) from e
    p=subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,timeout=25)
    if p.returncode:raise ValueError('ffprobe rejected video')
    data=json.loads(p.stdout);video=next((s for s in data.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not video or 'mp4' not in data.get('format',{}).get('format_name',''):raise ValueError('Not an MP4 video')
    return {'mime':'video/mp4','duration_seconds':float(data['format']['duration']),'codec':video.get('codec_name'),'width':video.get('width'),'height':video.get('height'),'audio':any(s.get('codec_type')=='audio' for s in data['streams'])}


def require_unpublished(snapshot):
    snapshot=Path(snapshot).resolve();active=snapshot.parent.parent/'active.json'
    if active.is_file() and json.loads(active.read_text()).get('snapshot_id')==snapshot.name:
        raise FileExistsError('An active snapshot is immutable; prepare a new snapshot instead')


def prepare_media_plan(snapshot):
    """Plan only poster downloads. Video demos stay as external viewing links."""
    require_unpublished(snapshot)
    snapshot=Path(snapshot);manifest=json.loads((snapshot/'manifest.json').read_text())
    assets=[a for a in manifest.get('planned_assets',[]) if a.get('type')=='poster']
    plan={'snapshot_id':manifest['snapshot_id'],'assets':assets,'discovery_errors':[],
          'known_video_bytes':0,'source_bytes_before_media':sum(p.stat().st_size for p in snapshot.rglob('*') if p.is_file()),
          'unknown_video_lengths':[],'video_policy':'external-links-only-preserve-existing',
          'selection_rule':'Preserve existing media; download original posters only. Do not fetch video pages or video bodies.'}
    (snapshot/'media-plan.json').write_bytes(encoded(plan));return plan


def fetch_media(snapshot,budget=1_000_000_000):
    require_unpublished(snapshot)
    snapshot=Path(snapshot).resolve();manifest=json.loads((snapshot/'manifest.json').read_text());catalog=json.loads((snapshot/'catalog.json').read_text());plan=json.loads((snapshot/'media-plan.json').read_text());existing={r['asset_id']:r for r in manifest.get('resources',[])}
    if any(a.get('type')!='poster' for a in plan['assets']):raise ValueError('Video downloads are disabled; rebuild a poster-only plan')
    for r in existing.values():
        rel=Path(r['path']);p=snapshot/rel
        if rel.is_absolute() or '..' in rel.parts or any(x.is_symlink() for x in [p,*p.parents]) or not p.is_file() or p.stat().st_size!=r['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Existing media failed verification; preserve manifest and investigate')
    baseline=sum(p.stat().st_size for p in snapshot.rglob('*') if p.is_file() and p.parts[-2] not in {'previews','posters'})
    if plan['known_video_bytes']+baseline>budget:raise ValueError('Mandatory media selection exceeds budget; revise selection explicitly before download')
    downloader=MediaDownloader(snapshot,budget);resources=list(existing.values());errors=[];completed=0
    def one(a):
        old=existing.get(a['id']);relative=(old or {}).get('path') or ('previews/' if a['type']=='video' else 'posters/')+a['id']+('.mp4' if a['type']=='video' else '.webp');p=snapshot/relative
        last=None
        for attempt in range(2):
            try:
                raw=downloader.fetch(a['source_url'],p,expected=a.get('expected_bytes'),known_sha=(old or {}).get('sha256'),max_file=4194304,referer=a.get('referer') or 'https://skillry.dev/',required_content_prefix='image/')
                try:details=inspect_asset(p,a['type'])
                except Exception:
                    with downloader.lock:downloader.used-=p.stat().st_size
                    p.unlink();raise
                if a.get('github_digest') and a['github_digest'].startswith('sha256:') and a['github_digest'][7:]!=raw['sha256']:raise ValueError('GitHub release digest mismatch')
                return {**a,**raw,**details,'path':relative,'asset_id':a['id']}
            except Exception as e:last=e
        raise ValueError(str(last))
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(one,a):a for a in plan['assets']}
        for job in as_completed(jobs):
            try:
                resource=job.result();resources=[r for r in resources if r['asset_id']!=resource['asset_id']];resources.append(resource)
            except Exception as e:errors.append({'asset_id':jobs[job]['id'],'source_url':jobs[job]['source_url'],'error':str(e)})
            completed+=1
            if completed%25==0:print(json.dumps({'completed':completed,'total':len(jobs),'download_bytes_so_far':downloader.used,'errors':len(errors)}),flush=True)
            # Persist progress for hash-verified restarts, not only at the end.
            manifest['resources']=sorted(resources,key=lambda r:r['asset_id']);(snapshot/'manifest.json').write_bytes(encoded(manifest))
    by_asset={r['asset_id']:r for r in resources};by_entry={e['id']:e for e in catalog['entries']}
    for e in catalog['entries']:
        poster=by_asset.get(e.get('poster_asset_id'))
        if poster:
            e['thumbnail']=e['thumbnail_url']='/inspiration-media/'+manifest['snapshot_id']+'/'+poster['path']
            e['cover_status']='archived-original'
        for media in e['media']:
            aid=media.get('asset_id')
            if not aid and e['id'].startswith('animation:awesome:') and media['role']=='original':aid='awesome-'+e['id'].split(':',2)[2]
            resource=by_asset.get(aid)
            if resource:media.update(url='/inspiration-media/'+manifest['snapshot_id']+'/'+resource['path'],availability='local',mime=resource['mime'],bytes=resource['bytes'],file_duration_seconds=resource['duration_seconds'],duration_seconds=media.get('duration_seconds') or resource['duration_seconds'])
        e['playable']=any(m['availability']=='local' for m in e['media'])
        e['duration_seconds']=e.get('duration_seconds') or next((m.get('duration_seconds') for m in e['media'] if m.get('duration_seconds')),None)
    manifest['resources']=sorted(resources,key=lambda r:r['asset_id']);manifest['media_errors']=errors
    for p in sorted((snapshot/'sources/awesome-pages').glob('*.html')):
        rel=p.relative_to(snapshot).as_posix()
        if not any(f['path']==rel for f in manifest['source_files']):manifest['source_files'].append({'path':rel,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (snapshot/'manifest.json').write_bytes(encoded(manifest));(snapshot/'catalog.json').write_bytes(encoded(catalog));report={'resources':len(resources),'videos':sum(r['type']=='video' for r in resources),'posters':sum(r['type']=='poster' for r in resources),'errors':errors,'local_entries':sum(e['playable'] for e in catalog['entries']),'external_only_entries':sum(not e['playable'] for e in catalog['entries']),'published_resource_bytes':sum(r['bytes'] for r in resources),'total_snapshot_bytes':sum(p.stat().st_size for p in snapshot.rglob('*') if p.is_file()),'budget_bytes':budget}
    (snapshot/'media-report.json').write_bytes(encoded(report));return report
