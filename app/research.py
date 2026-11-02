"""Bounded, HTTPS-only public document fetch with IP pinning and redirect checks.

Not a crawler. Webpage content is untrusted evidence, never instructions for agents.
"""
import hashlib
import http.client
import ipaddress
import os
import socket
import ssl
import time
from urllib.parse import urlsplit, urljoin

MAX_BYTES=65536
MAX_REDIRECTS=2
TIMEOUT=5


def validated_destination(url):
    if not isinstance(url,str) or len(url)>2048:raise ValueError('Invalid URL')
    try:
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
            raise ValueError('Only public HTTPS websites on port 443 are permitted')
        host=p.hostname.encode('idna').decode('ascii')
        # Preclude IP literals, including numeric or IPv6 hostnames.
        try:
            ipaddress.ip_address(host)
            raise ValueError('IP literal destinations are forbidden')
        except ValueError as e:
            if 'forbidden' in str(e): raise
        if host in ('localhost','localhost.localdomain') or '.' not in host or host.endswith(('.localhost','.local','.internal','.test','.invalid')):
            raise ValueError('Reserved hostname not permitted')
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        ips=[ipaddress.ip_address(x[4][0]) for x in addresses]
        if not ips or any(not ip.is_global for ip in ips):raise ValueError('Non-public destination blocked')
        return host,str(ips[0]),p
    except (ValueError,UnicodeError,socket.gaierror) as e:
        raise ValueError('Invalid or unsafe website: '+str(e)) from e


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname,ip):
        super().__init__(hostname,port=443,timeout=TIMEOUT,context=ssl.create_default_context())
        self.pinned_ip=ip
    def connect(self):
        sock=socket.create_connection((self.pinned_ip,443),timeout=TIMEOUT)
        self.sock=self._context.wrap_socket(sock,server_hostname=self.host)


def fetch_public(url):
    if os.environ.get('POLSIA_NETWORK_ENABLED')!='1':raise ValueError('Internet retrieval is not enabled')
    for step in range(MAX_REDIRECTS+1):
        host,ip,p=validated_destination(url)
        target=p.path or '/'
        if p.query:target+='?'+p.query
        conn=PinnedHTTPSConnection(host,ip)
        try:
            conn.request('GET',target,headers={'Host':host,'User-Agent':'PolsiaResearch/0.2 (+user-operated)','Accept':'text/html,text/plain','Accept-Encoding':'identity','Connection':'close'})
            r=conn.getresponse()
            if r.status in (301,302,303,307,308):
                if step==MAX_REDIRECTS:raise ValueError('Too many redirects')
                loc=r.getheader('Location')
                if not loc:raise ValueError('Redirect missing Location')
                url=urljoin(url,loc)
                continue
            if r.status!=200:raise ValueError('HTTP error '+str(r.status))
            typ=r.getheader('Content-Type','').lower()
            if not (typ.startswith('text/plain') or typ.startswith('text/html')):
                raise ValueError('Unsupported content type')
            size=r.getheader('Content-Length')
            if size and int(size)>MAX_BYTES:raise ValueError('Document too large')
            data=r.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise ValueError('Document exceeds byte limit')
            return {'url':url,'retrieved_at':int(time.time()),'sha256':hashlib.sha256(data).hexdigest(),
                    'size_bytes':len(data),'content_type':typ,'excerpt':data.decode('utf-8','replace')[:12000],
                    'evidence_status':'retrieved_unverified'}
        except (OSError,http.client.HTTPException) as e:
            raise ValueError('HTTPS retrieval failed: '+type(e).__name__) from e
        finally:conn.close()
    raise ValueError('Redirect limit reached')
