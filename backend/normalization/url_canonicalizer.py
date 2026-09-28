"""URL canonicalization, tracking parameter removal, and redirect resolution."""

import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger("job_intelligence.normalization.url")

# Known marketing and telemetry tracking query parameters that are safe to remove
TRACKING_QUERY_PARAMS = {
    # Google Analytics / Urchin
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_reader",
    # Ad Network Click IDs
    "gclid",
    "fbclid",
    "msclkid",
    "twclid",
    "igshid",
    "ttclid",
    "dclid",
    "wbraid",
    "gbraid",
    # Platform / Aggregator Referral Tracking
    "ref",
    "refid",
    "reference",
    "trk",
    "trackingid",
    "tracking_id",
    "tracking",
    "origin",
    "source",
    "gh_src",
    "lever-source",
    "hire_src",
    "indeed_src",
    "li_fat_id",
    # Email & Marketing Automation
    "mc_cid",
    "mc_eid",
    "_hsenc",
    "_hsmi",
    "vero_id",
    "vero_conv",
}

# Critical query parameters that must NEVER be stripped because they identify the job or routing
CRITICAL_JOB_PARAMS = {
    "id",
    "job_id",
    "jobid",
    "jid",
    "gh_jid",  # Greenhouse embedded iframe job id
    "req",
    "req_id",
    "reqid",
    "requisition_id",
    "posting_id",
    "position_id",
    "role",
    "slug",
    "p",
    "code",
}


def normalize_url(url: str) -> str:
    """Normalize a URL to canonical form.

    Operations performed:
    1. Strip leading and trailing whitespace.
    2. Lowercase protocol scheme and network domain.
    3. Remove redundant default ports (:80 on http, :443 on https).
    4. Remove safe marketing tracking parameters while preserving critical job identifiers.
    5. Sort preserved query parameters deterministically.
    6. Remove unnecessary trailing slash on paths.
    7. Remove fragment anchors (#...) unless the fragment contains an SPA path route.
    """
    if not url or not url.strip():
        return ""

    raw_url = url.strip()
    if not (raw_url.lower().startswith("http://") or raw_url.lower().startswith("https://")):
        raw_url = "https://" + raw_url


    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default port numbers
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Standardize hostname: strip www prefix for domain canonicalization
    if netloc.startswith("www.") and len(netloc) > 4:
        netloc = netloc[4:]

    # Clean path
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Filter and sort query parameters
    filtered_params: list[tuple[str, str]] = []
    if parsed.query:
        for k, v in parse_qsl(parsed.query, keep_blank_values=False):
            k_lower = k.lower().strip()
            # If it's a known tracking parameter and not a critical job parameter, remove it
            if k_lower in TRACKING_QUERY_PARAMS and k_lower not in CRITICAL_JOB_PARAMS:
                continue
            # Remove any generic utm_ prefixed parameter
            if k_lower.startswith("utm_"):
                continue
            filtered_params.append((k, v))

    # Sort deterministically
    filtered_params.sort(key=lambda item: (item[0], item[1]))
    new_query = urlencode(filtered_params)

    # Clean fragment: keep SPA hash routes like #/jobs/123, otherwise drop
    fragment = parsed.fragment
    if fragment and not (fragment.startswith("/") or "/" in fragment):
        fragment = ""

    return urlunparse((
        scheme,
        netloc,
        path,
        parsed.params,
        new_query,
        fragment,
    ))


def extract_canonical_from_html(html_text: str) -> str | None:
    """Extract <link rel="canonical" href="..."> from HTML document if present."""
    if not html_text:
        return None
    match = re.search(
        r'<link\s+[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r'<link\s+[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']',
            html_text,
            re.IGNORECASE,
        )
    return match.group(1).strip() if match else None


def resolve_redirects(url: str, timeout: float = 3.0) -> str:
    """Follow HTTP redirects to discover the destination canonical URL (e.g. for link shorteners)."""
    norm_orig = normalize_url(url)
    if not norm_orig:
        return url

    # Only follow redirects for known shorteners or tracking redirects to keep it fast
    shortener_domains = {"bit.ly", "lnkd.in", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "buff.ly"}
    parsed = urlparse(norm_orig)
    if parsed.netloc.lower() not in shortener_domains:
        return norm_orig

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.head(norm_orig, headers={"User-Agent": "JobIntelligencePlatform/1.0"})
            if resp.status_code < 400:
                return normalize_url(str(resp.url))
            # Fallback to GET with stream to avoid downloading full body
            with client.stream("GET", norm_orig, headers={"User-Agent": "JobIntelligencePlatform/1.0"}) as stream_resp:
                return normalize_url(str(stream_resp.url))
    except Exception as e:
        logger.debug("Redirect resolution skipped for '%s': %s", url, e)
        return norm_orig
