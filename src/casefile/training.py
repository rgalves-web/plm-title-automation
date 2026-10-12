"""Local, immutable methodological knowledge. Never evidence of a unit fact.

Source ingestion extracts fragments, NOT semantic rules or approvals. No network.
Releases require explicit review of exact versions; sessions consume DB snapshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

SCOPE_KEYS = ('project', 'jurisdiction', 'substance', 'stage', 'work_type')
ROOT = Path(__file__).resolve().parents[2] / 'data' / 'training_suite'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    from src.casefile.storage import preserved_path
    path=preserved_path(path)
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def immutable(path, value):
    """Exclusive creation; same identity must always have identical bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = encoded(value)
    try:
        with path.open('xb') as f:
            f.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError(f'immutable_content_mismatch: {path.name}')


def identifier(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value):
        raise ValueError('invalid_identifier')
    return value


def applicable(card, context):
    """Only metadata selection. Unknown is not global. Conditions stay visible."""
    scope = card.get('scope', {})
    return all(scope.get(k) and context.get(k) and
               ('*' in scope[k] or context[k].casefold() in
                [x.casefold() for x in scope[k]]) for k in SCOPE_KEYS)


class Store:
    def __init__(self, root=ROOT):
        self.root = Path(root)

    def put(self, card, *, verify_source=True):
        c = dict(card)
        for k in ('rule_id', 'literal', 'interpretation', 'nature', 'scope',
                  'conditions', 'exceptions', 'relations', 'sources'):
            if k not in c:
                raise ValueError(f'missing_{k}')
        identifier(c['rule_id'])
        if c['nature'] not in ('source_fragment', 'quiz', 'example', 'administrative', 'methodology',
                              'project_instruction', 'review_criterion', 'tool_recipe', 'alert', 'gap'):
            raise ValueError('invalid_nature')
        if not c['sources'] or not c['literal'].strip():
            raise ValueError('source_and_literal_required')
        if c['nature'] != 'source_fragment' and len(encoded(c)) > 23000:
            raise ValueError('card_too_large_split_before_review')
        for key in SCOPE_KEYS:
            if not isinstance(c['scope'].get(key), list) or any(
                    not isinstance(v, str) or not v.strip() for v in c['scope'][key]):
                raise ValueError('scope_must_be_explicit_lists')
        for source in c['sources']:
            for k in ('path', 'sha256', 'locator', 'quote'):
                if not source.get(k):
                    raise ValueError(f'missing_source_{k}')
            if verify_source and file_hash(source['path']) != source['sha256']:
                raise ValueError('source_hash_mismatch')
            if verify_source:
                raw_text = '\n'.join(t for _, t in text_parts(Path(source['path'])))
                if source['quote'] not in raw_text:
                    raise ValueError('source_quote_not_found')
        c['status'] = 'candidate'
        c.setdefault('source_date', None)
        c.setdefault('effective_date', None)
        c.setdefault('author', 'import')
        c.pop('version', None)
        version = digest(c)
        immutable(self.root / 'cards' / c['rule_id'] / f'{version}.json', c)
        return {**c, 'version': version}

    def get(self, rule_id, version):
        path = self.root / 'cards' / identifier(rule_id) / f'{identifier(version)}.json'
        c = json.loads(path.read_text(encoding='utf-8'))
        if digest(c) != version:
            raise ValueError('card_hash_mismatch')
        return {**c, 'version': version}

    def cards(self):
        for path in sorted((self.root / 'cards').glob('*/*.json')):
            yield self.get(path.parent.name, path.stem)

    def publish(self, refs, *, reviewer, reason, reviewed_at, inventory_id=None):
        if not reviewer.strip() or not reason.strip() or not reviewed_at.strip():
            raise ValueError('explicit_review_required')
        cards = [self.get(r['rule_id'], r['version']) for r in refs]
        if not cards or len({c['rule_id'] for c in cards}) != len(cards):
            raise ValueError('one_version_per_rule_required')
        for c in cards:
            if any(not c['scope'].get(k) for k in SCOPE_KEYS):
                raise ValueError('unknown_scope_requires_review')
            if c['nature'] in ('source_fragment', 'quiz', 'example', 'administrative'):
                raise ValueError('non_operational_content')
        release = {'cards': sorted(refs, key=lambda r: r['rule_id']),
                   'reviewer': reviewer, 'reason': reason, 'reviewed_at': reviewed_at}
        if inventory_id:
            manifest = json.loads((self.root / 'inventories' / f'{identifier(inventory_id)}.json').read_text('utf-8'))
            if digest(manifest) != inventory_id:
                raise ValueError('inventory_hash_mismatch')
            release['inventory_id'] = inventory_id
            release['coverage'] = [{k: s[k] for k in ('relative_path', 'sha256', 'coverage', 'destination')}
                                   for s in manifest['sources']]
        rid = digest(release)
        immutable(self.root / 'releases' / f'{rid}.json', release)
        return rid

    def release(self, rid):
        if list((self.root / 'withdrawals' / identifier(rid)).glob('*.json')):
            raise ValueError('release_withdrawn_requires_new_operator_decision')
        r = json.loads((self.root / 'releases' / f'{identifier(rid)}.json').read_text('utf-8'))
        if digest(r) != rid:
            raise ValueError('release_hash_mismatch')
        return r, [self.get(c['rule_id'], c['version']) for c in r['cards']]

    def withdraw(self, release_id, reviewer, reason, reviewed_at):
        if not all(str(v).strip() for v in (reviewer, reason, reviewed_at)):
            raise ValueError('explicit_review_required')
        self.release(release_id)
        event = dict(release_id=release_id, reviewer=reviewer, reason=reason, reviewed_at=reviewed_at)
        immutable(self.root / 'withdrawals' / identifier(release_id) / f'{digest(event)}.json', event)

    def search(self, query, context, release_id, limit=8):
        _, cards = self.release(release_id)
        words = set(re.findall(r'\w+', query.casefold()))
        found = []
        for c in cards:
            if not applicable(c, context):
                continue
            score = len(words & set(re.findall(r'\w+', (c['literal'] + ' ' + c['interpretation']).casefold())))
            if score or not words:
                found.append((score, c))
        return [c for _, c in sorted(found, key=lambda x: (-x[0], x[1]['rule_id']))[:max(1, min(limit, 20))]]


