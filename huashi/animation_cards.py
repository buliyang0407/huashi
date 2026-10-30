"""Offline editorial metadata snapshots; original sources and archived media stay intact."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from .animation_catalog import encoded, sha


FEATURES = [
    (r'morph|形态|変身|连续变形', '连续变形', '让同一图形在多个状态间连续变换'),
    (r'kinetic typ|typography|タイポグラフィ|动态文字|文字编排', '动态文字', '用文字的位置、尺度和节奏组织信息'),
    (r'beat|BPM|sync|卡点|踩拍|同期', '音乐同步', '让动作或转场与音乐节拍同步'),
    (r'particle|粒子', '粒子效果', '用粒子的聚散或流动组织画面'),
    (r'hand.drawn|doodle|手绘|手描|线描|白描', '手绘质感', '以手绘线条或涂鸦表达画面'),
    (r'pixel.art|pixelated|像素|ピクセル', '像素风', '以像素画面呈现角色或场景'),
    (r'paper.(?:cut|texture|grain|collage)|origami|collage|剪纸|折纸|コラージュ', '纸艺拼贴', '借助纸张、剪影或拼贴组织视觉层次'),
    (r'claymation|stop.motion|定格|黏土', '定格质感', '采用黏土或逐格停顿的运动质感'),
    (r'physics|collision|物理|碰撞', '物理运动', '通过运动或碰撞规则表现对象之间的关系'),
    (r'interactive|playable|controls|game|交互|游戏|ゲーム', '可交互', '让观众通过操作探索画面或规则'),
    (r'explainer|explain|讲解|科普|解説', '概念讲解', '把概念或过程拆成便于理解的视觉步骤'),
    (r'data.?viz|visualization|real data|统计|数据可视化|图表', '数据可视化', '将数据或结构关系转化为可观察的变化'),
    (r'one shot|no cuts|never cut|一镜到底', '连续镜头', '在连续镜头中完成场景或尺度变化'),
    (r'zoom|camera (?:move|motion|push|orbit|pan|cut)|镜头(?:推|移|旋|切)|カメラ', '镜头运动', '利用镜头移动或景别变化引导注意力'),
    (r'looping|\bloop\b(?! transformers)|循环(?:动画|观看|结构)|ループ', '循环结构', '安排可以循环观看的动作或时间结构'),
    (r'CRT|glitch|故障|グリッチ', '复古故障', '借助屏幕或故障视觉营造复古气氛'),
    (r'glass (?:material|shader|product)|refraction|玻璃|折射', '玻璃与折射', '通过透明材质与光线变化表现空间'),
    (r'procedural|程序化|代码生成', '程序化构建', '以代码规则构建物体、纹理或场景'),
]


def viewing_links(entry):
    result = {}
    for media in entry.get('media', []):
        url = media.get('external_url', '')
        if urlsplit(url).scheme not in {'http', 'https'} or not urlsplit(url).netloc:
            continue
        record = result.setdefault(url, {'url': url, 'roles': []})
        if media.get('role', 'original') not in record['roles']:
            record['roles'].append(media.get('role', 'original'))
    original = entry.get('original', {})
    for url in [original.get('post_url'), original.get('skillry_url')]:
        if url and urlsplit(url).scheme in {'http', 'https'} and urlsplit(url).netloc:
            result.setdefault(url, {'url': url, 'roles': ['source']})
    if not result:
        for url in entry.get('source_urls', []):
            if urlsplit(url).scheme in {'http', 'https'} and urlsplit(url).netloc:
                result.setdefault(url, {'url': url, 'roles': ['reference']})
                break
    return list(result.values())


def describe(entry, notes):
    text = '\n'.join(str(x) for x in [entry.get('source_description', entry.get('description', '')), entry.get('prompts', {}).get('original', ''), entry.get('production_notes', '')])
    # A source mentioning a technique is evidence for a tag, not proof of a verified finished film.
    selected = [(label, detail) for pattern, label, detail in FEATURES if re.search(pattern, text, re.I)]
    title = notes.get('title') or entry['title']
    description = notes.get('description')
    if not description:
        if entry.get('source') == 'lemo-opuscar':
            description = entry.get('description') or entry.get('prompts', {}).get('zh', '')
        elif entry.get('source') == 'opus-video-prompts':
            description = entry.get('description') or entry.get('production_notes', '').removeprefix('上游说明：').split('\n')[0]
        if not description:
            detail = '；'.join(x[1] for x in selected[:2])
            description = ('围绕“' + title + '”，' + detail + '。') if detail else ('以“' + title + '”为参考，收录来源中的制作思路和表达要求。')
    description = re.sub(r'\s+', ' ', description).strip()
    if len(description) > 230:
        description = description[:230].rsplit('。', 1)[0] + '。'
    return title, description, notes.get('feature_tags') or [x[0] for x in selected[:4]] or [entry.get('category') or '制作参考']


def prepare_cards(base_snapshot, output_root, curation, dry_run=False):
    base = Path(base_snapshot).resolve()
    output = Path(output_root).absolute()
    if output.exists():
        raise FileExistsError('Existing snapshot cannot be overwritten')
    if output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('Source and destination snapshots must not overlap')
    if any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError('Unsafe snapshot output')
    if any(p.is_symlink() for p in base.rglob('*')):
        raise ValueError('Source snapshot contains symlinks')
    catalog = json.loads((base / 'catalog.json').read_text())
    manifest = json.loads((base / 'manifest.json').read_text())
    old_id = catalog['snapshot_id']
    digest = sha(encoded({'base_catalog': sha((base / 'catalog.json').read_bytes()), 'curation': curation, 'feature_rules': FEATURES, 'schema': 1}))
    new_id = 'code-cards-' + digest[:12]
    known = {e['id'] for e in catalog['entries']}
    if set(curation.get('entries', {})) - known:
        raise ValueError('Curation contains unknown stable IDs')
    for row in manifest.get('resources', []) + manifest.get('source_files', []):
        rel = Path(row['path'])
        p = base / rel
        if rel.is_absolute() or '..' in rel.parts or not p.is_file() or p.stat().st_size != row['bytes'] or sha(p.read_bytes()) != row['sha256']:
            raise ValueError('Base archive verification failed: ' + str(rel))
    catalog = copy.deepcopy(catalog)
    for e in catalog['entries']:
        notes = curation.get('entries', {}).get(e['id'], {})
        prompt_hash = sha(e.get('prompts', {}).get('original', '').encode())
        if notes.get('source_text_sha256') and notes['source_text_sha256'] != prompt_hash:
            raise ValueError('Stale curation for changed source text: ' + e['id'])
        e['source_title'] = e.get('source_title') or e['title']
        e['source_description'] = e.get('source_description', e.get('description', ''))
        e['title'], e['description'], e['features'] = describe(e, notes)
        e['editorial'] = {'basis': 'archived-source-text', 'label': '依据来源文字整理；未逐条实播复核',
                          'source_prompt_sha256': prompt_hash, 'version': curation.get('version', 1)}
        e['viewing_links'] = viewing_links(e)
        poster = notes.get('poster_source')
        if poster and not e.get('thumbnail_url'):
            url = poster['url']
            if urlsplit(url).scheme != 'https' or re.search(r'\.(mp4|m3u8)(?:\?|$)', url, re.I):
                raise ValueError('Poster source must be an HTTPS image')
            asset_id = 'poster-source-' + sha((e['id'] + ':' + url).encode())[:18]
            e['poster_asset_id'] = asset_id
            manifest.setdefault('planned_assets', []).append({'id': asset_id, 'type': 'poster', 'role': 'cover',
                'source_url': url, 'referer': poster['page'], 'source_id': e.get('source_id', ''), 'entries': [e['id']]})
            e['cover_provenance'] = {'page': poster['page'], 'image_url': url, 'method': 'source-page-og-image'}
        for key in ['thumbnail', 'thumbnail_url']:
            if isinstance(e.get(key), str):
                e[key] = e[key].replace('/inspiration-media/' + old_id + '/', '/inspiration-media/' + new_id + '/')
        for media in e.get('media', []):
            if media.get('availability') == 'local':
                media['url'] = media['url'].replace('/inspiration-media/' + old_id + '/', '/inspiration-media/' + new_id + '/')
        e['cover_status'] = 'archived-original' if e.get('thumbnail_url') else 'text-fallback-no-original-cover'
    catalog['snapshot_id'] = manifest['snapshot_id'] = new_id
    catalog['video_policy'] = manifest['video_policy'] = 'external-links-only-preserve-existing'
    manifest['parent_snapshot_id'] = old_id
    manifest['metadata_digest'] = digest
    report = {'snapshot_id': new_id, 'parent_snapshot_id': old_id, 'entries': len(known),
              'local_videos_preserved': sum(r.get('type') == 'video' for r in manifest.get('resources', [])),
              'video_downloads': 0, 'curated_titles': sum(bool(n.get('title')) for n in curation.get('entries', {}).values())}
    if dry_run:
        return report
    shutil.copytree(base, output, copy_function=shutil.copy2)
    source = output / 'sources/huashi/cards-curation.json'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(encoded(curation))
    manifest['source_files'] = [r for r in manifest.get('source_files', []) if r['path'] != 'sources/huashi/cards-curation.json']
    manifest['source_files'].append({'path': 'sources/huashi/cards-curation.json', 'bytes': source.stat().st_size, 'sha256': sha(source.read_bytes())})
    (output / 'catalog.json').write_bytes(encoded(catalog))
    (output / 'manifest.json').write_bytes(encoded(manifest))
    (output / 'cards-report.json').write_bytes(encoded(report))
    # Never carry a legacy video download plan into the new maintenance snapshot.
    (output / 'media-plan.json').write_bytes(encoded({'snapshot_id': new_id, 'assets': [], 'known_video_bytes': 0, 'video_policy': manifest['video_policy']}))
    return report
