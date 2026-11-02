"""Astronomy measurements and traditional zodiac coordinate classification.

Ephemeris data are requested from NASA/JPL Horizons. The zodiac classification
is a cultural coordinate convention, NOT evidence of personality or causality.
No birth-chart accuracy is claimed: proper charts require historical timescales,
location, precession/nutation, sidereal convention and expert validation.
"""
import datetime as dt
import math
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from . import research

HORIZONS_ENDPOINT = 'https://ssd.jpl.nasa.gov/api/horizons.api'
BODIES = {'sun':'10','moon':'301','mercury':'199','venus':'299','mars':'499',
          'jupiter':'599','saturn':'699','uranus':'799','neptune':'899'}
SIGNS = ('Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio',
         'Sagittarius','Capricorn','Aquarius','Pisces')
NAKSHATRAS = ('Ashwini','Bharani','Krittika','Rohini','Mrigashira','Ardra',
              'Punarvasu','Pushya','Ashlesha','Magha','Purva Phalguni',
              'Uttara Phalguni','Hasta','Chitra','Swati','Vishakha','Anuradha',
              'Jyeshtha','Mula','Purva Ashadha','Uttara Ashadha','Shravana',
              'Dhanishta','Shatabhisha','Purva Bhadrapada','Uttara Bhadrapada','Revati')
NUM = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')


def zodiac(longitude_deg, *, ayanamsha_deg=None, frame='ecliptic_of_date'):
    """Classify input longitude; no ephemeris lookup or future prediction."""
    if frame != 'ecliptic_of_date':
        raise ValueError('Only explicitly supplied ecliptic-of-date longitudes are supported')
    try:
        lon = Decimal(str(longitude_deg))
        if not lon.is_finite(): raise ValueError('Longitude must be finite')
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Longitude must be a finite number') from exc
    lon = ((lon % 360) + 360) % 360
    result = {'coordinate_system':frame,'longitude_degrees':str(lon),
              'tropical_sign':SIGNS[int(lon // 30)],
              'evidence_class':'mathematical_coordinate_mapping',
              'limitations':'Geometric sign labeling does not establish astrology as a causal predictor.'}
    if ayanamsha_deg is not None:
        try:
            offset = Decimal(str(ayanamsha_deg))
            if not offset.is_finite() or not 0 <= offset <= 40:
                raise ValueError('Ayanamsha must be between 0 and 40 degrees')
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError('Ayanamsha must be a finite number between 0 and 40') from exc
        sidereal = (lon - offset) % 360
        result.update({'sidereal_longitude_degrees':str(sidereal),
                       'sidereal_sign':SIGNS[int(sidereal // 30)],
                       'nakshatra':NAKSHATRAS[int((sidereal * 27 // 360))],
                       'ayanamsha_degrees':str(offset),
                       'ayanamsha_source':'caller_supplied_not_independently_verified'})
    else:
        result['sidereal_status']='ayanamsha_required; no default is silently selected'
    return result


def horizons_url(body, date_utc):
    """Build a strictly bounded, fixed-schema Horizons request with no user URL."""
    if body not in BODIES: raise ValueError('Unsupported celestial body')
    if not isinstance(date_utc,str): raise ValueError('Date must be YYYY-MM-DD')
    try: date=dt.date.fromisoformat(date_utc)
    except ValueError as exc: raise ValueError('Date must be YYYY-MM-DD') from exc
    if date.isoformat()!=date_utc or not 1900 <= date.year <= 2100:
        raise ValueError('Supported date range is 1900-01-01 through 2100-12-31')
    # One discrete observation via JPL TLIST. TIME_TYPE=UT is explicit for
    # date interpretation; ECLIPTIC is J2000, not ecliptic of date.
    params={'format':'text','COMMAND':f"'{BODIES[body]}'",'OBJ_DATA':'NO',
            'MAKE_EPHEM':'YES','EPHEM_TYPE':'VECTORS','CENTER':"'500@399'",
            'REF_PLANE':'ECLIPTIC','OUT_UNITS':'KM-S','VEC_TABLE':'2',
            'CSV_FORMAT':'YES','TLIST':f"'{date_utc} 00:00'",
            'TLIST_TYPE':'CAL','TIME_TYPE':'UT'}
    return HORIZONS_ENDPOINT+'?'+urlencode(params)


def parse_vectors(text):
    """Accept only one complete CSV state vector enclosed by Horizons markers."""
    if not isinstance(text,str) or '$$SOE' not in text or '$$EOE' not in text:
        raise ValueError('JPL response is missing complete ephemeris markers')
    segment=text.split('$$SOE',1)[1].split('$$EOE',1)[0]
    lines=[line.strip() for line in segment.splitlines() if line.strip()]
    if len(lines)!=1: raise ValueError('Expected exactly one ephemeris vector')
    parts=[x.strip() for x in lines[0].strip().rstrip(',').split(',')]
    if len(parts)!=8 or not all(NUM.fullmatch(v) for v in [parts[0],*parts[2:]]):
        raise ValueError('Malformed JPL vector response')
    values=[float(x) for x in parts[2:]]
    if not all(math.isfinite(v) for v in values):raise ValueError('Non-finite JPL vector')
    return {'julian_date_as_reported':parts[0], 'calendar_time_as_reported':parts[1],
            'position_km':dict(zip(('x','y','z'),values[:3])),
            'velocity_km_s':dict(zip(('vx','vy','vz'),values[3:])),
            'geocentric_ecliptic_J2000_longitude_degrees':round(math.degrees(math.atan2(values[1],values[0])) % 360,8)}


def jpl_ephemeris(body,date_utc):
    url=horizons_url(body,date_utc)
    # Research client pins DNS addresses, enforces HTTPS, a byte budget, and
    # checks every redirect. It fails closed when internet access is disabled.
    response=research.fetch_public(url)
    # fetch_public keeps at most a 12K excerpt. Refuse truncated output.
    value=parse_vectors(response['excerpt'])
    return {**value,'body':body,'requested_date_utc':date_utc,
            'source_url':response['url'],'retrieved_at':response['retrieved_at'],
            'source_sha256':response['sha256'],
            'reference_frame':'geocentric J2000 ecliptic; not ecliptic of date',
            'time_scale_requested':'UT (explicit Horizons TIME_TYPE)',
            'evidence_class':'remote_scientific_ephemeris_unverified_locally',
            'limitations':'External JPL output is parsed, not independently recomputed; timescale appears as JPL reports it. Do not use J2000 longitude as ecliptic-of-date without transformation.'}