def text_parts(path):
    from src.casefile.storage import preserved_path
    path=preserved_path(path)
    """Preserve paragraph/line locators; do not claim visual coverage."""
    if path.suffix.lower() == '.docx':
        with ZipFile(path) as z:
            root = ET.fromstring(z.read('word/document.xml'))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return [(f'paragraph:{i}', ''.join(p.itertext())) for i, p in
                    enumerate(root.findall('.//w:p', ns), 1)]
    if path.suffix.lower() in ('.md', '.txt', '.json'):
        return [(f'line:{i}', line) for i, line in
                enumerate(path.read_text('utf-8-sig').splitlines(), 1)]
    return []


def inventory(source_root, store):
    root = Path(source_root).resolve()
    if store.root.resolve().is_relative_to(root):
        raise ValueError('output_must_be_outside_source_tree')
    files, duplicates = [], {}
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        sha = file_hash(path)
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        dates = re.findall(r'20\d\d-\d\d-\d\d', path.name)
        item = {'path': str(path), 'relative_path': rel, 'sha256': sha,
                'bytes': path.stat().st_size, 'modality': suffix.lstrip('.'),
                'course_hint': path.stem.split('__')[1:2], 'lesson': None,
                'source_date': None, 'capture_date_hint': dates[-1] if dates else None,
                'snapshot': 'snapshot' in path.name.casefold(),
                'duplicate_of': duplicates.get(sha),
                'coverage': {'lms_completed': 'unknown', 'text_extracted': False,
                             'image_examined': False, 'video_transcribed': False,
                             'knowledge_approved': False},
                'destination': 'coverage_pending', 'fragments': []}
        duplicates.setdefault(sha, rel)
        # Exclude task prompts/evaluations: they are not training sources.
        eligible = path.name.startswith('TRAINING SUITE')
        parts = text_parts(path) if eligible else []
        if parts:
            item['coverage']['text_extracted'] = True
            item['destination'] = 'snapshot_reference' if item['snapshot'] else 'candidate_fragments'
        if suffix == '.docx' and eligible:
            with ZipFile(path) as z:
                item['embedded_media'] = [
                    {'name': n, 'sha256': hashlib.sha256(z.read(n)).hexdigest(),
                     'coverage': 'not_examined'} for n in z.namelist() if n.startswith('word/media/')]
        # All current text is addressable. Snapshots kept as source identities only.
        if parts and not item['snapshot'] and not item['duplicate_of']:
            chunk, start, size = [], None, 0
            def save():
                if not chunk:
                    return
                text = '\n'.join(chunk)
                card = store.put({'rule_id': 'fragment-' + sha[:16] + '-' + start.replace(':', '-'),
                    'literal': text, 'interpretation': '', 'nature': 'source_fragment',
                    'scope': {k: [] for k in SCOPE_KEYS}, 'conditions': [], 'exceptions': [],
                    'relations': [], 'sources': [{'path': str(path), 'sha256': sha,
                        'locator': start, 'quote': text}], 'author': 'mechanical_extraction'}, verify_source=False)
                item['fragments'].append({'rule_id': card['rule_id'], 'version': card['version']})
            for locator, line in parts:
                if size >= 2400 or (line.startswith('# ') and chunk):
                    save(); chunk, start, size = [], None, 0
                if line.strip():
                    start = start or locator
                    chunk.append(line); size += len(line)
            save()
        files.append(item)
    manifest = {'schema': 1, 'source_root': str(root), 'sources': files}
    mid = digest(manifest)
    immutable(store.root / 'inventories' / f'{mid}.json', manifest)
    return mid, manifest


