"""Source-grounded single-agent question answering; not autonomous general intelligence.

Citation-ID verification prevents invented citations, not all factual errors.
"""
import json
from . import evidence, providers


def validate_answer(content, retrieved):
    if not isinstance(content, dict) or set(content) != {'answer', 'citations', 'confidence', 'limitations'}:
        raise ValueError('Model answer does not match required fields')
    if not isinstance(content['answer'], str) or not 1 <= len(content['answer']) <= 5000:
        raise ValueError('Invalid answer length')
    if not isinstance(content['limitations'], str) or len(content['limitations']) > 2000:
        raise ValueError('Invalid limitations')
    if content['confidence'] not in ('low','moderate','high'):
        raise ValueError('Invalid confidence')
    citations = content['citations']
    permitted = {item['citation_id'] for item in retrieved}
    if not isinstance(citations, list) or not 1 <= len(citations) <= 6 or any(
        not isinstance(x, str) or x not in permitted for x in citations
    ) or len(set(citations)) != len(citations):
        raise ValueError('Unknown, missing, or duplicate citation IDs')
    return content


def answer(db_factory, company_id, inputs, reserve_call, record_call):
    question = inputs.get('question')
    min_sources = inputs.get('min_sources', 1)
    if type(min_sources) is not int or not 1 <= min_sources <= 4:
        raise ValueError('min_sources must be 1–4')
    with db_factory() as db:
        retrieved = evidence.search(db, company_id, question, limit=6)
    if len(retrieved) < min_sources:
        raise ValueError('INSUFFICIENT_EVIDENCE: add sourced company knowledge or cultural records')
    model = providers.require_configured()
    reserve_call(model)
    try:
        result = providers.generate(question, retrieved)
        content = validate_answer(result['content'], retrieved)
        # Usage is taken from the actual provider response, not calculated or guessed.
        record_call('completed', result['usage'])
    except Exception:
        record_call('failed', {'input_tokens': None, 'output_tokens': None})
        raise
    source_map = {r['citation_id']: r for r in retrieved}
    return {
        'question': question,
        'answer': content['answer'],
        'citations': [source_map[c] for c in content['citations']],
        'confidence': content['confidence'],
        'limitations': content['limitations'],
        'verification': 'citation_identifiers_checked_only_not_fact_checked',
        'source_quality': 'unverified_and_user_supplied_sources_remain_unverified',
        'provider': 'openai_responses', 'model': result['model'],
        'provider_response_id': result['provider_response_id'],
        'model_usage': result['usage'],
        'model_cost_usd': None,
    }
