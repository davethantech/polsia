"""Tenant-filtered, provenance-preserving *keyword* retrieval.

This is intentionally not called semantic/vector search. Data retrieved from the
web or user-submitted cultural records are untrusted context, not instructions.
"""
import html
import re

TOKEN = re.compile(r'[^\W_]{2,}', re.UNICODE)
STOP = frozenset('what when where which who how why does do did is are the this that with from about could would should into any for have has and or to in on of a an be by as at me my your tell explain describe please'.split())
MAX_SOURCE_CHARS = 1200


def _terms(query):
    if not isinstance(query, str) or not 3 <= len(query.strip()) <= 1200:
        raise ValueError('Question must have 3–1200 characters')
    if len(query.encode('utf-8')) > 4000:
        raise ValueError('Question is too large')
    return list(dict.fromkeys(x.lower() for x in TOKEN.findall(query) if x.lower() not in STOP))[:24]


def _plain(value):
    # HTML pages currently arrive in bounded text snapshots. Extracted text is
    # still treated as untrusted and is NOT reinterpreted as system instructions.
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]{0,500}>', ' ', value))).strip()


def search(db, company_id, query, limit=5):
    """Return bounded evidence with exact tenant filter on both backing tables.

    No cross-company fallback, global cache, network call or inferred citation.
    The scores measure keyword overlap, not factual reliability.
    """
    terms = _terms(query)
    if not terms:
        return []
    if type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError('limit must be an integer between 1 and 8')
    candidates = []
    memories = db.execute('''SELECT id,layer,content,source,evidence_status,created_at
        FROM knowledge WHERE company_id=? ORDER BY created_at DESC,id DESC LIMIT 300''', (company_id,)).fetchall()
    for row in memories:
        raw = dict(row)
        body = _plain(raw['content'])
        candidates.append({
            'citation_id': 'memory:' + raw['id'], 'kind': 'company_memory',
            'title': raw['layer'], 'source_url': raw['source'],
            'evidence_class': raw['evidence_status'],
            'review_status': 'source_not_independently_verified',
            'recorded_at': raw['created_at'], 'excerpt': body[:MAX_SOURCE_CHARS],
            '_matching_text': (raw['layer'] + ' ' + body).lower(),
        })
    cultures = db.execute('''SELECT id,title,tradition,topic,work,passage,content,
        source_url,evidence_class,review_status,created_at,retrieved_at
        FROM culture_records WHERE company_id=? ORDER BY created_at DESC,id DESC LIMIT 300''',
        (company_id,)).fetchall()
    for row in cultures:
        raw = dict(row)
        body = _plain(raw['content'])
        title = ' — '.join(x for x in (raw['title'], raw['work'], raw['passage']) if x)
        candidates.append({
            'citation_id': 'culture:' + raw['id'], 'kind': 'cultural_source',
            'title': title, 'source_url': raw['source_url'],
            'evidence_class': raw['evidence_class'], 'review_status': raw['review_status'],
            'recorded_at': raw['retrieved_at'] or raw['created_at'], 'excerpt': body[:MAX_SOURCE_CHARS],
            '_matching_text': ' '.join([title, raw['tradition'], raw['topic'], body]).lower(),
        })
    ranked = []
    for item in candidates:
        score = sum(min(3, item['_matching_text'].count(t)) for t in terms)
        if score:
            ranked.append((score, item['recorded_at'], item))
    ranked.sort(key=lambda s: (-s[0], -s[1], s[2]['citation_id']))
    return [{k: v for k, v in item.items() if k != '_matching_text'} for _, _, item in ranked[:limit]]
