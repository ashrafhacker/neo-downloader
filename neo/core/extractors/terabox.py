"""Custom Terabox "TeraPlayer" resolver + yt-dlp extractor.

yt-dlp dropped its built-in TeraboxIE in 2026, so Terabox links fail with
"Unsupported URL". This module resolves a Terabox share link (surl token) to a
direct download URL server-side, the same way sites like iTeraPlay work:
the USER only pastes the link; the SERVER calls Terabox's `share/list` API
with a cookie it holds (operator-configured TERABOX_COOKIE, else an anonymous
public cookie) and a jsToken scraped from the share page.

The resolution is done with plain urllib (not yt-dlp's redirect-following
webpage fetcher) so the 302 from terabox.com -> terabox.app never re-dispatches
through yt-dlp's generic extractor. `resolve_terabox()` is the reusable core;
`TeraboxIE` wraps it for the existing /info and /download flow.
"""
import re
import os
import json
import urllib.request
import urllib.error

from yt_dlp.extractor.common import InfoExtractor

# Single-line (no VERBOSE) so yt-dlp's _match_valid_url compiles it correctly.
_TERABOX_HOST_RE = r'(?:www\.)?(?:1024terabox\.com|1024tera\.com|terabox\.com|teraboxapp\.com|terabox\.app|terabox\.link|dubox\.com|dubox\.link|4funbox\.com|freeterabox\.com|neoterabox\.com|terabox\.tech|terabox\.share|terabox\.ink|terabox\.to|terabox\.pro)'

# Accept both the /s/<token> short form and /sharing/link?surl=<token>.
_TERABOX_RE = r'https?://' + _TERABOX_HOST_RE + r'/?(?:s/|sharing/link)?(?:[?\w/-]*)'

_SURL_RE = re.compile(r'(?:[?&]surl=|/s/)([A-Za-z0-9_-]+)')
_JSTOKEN_RE = re.compile(r'[\'"\s]jsToken[\'"]?\s*[:=]\s*[\'"]([A-Za-z0-9_.-]+)[\'"]')

_API_BASE = 'https://www.terabox.com'
_WEB_BASE = 'https://www.terabox.com'

_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

# Built-in anonymous cookie used for public shares when no TERABOX_COOKIE is
# configured. Terabox accepts a generic lang/ndus pair for public links; this
# lets "just paste a link" work without any operator setup.
_ANON_COOKIE = 'lang=en; ndus=; browser_id=neoterabox;'


def _surl(url):
    m = _SURL_RE.search(url or '')
    return m.group(1) if m else None


def _cookie_header(raw):
    """Turn Netscape/name=value cookie text into a `name=value; ...` header."""
    if not raw:
        return None
    pairs = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = re.split(r'[ \t]+', line)
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
        elif '=' in line:
            pairs.append(line)
    return '; '.join(pairs) if pairs else None


def _http_get(url, headers, timeout=20):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            charset = r.headers.get_content_charset() or 'utf-8'
            return r.read().decode(charset, errors='ignore')
    except urllib.error.HTTPError as e:
        # 403/404 still often carry a body worth scraping for jsToken.
        try:
            return e.read().decode('utf-8', errors='ignore')
        except Exception:
            return ''
    except Exception:
        return ''


