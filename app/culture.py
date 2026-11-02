"""Evidence-labeled cultural studies and public-source reference catalog.

No statement here claims automatic verification of interpretations or the
complete contents of any tradition. Source records are not model instructions.
"""
from urllib.parse import urlsplit
import ipaddress

EVIDENCE_CLASSES={
    'astronomical_measurement',
    'historical_primary_text',
    'scholarly_interpretation',
    'cultural_belief',
    'mythological_narrative',
    'hypothesis',
    'unverified_claim',
}
# A directory of starting points, not an ingested encyclopedia or endorsement.
SOURCE_CATALOG=(
    {'id':'jpl-horizons','title':'JPL Horizons','url':'https://ssd.jpl.nasa.gov/horizons/',
     'domain':'astronomy','evidence_class':'astronomical_measurement',
     'scope':'Astronomical ephemeris and solar-system positional calculations'},
    {'id':'nasa-pds','title':'NASA Planetary Data System','url':'https://pds.nasa.gov/',
     'domain':'space','evidence_class':'astronomical_measurement',
     'scope':'Archived planetary science mission data'},
    {'id':'nasa-ntrs','title':'NASA Technical Reports Server','url':'https://ntrs.nasa.gov/',
     'domain':'science','evidence_class':'scholarly_interpretation',
     'scope':'Scientific and technical reports; item-level review required'},
    {'id':'gretil','title':'GRETIL Sanskrit and Indian-language texts','url':'https://gretil.sub.uni-goettingen.de/',
     'domain':'vedic_and_indic_studies','evidence_class':'historical_primary_text',
     'scope':'Edited and digitized Indic texts; editions and translations vary'},
    {'id':'smithsonian','title':'Smithsonian Open Access','url':'https://www.si.edu/openaccess',
     'domain':'world_history_and_cultures','evidence_class':'historical_primary_text',
     'scope':'Museum and archival material; assess each item and its rights'},
)


def validate_record(values):
    """Validate metadata, never upgrade user claims to verified facts."""
    if not isinstance(values,dict):raise ValueError('Record must be an object')
    x={k:values.get(k,'') for k in ('title','tradition','topic','language','work','passage','source_url','evidence_class','content')}
    limits={'title':200,'tradition':100,'topic':120,'language':80,
            'work':200,'passage':200,'source_url':2048,'content':12000}
    for k,maxlen in limits.items():
        if not isinstance(x[k],str) or len(x[k])>maxlen:
            raise ValueError('Invalid '+k)
    for key in ('title','tradition','topic','source_url','content'):
        if not x[key].strip(): raise ValueError('Missing '+key)
    if x['evidence_class'] not in EVIDENCE_CLASSES:
        raise ValueError('Unsupported evidence class')
    # URL is a citation field, not a fetch request. User records remain unverified.
    p=urlsplit(x['source_url'])
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('Citation must be an HTTPS URL')
    x['review_status']='user_supplied_unverified'
    x['decision_role']='context_only_not_authoritative'
    return x


def validate_subscription(values):
    if not isinstance(values,dict):raise ValueError('Subscription must be an object')
    title=values.get('title');url=values.get('url');tradition=values.get('tradition')
    interval=values.get('interval_hours',24)
    if not isinstance(title,str) or not 1<=len(title)<=200:raise ValueError('Invalid title')
    if not isinstance(tradition,str) or not 1<=len(tradition)<=100:raise ValueError('Invalid tradition')
    if not isinstance(url,str) or not 1<=len(url)<=2048:raise ValueError('Invalid URL')
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('Subscriptions require HTTPS URL')
    if p.hostname=='localhost' or p.hostname.endswith(('.local','.internal','.localhost','.test','.invalid','.onion')):
        raise ValueError('Private hostname not allowed')
    try:
        ipaddress.ip_address(p.hostname)
    except ValueError:
        pass
    else:
        raise ValueError('IP literal URLs are not allowed')
    if type(interval) is not int or not 24<=interval<=24*90:raise ValueError('Interval must be 24–2160 hours')
    return {'title':title,'url':url,'tradition':tradition,'interval_seconds':interval*3600}