def legacy_candidates(root, query):
    """Read all OKF bodies, retain source bytes/version; never retroapprove."""
    words = set(re.findall(r'\w+', query.casefold()))
    out = []
    for p in sorted(Path(root).glob('*.md')):
        if p.name in ('index.md', 'log.md'):
            continue
        body = p.read_text('utf-8')
        score = len(words & set(re.findall(r'\w+', body.casefold())))
        if score:
            out.append({'rule_id': p.stem, 'version': file_hash(p), 'path': str(p),
                        'status': 'legacy_unreviewed', 'score': score})
    return sorted(out, key=lambda x: (-x['score'], x['rule_id']))[:8]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--store', type=Path, default=ROOT)
    sub = p.add_subparsers(dest='command', required=True)
    inv = sub.add_parser('inventory'); inv.add_argument('source_root', type=Path)
    imp = sub.add_parser('import'); imp.add_argument('cards_json', type=Path)
    pub = sub.add_parser('publish'); pub.add_argument('review_json', type=Path)
    search = sub.add_parser('search'); search.add_argument('release_id'); search.add_argument('query'); search.add_argument('context_json', type=Path)
    cand = sub.add_parser('candidates'); cand.add_argument('query')
    activate = sub.add_parser('activate'); activate.add_argument('unit_id', type=int); activate.add_argument('config_json', type=Path)
    withdraw = sub.add_parser('withdraw'); withdraw.add_argument('review_json', type=Path)
    args = p.parse_args(argv); store = Store(args.store)
    if args.command == 'inventory':
        mid, m = inventory(args.source_root, store)
        print(json.dumps({'inventory': mid, 'sources': len(m['sources'])}))
    elif args.command == 'import':
        print(json.dumps([{'rule_id': c['rule_id'], 'version': c['version']} for c in
            [store.put(c) for c in json.loads(args.cards_json.read_text('utf-8'))]], indent=2))
    elif args.command == 'publish':
        review = json.loads(args.review_json.read_text('utf-8'))
        print(store.publish(**review))
    elif args.command == 'withdraw':
        store.withdraw(**json.loads(args.review_json.read_text('utf-8')))
        print('withdrawal recorded; historical contexts retained')
    elif args.command == 'activate':
        from src.casefile.db import connect
        from src.casefile.repo import Repo
        config = json.loads(args.config_json.read_text('utf-8'))
        config['store_root'] = str(args.store.resolve())
        store.release(config['release_id'])
        if not config.get('reviewer') or not config.get('reason') or any(
                not config.get('scope', {}).get(k) for k in SCOPE_KEYS if k != 'stage'):
            raise ValueError('explicit_scope_reviewer_reason_required')
        with connect() as conn:
            print(Repo(conn).configure_training(args.unit_id, config))
    elif args.command == 'candidates':
        terms = set(re.findall(r'\w+', args.query.casefold()))
        hits = [(len(terms & set(re.findall(r'\w+', c['literal'].casefold()))), c) for c in store.cards()]
        print(json.dumps([c for n, c in sorted(hits, key=lambda x: -x[0]) if n][:10], ensure_ascii=False, indent=2))
    else:
        print(json.dumps(store.search(args.query, json.loads(args.context_json.read_text('utf-8')),
                                     args.release_id), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
