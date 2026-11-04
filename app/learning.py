"""Scoped, explicit source subscriptions for incremental knowledge acquisition.

This is retrieval-augmented memory, NOT neural-network weight training.
"""
from .culture import validate_subscription


def validate_source(data):
    if not isinstance(data, dict):
        raise ValueError('Source must be an object')
    title, topic = data.get('title'), data.get('topic')
    if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 100:
        raise ValueError('Learning topic must have 1–100 characters')
    normalized = validate_subscription({
        'title': title, 'tradition': topic.strip(),
        'url': data.get('url'), 'interval_hours': data.get('interval_hours', 24),
    })
    return {'title': normalized['title'], 'topic': topic.strip(),
            'url': normalized['url'], 'interval_seconds': normalized['interval_seconds']}
