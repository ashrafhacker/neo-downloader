"""Custom yt-dlp extractor for diskwala.com.

diskwala is a Cloudflare-fronted SPA with no built-in yt-dlp support. This
extractor claims diskwala URLs and attempts several strategies to find a
playable source so the link flows through the standard player like any other
platform:

1. Parse JSON-LD / <meta> tags for a direct video URL.
2. Scan the rendered HTML for <video>/<source> or HLS (.m3u8) URLs.
3. Fall back to yt-dlp's generic extractor.
"""
import re
import json

from yt_dlp.extractor.common import InfoExtractor

_DISKWALA_RE = r'https?://(?:www\.)?diskwala\.com/'

_VIDEO_SRC_RE = re.compile(
    r'(?:src|data-src|data-source)\s*=\s*["\'](https?://[^"\']+\.(?:mp4|webm|m3u8)(?:[^"\']*)?)["\']',
    re.IGNORECASE,
)
_M3U8_RE = re.compile(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', re.IGNORECASE)
_DIRECT_RE = re.compile(r'(https?://[^\s"\']+\.(?:mp4|webm)(?:\?[^"\']*)?)', re.IGNORECASE)


class DiskWalaIE(InfoExtractor):
    IE_NAME = 'diskwala'
    IE_DESC = 'diskwala.com video/file host'
    _VALID_URL = _DISKWALA_RE + r'.*'

    _REQUEST_HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/json,*/*',
        'Referer': 'https://www.diskwala.com/',
    }

    def _real_extract(self, url):
        # Try our targeted parsing first.
        webpage = self._download_webpage(
            url, None, headers=self._REQUEST_HEADERS, fatal=False
        )
        if webpage:
            entry = self._parse_page(url, webpage)
            if entry:
                return entry

        # Fall back to yt-dlp's generic extractor for this single URL.
        from yt_dlp.extractor.generic import GenericIE
        generic = GenericIE(self._downloader)
        return generic._real_extract(url)

    def _parse_page(self, url, webpage):
        title = self._og_search_title(webpage, default=None) or self._html_search_regex(
            r'<title>(.*?)</title>', webpage, 'title', default=url
        )

        # 1. JSON-LD
        for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', webpage, re.S):
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            content = data.get('contentUrl') or (data.get('video') or {}).get('contentUrl')
            if content:
                return self._make_entry(url, title, content)

        # 2. Direct video / HLS sources
        for m in _VIDEO_SRC_RE.finditer(webpage):
            return self._make_entry(url, title, m.group(1))
        m = _M3U8_RE.search(webpage)
        if m:
            return self._make_entry(url, title, m.group(1))
        m = _DIRECT_RE.search(webpage)
        if m:
            return self._make_entry(url, title, m.group(1))
        return None

    def _make_entry(self, url, title, src):
        ext = 'm3u8' if src.endswith('.m3u8') else (src.rsplit('.', 1)[-1].split('?')[0] or 'mp4')
        return {
            'id': re.sub(r'\W+', '_', url),
            'title': title,
            'url': src,
            'ext': ext,
            'http_headers': self._REQUEST_HEADERS,
        }


def register():
    """Inject DiskWalaIE into yt-dlp's extractor registry at runtime."""
    import yt_dlp.extractor as extractor_mod

    # Ensure the built-in registry is populated first.
    extractor_mod.import_extractors()

    # _extractors_context holds the live registry dict (IE_NAME -> class).
    ctx = extractor_mod._extractors_context.value
    ctx[DiskWalaIE.IE_NAME] = DiskWalaIE

    # Keep the module importable for plugins/debugging.
    setattr(extractor_mod, 'DiskWalaIE', DiskWalaIE)

