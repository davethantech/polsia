"""Tiny, auditable, tenant-specific neural re-ranker trained on evaluated preferences.

This neural network is NOT a general-purpose language model or evidence of AGI.
It only learns which of two previously retrieved sources is more relevant to a
question. Neither internet access nor a valid citation supplies a training label.
"""
import json
import math
import re

DIM = 8
HIDDEN = 6
MAX_FEEDBACK = 300
TERM = re.compile(r'[^\W_]{2,}', re.UNICODE)


def initial():
    # Fixed small, nonidentical weights: reproducible across environments.
    return {
        'w1': [[((j * 11 + i * 7) % 17 - 8) / 80 for i in range(DIM)] for j in range(HIDDEN)],
        'b1': [0.0] * HIDDEN,
        'w2': [((j * 7) % 13 - 6) / 30 for j in range(HIDDEN)],
        'b2': 0.0,
    }


def validate(weights):
    if not isinstance(weights, dict) or set(weights) != {'w1','b1','w2','b2'}:
        raise ValueError('Invalid neural parameters')
    if len(weights['w1']) != HIDDEN or any(len(row) != DIM for row in weights['w1']):
        raise ValueError('Invalid neural weight matrix')
    if len(weights['b1']) != HIDDEN or len(weights['w2']) != HIDDEN:
        raise ValueError('Invalid neural layer dimension')
    values = [v for row in weights['w1'] for v in row] + weights['b1'] + weights['w2'] + [weights['b2']]
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v) > 6 for v in values):
        raise ValueError('Unbounded or invalid neural parameters')
    return weights


def features(question, source):
    """Eight transparent, bounded relevance signals (not truth judgments)."""
    q = set(TERM.findall(question.lower()))
    title = (source.get('title') or '').lower()
    excerpt = (source.get('excerpt') or '').lower()
    title_tokens = set(TERM.findall(title))
    body_tokens = set(TERM.findall(excerpt))
    overlap = len(q & body_tokens) / max(1, len(q))
    t_overlap = len(q & title_tokens) / max(1, len(q))
    quoted = min(1.0, len(excerpt) / 500)
    class_name = (source.get('evidence_class') or '').lower()
    return [min(1., overlap), min(1., t_overlap),
            min(1., len(q & body_tokens) / 8), quoted,
            1.0 if source.get('kind') == 'company_memory' else 0.0,
            1.0 if bool(source.get('source_url')) else 0.0,
            1.0 if 'unverified' in class_name else 0.0,
            min(1., len(q) / 16)]


def _forward(w, x):
    hidden = [math.tanh(sum(a * b for a, b in zip(row,x)) + bias)
              for row, bias in zip(w['w1'], w['b1'])]
    value = sum(a*b for a,b in zip(w['w2'],hidden)) + w['b2']
    return value, hidden


def score(w, question, source):
    validate(w)
    return _forward(w, features(question, source))[0]


def _loss(w, pos_x, neg_x):
    a = _forward(w,pos_x)[0]
    b = _forward(w,neg_x)[0]
    margin = max(-30., min(30., a-b))
    return math.log1p(math.exp(-margin))


def train_pair(weights, question, preferred, rejected):
    """One bounded pairwise gradient update. Reject updates that do not improve loss."""
    w = validate(json.loads(json.dumps(weights)))
    xp, xn = features(question,preferred), features(question,rejected)
    if xp == xn:
        raise ValueError('Sources have identical learning features; cannot learn preference')
    before = _loss(w,xp,xn)
    ap,hp = _forward(w,xp)
    an,hn = _forward(w,xn)
    scale = 1/(1+math.exp(max(-30.,min(30.,ap-an))))  # -dloss/dmargin
    # Compute gradient at old weights. w2 derivative flows into first layer.
    dw2 = [scale*(hp[j]-hn[j]) for j in range(HIDDEN)]
    dw1 = [[scale*w['w2'][j]*((1-hp[j]**2)*xp[i]-(1-hn[j]**2)*xn[i])
            for i in range(DIM)] for j in range(HIDDEN)]
    db1 = [scale*w['w2'][j]*((1-hp[j]**2)-(1-hn[j]**2)) for j in range(HIDDEN)]
    for rate in (.25,.08,.02):
        candidate = json.loads(json.dumps(w))
        for j in range(HIDDEN):
            candidate['w2'][j] += rate * dw2[j]
            candidate['b1'][j] += rate * db1[j]
            for i in range(DIM):
                candidate['w1'][j][i] += rate * dw1[j][i]
        validate(candidate)
        after = _loss(candidate,xp,xn)
        if after < before-1e-10:
            return candidate, {'loss_before':round(before,8),'loss_after':round(after,8)}
    raise ValueError('Update did not improve validated pairwise loss')