def resolve_terabox(url, cookiefile=None):
    """Resolve a Terabox share link to a direct download.

    Returns a dict with title/url/ext/filesize/http_headers, or raises a
    ValueError with a clear message. The user supplies only the link; the
    server supplies the cookie (TERABOX_COOKIE env, cookiefile, or anonymous).
    """
    surl = _surl(url)
    if not surl:
        raise ValueError(
            "Could not find a Terabox sharing token (surl) in the URL."
        )

    # Cookie priority: per-request cookiefile > TERABOX_COOKIE env > anon.
    raw = None
    if cookiefile and os.path.isfile(cookiefile):
        try:
            raw = open(cookiefile, 'r', errors='ignore').read()
        except OSError:
            raw = None
    if not raw:
        raw = os.environ.get('TERABOX_COOKIE', '').strip()
    cookie = _cookie_header(raw) or _ANON_COOKIE

    headers = {
        'User-Agent': _USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Referer': _WEB_BASE + '/',
        'Cookie': cookie,
    }

    # 1. Fetch the share page HTML to extract the jsToken CSRF value.
    webpage = _http_get(url, headers)
    if not webpage:
        # Try the canonical /s/<token> form in case the mirror was unreachable.
        webpage = _http_get(f"{_WEB_BASE}/s/{surl}", headers)
    js_token = None
    if webpage:
        m = _JSTOKEN_RE.search(webpage)
        js_token = m.group(1) if m else None
    if not js_token:
        raise ValueError(
            "Could not read Terabox's jsToken from the share page. The share "
            "may be unavailable, or your server IP is blocked. If this is a "
            "private share, set the TERABOX_COOKIE env var."
        )

    # 2. Resolve the surl via the sharing API.
    api_url = (
        f"{_API_BASE}/share/list?app_id=250528&shorturl=1&web=1"
        f"&channel=0&scheme=https&surls={surl}&jsToken={js_token}"
    )
    body = _http_get(api_url, headers)
    if not body:
        raise ValueError("Terabox API returned an empty response.")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise ValueError("Terabox API returned a non-JSON response.")

    errno = data.get('errno')
    if errno not in (0, None):
        msg = data.get('errmsg') or 'unknown error'
        if errno == 2 or 'login' in str(msg).lower() or 'cookie' in str(msg).lower():
            raise ValueError(
                "This Terabox share needs a logged-in session. Set the "
                "TERABOX_COOKIE env var on the server with a terabox.com "
                "account cookie, then retry."
            )
        if errno == -6 or 'token' in str(msg).lower():
            raise ValueError(
                "Terabox rejected the jsToken. The share page may have "
                "changed; retry or set TERABOX_COOKIE."
            )
        raise ValueError(f"Terabox API error: {msg}")

    records = data.get('list') or []
    if not records:
        raise ValueError(
            "Terabox returned no files for this link. The share may be "
            "private, expired, or require a logged-in session."
        )

    record = records[0]
    dlink = (
        record.get('dlink')
        or record.get('download_url')
        or ((record.get('urls') or {}).get('url')
            if isinstance(record.get('urls'), dict) else None)
    )
    if not dlink:
        raise ValueError(
            "Terabox resolved the file but returned no download link."
        )

    title = record.get('server_filename') or record.get('filename') or surl
    size = record.get('size') or 0
    ext = (title.rsplit('.', 1)[-1].lower() if '.' in title else 'bin')
    return {
        'id': surl,
        'title': title,
        'url': dlink,
        'ext': ext,
        'filesize': size,
        'http_headers': dict(headers),
    }


class TeraboxIE(InfoExtractor):
    IE_NAME = 'terabox'
    IE_DESC = 'terabox.com and mirror file hosts (TeraPlayer)'
    _VALID_URL = _TERABOX_RE

    def _real_extract(self, url):
        cookiefile = (self._downloader.params.get('cookiefile')
                      if self._downloader else None)
        try:
            res = resolve_terabox(url, cookiefile=cookiefile)
        except ValueError as e:
            self.report_error(str(e))
            return None
        return {
            'id': res['id'],
            'title': res['title'],
            'url': res['url'],
            'ext': res['ext'],
            'filesize': res['filesize'],
            'http_headers': res['http_headers'],
        }


def register():
    """Inject TeraboxIE into yt-dlp's extractor registry at runtime."""
    import yt_dlp.extractor as extractor_mod

    extractor_mod.import_extractors()

    ctx = extractor_mod._extractors_context.value
    ctx[TeraboxIE.IE_NAME] = TeraboxIE

    setattr(extractor_mod, 'TeraboxIE', TeraboxIE)
