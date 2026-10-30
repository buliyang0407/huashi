"""Read-only adapters for the inspiration catalog and saved prompts."""
from __future__ import annotations

import json
import sqlite3

from .thumbnails import ThumbnailService, ThumbnailError

KINDS = ('case', 'style', 'layout', 'prompt')


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return ''


def _asset(value):
    if isinstance(value, str) and value.startswith('/') and not value.startswith('//'):
        return value if value.startswith('/inspiration/') else '/inspiration' + value
    return ''


class InspirationSearch:
    def __init__(self, library, store):
        self.library = library
        self.store = store
        self.thumbnails = ThumbnailService(store.db_path.parent)
        self._archive_stamp = None
        self._archive_items = []

    def _archive(self):
        # Index only immutable catalog fields, never scan/download original images.
        raw, catalog = self.library._catalog()
        stamp = id(raw)
        if stamp != self._archive_stamp:
            items = []
            for entry in catalog.get('entries', []):
                kind = entry.get('kind') or entry.get('type')
                if kind not in KINDS[:3] or not isinstance(entry.get('id'), str):
                    continue
                prompt = next((entry.get(key) for key in ('prompt', 'prompt_en', 'promptEn', 'promptHintEn') if isinstance(entry.get(key), str) and entry[key].strip()), '')
                item = {'id': entry['id'], 'kind': kind, 'title': _text(entry.get('title') or entry.get('name') or entry['id']),
                        'description': _text(entry.get('description') or entry.get('traits')), 'prompt': prompt,
                        'thumbnail': _asset(entry.get('thumbnail')), 'image': _asset(entry.get('image') or entry.get('referenceImage')),
                        'tags': entry.get('tags') if isinstance(entry.get('tags'), list) else [],
                        'source': _text(entry.get('source')), 'source_url': _text(entry.get('sourceUrl'))}
                item['_search'] = ' '.join(_text(entry.get(key)) for key in ('title', 'name', 'category', 'tags', 'description', 'traits', 'prompt', 'promptEn', 'prompt_en', 'promptHintEn')).casefold()
                items.append(item)
            self._archive_items = items
            self._archive_stamp = stamp
        return self._archive_items

    def _prompts(self, folder_id=None):
        items = []
        for prompt in self.store.list_prompts(folder_id=folder_id):
            thumbnail = prompt.get('sample_url') or ''
            try:
                thumbnail = self.thumbnails.url_for_existing_source(prompt.get('sample_path') or '')
            except (OSError, ThumbnailError):
                pass
            common = {'kind': 'prompt', 'thumbnail': thumbnail,
                      'image': prompt.get('sample_url') or '', 'tags': prompt.get('tags') or [], 'source': prompt.get('folder_path') or '我的提示词', 'source_url': '', 'prompt_id': prompt['id'],
                      'folder_id': prompt.get('folder_id'), 'folder_path': prompt.get('folder_path') or ''}
            item = {**common, 'id': 'prompt:' + prompt['id'], 'title': prompt['title'], 'description': prompt.get('note') or '', 'prompt': prompt['content']}
            item['_search'] = ' '.join(_text(prompt.get(key)) for key in ('title', 'content', 'tags', 'note', 'folder_path')).casefold()
            items.append(item)
            for variant in prompt.get('variants') or []:
                variant_item = {**common, 'id': 'variant:' + variant['id'], 'title': variant.get('title') or prompt['title'],
                                'description': variant.get('translation') or variant.get('edit_idea') or '', 'prompt': variant['content'], 'variant_id': variant['id']}
                variant_item['_search'] = ' '.join(_text(variant.get(key)) for key in ('title', 'content', 'translation', 'edit_idea', 'explanation_cn')).casefold()
                items.append(variant_item)
        return items

    def search(self, query='', kind='all', offset=0, limit=24, prompt_folder_id=None):
        query = str(query or '').strip()
        if len(query) > 256 or kind not in ('all', *KINDS) or not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('搜索类型、长度或分页范围不正确')
        sources = {'archive': {'available': True}, 'prompts': {'available': True}}
        try:
            items = list(self._archive())
        except (OSError, ValueError, KeyError, TypeError):
            items = []
            sources['archive'] = {'available': False, 'message': '灵感归档暂时不可用，仍可搜索提示词'}
        try:
            items.extend(self._prompts(folder_id=prompt_folder_id))
        except sqlite3.Error:
            sources['prompts'] = {'available': False, 'message': '提示词库暂时不可用'}
        tokens = query.casefold().split()
        matches = [item for item in items if all(token in item['_search'] for token in tokens)]
        counts = {k: sum(item['kind'] == k for item in matches) for k in KINDS}
        counts = {'all': len(matches), **counts}
        matches = [item for item in matches if kind == 'all' or item['kind'] == kind]
        matches.sort(key=lambda item: (-sum(token in item['title'].casefold() for token in tokens), KINDS.index(item['kind']), item['id']))
        if kind == 'all':
            # Interleave matching sources so a large catalog cannot bury saved prompts.
            groups = [[item for item in matches if item['kind'] == k] for k in KINDS]
            matches = [group[index] for index in range(max((len(group) for group in groups), default=0)) for group in groups if index < len(group)]
        total = len(matches)
        visible = [{k: v for k, v in item.items() if k != '_search'} for item in matches[offset:offset + limit]]
        next_offset = offset + limit if offset + limit < total else None
        return {'query': query, 'kind': kind, 'counts': counts, 'total': total, 'offset': offset, 'limit': limit,
                'items': visible, 'next_offset': next_offset, 'sources': sources}
