"""Page content inspector and 15-point conservative verification analyzer."""

import html
import logging
import re

import httpx

from backend.normalization.normalizer import normalize_company, normalize_title
from backend.verification.schemas import ExtractedPageSignals

logger = logging.getLogger("job_intelligence.verification.inspector")

# Specific cues identifying expired or filled vacancies
EXPIRED_CUES = [
    r"this job has expired",
    r"this position has been filled",
    r"this job is no longer available",
    r"no longer accepting applications",
    r"this posting is closed",
    r"position closed",
    r"job is closed",
    r"job has closed",
    r"applications are now closed",
    r"this listing has expired",
    r"the job you are trying to view is no longer available",
    r"this vacancy is no longer open",
    r"this requisition has been closed",
    r"role has been filled",
    r"we are no longer hiring for this position",
]

# Cues identifying login walls
LOGIN_WALL_CUES = [
    r"please sign in to view this job",
    r"sign in to apply",
    r"log in to view",
    r"login required",
    r"you must be signed in to apply",
    r"members only",
    r"log in or sign up to view",
]

# Cues identifying blocked access or bot challenges
ACCESS_DENIED_CUES = [
    r"access denied",
    r"403 forbidden",
    r"request blocked",
    r"attention required! \| cloudflare",
    r"verify you are human",
    r"security check to continue",
    r"bot detected",
    r"waf block",
]

# Cues identifying active application actions
APPLICATION_MECHANISM_CUES = [
    r"apply now",
    r"apply for this job",
    r"apply for this role",
    r"submit application",
    r"start application",
    r"apply with linkedin",
    r"easy apply",
    r"attach resume",
    r"upload resume",
    r"application form",
]


class PageInspector:
    """Performs deep inspection of HTML/text content across all 15 verification criteria."""

    def __init__(self, timeout: float = 8.0, custom_client: httpx.Client | None = None) -> None:
        self.timeout = timeout
        self.custom_client = custom_client

    def fetch_page(self, url: str) -> tuple[int | None, str | None, str, dict[str, str]]:
        """Fetch remote web page following redirects.

        Returns:
            Tuple of (status_code, final_url, html_body, response_headers)
        """
        if self.custom_client:
            resp = self.custom_client.get(
                url,
                headers={"User-Agent": "JobIntelligencePlatform/1.0 (Verification Probe)"},
            )
            return resp.status_code, str(resp.url), resp.text, dict(resp.headers)

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=self.timeout,
                verify=True,
            ) as client:
                resp = client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36 JobIntelligence/1.0"
                        ),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                return resp.status_code, str(resp.url), resp.text, dict(resp.headers)
        except httpx.HTTPStatusError as e:
            return e.response.status_code, str(e.response.url), e.response.text, dict(e.response.headers)
        except Exception as e:
            logger.debug("Fetch failed for '%s': %s", url, e)
            return None, None, "", {}

    def inspect_html(
        self,
        html_content: str,
        expected_title: str,
        expected_company: str,
        expected_location: str | None = None,
        status_code: int = 200,
        final_url: str | None = None,
    ) -> ExtractedPageSignals:
        """Inspect page body for all signals, title, company, active forms, and expiration markers."""
        signals = ExtractedPageSignals(
            http_status=status_code,
            final_url=final_url,
        )

        # Clean text
        raw_text = html.unescape(html_content)
        cleaned_text = re.sub(r"(?i)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_text, flags=re.DOTALL)
        clean_text_no_tags = re.sub(r"<[^>]+>", " ", cleaned_text)
        normalized_body = re.sub(r"\s+", " ", clean_text_no_tags).strip()
        lower_body = normalized_body.lower()

        signals.page_text_length = len(normalized_body)

        # 1. Detect 404 / 410 / Soft-404
        if status_code in (404, 410) or any(
            err in lower_body[:500] for err in ["404 not found", "page not found", "error 404", "job not found"]
        ):
            signals.is_soft_404 = True
            signals.cues_detected.append("not_found")

        # 2. Detect Obvious Expired-Job Pages
        for cue in EXPIRED_CUES:
            if re.search(cue, lower_body):
                signals.is_expired_notice = True
                signals.cues_detected.append(f"expired_cue:{cue}")
                break

        # 3. Detect Login-Only Pages
        for cue in LOGIN_WALL_CUES:
            if re.search(cue, lower_body):
                signals.is_login_wall = True
                signals.cues_detected.append(f"login_wall:{cue}")
                break

        # 4. Detect Access Denied / Cloudflare Challenge
        if status_code in (401, 403):
            signals.is_access_denied = True
        for cue in ACCESS_DENIED_CUES:
            if re.search(cue, lower_body):
                signals.is_access_denied = True
                signals.cues_detected.append(f"access_denied:{cue}")
                break

        # 5. Confirm Substantive Job Content
        job_structure_keywords = [
            "experience",
            "requirements",
            "skills",
            "responsibilities",
            "role",
            "qualifications",
            "description",
            "team",
            "engineer",
            "developer",
            "apply",
            "hiring",
            "job",
            "position",
        ]
        found_kw_count = sum(1 for kw in job_structure_keywords if kw in lower_body)
        if len(normalized_body) >= 60 and found_kw_count >= 1:
            signals.has_substantive_content = True


        # 6. Confirm Job Title
        norm_expected_title = normalize_title(expected_title).lower()
        title_tokens = [t for t in norm_expected_title.split() if len(t) > 2]
        # Match if core title string appears or majority of distinctive tokens appear
        matched_tokens = [t for t in title_tokens if t in lower_body]
        if norm_expected_title in lower_body or (title_tokens and len(matched_tokens) / len(title_tokens) >= 0.70):
            signals.title_matched = True
            signals.detected_title = expected_title

        # 7. Confirm Company
        norm_expected_comp = normalize_company(expected_company).lower()
        comp_tokens = [t for t in norm_expected_comp.split() if len(t) > 2]
        if norm_expected_comp in lower_body or any(t in lower_body for t in comp_tokens):
            signals.company_matched = True
            signals.detected_company = expected_company

        # 8. Confirm Location
        if not expected_location or expected_location.lower() == "remote":
            signals.location_matched = True
        else:
            loc_parts = [p.strip().lower() for p in expected_location.split(",") if len(p.strip()) > 2]
            if any(p in lower_body for p in loc_parts) or "remote" in lower_body:
                signals.location_matched = True

        # 9. Detect Active Application Mechanism
        # Check for HTML forms, application buttons, file upload inputs, or apply links
        has_form_or_upload = bool(re.search(r"<form[^>]*>", raw_text, re.IGNORECASE)) or "type=\"file\"" in raw_text.lower()
        has_apply_phrase = any(re.search(cue, lower_body) for cue in APPLICATION_MECHANISM_CUES)

        # Check for explicit apply links in HTML
        apply_links = re.findall(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(?:[^<]*apply[^<]*)</a>',
            raw_text,
            re.IGNORECASE,
        )
        signals.application_links_found = apply_links[:5]

        if has_form_or_upload or has_apply_phrase or bool(apply_links):
            signals.has_active_application = True

        return signals

    def verify_application_url(self, app_url: str) -> tuple[int | None, bool]:
        """Separately verify that the dedicated application submission URL is currently responsive."""
        if not app_url:
            return None, False

        status, final_url, body, _ = self.fetch_page(app_url)
        if status is None:
            return None, False

        is_usable = (
            status < 400
            and not any(err in body.lower()[:400] for err in ["404 not found", "page not found", "expired"])
        )
        return status, is_usable
