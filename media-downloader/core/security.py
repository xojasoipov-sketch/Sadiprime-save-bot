"""URL validation and SSRF protection.

Every URL a user sends is untrusted input. This module is the single choke
point through which every URL must pass before it is handed to yt-dlp or
any network client. It:

  * only allows http(s)
  * rejects localhost / loopback / private / link-local / reserved IPs
    (both literal IPs and DNS names that resolve to them)
  * only allows an explicit domain allowlist per platform
  * normalizes the URL (strips fragments, tracking noise is left to the
    adapters since some platforms need query params)

This is defense in depth: yt-dlp itself will also fetch the URL, but we
never want to hand it something pointing at the Docker network, the host's
loopback interface, or an internal SadiPrime service.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}

# Platform -> allowed hostnames (exact match, case-insensitive, after
# stripping a leading "www.").
PLATFORM_DOMAINS: dict[str, set[str]] = {
    "instagram": {"instagram.com"},
    "tiktok": {
        "tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
        "m.tiktok.com",
    },
    "youtube": {"youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"},
    "pinterest": {"pinterest.com", "pin.it"},
}

# Regional Pinterest/TikTok TLD variants can be added here later without
# touching detection logic elsewhere.
ADDITIONAL_REGIONAL_DOMAINS: dict[str, set[str]] = {
    "pinterest": {f"pinterest.{tld}" for tld in ("co.uk", "fr", "de", "jp", "com.au")},
}
for _platform, _domains in ADDITIONAL_REGIONAL_DOMAINS.items():
    PLATFORM_DOMAINS[_platform] |= _domains

ALL_ALLOWED_DOMAINS: set[str] = set().union(*PLATFORM_DOMAINS.values())

_BLOCKED_HOSTNAME_SUBSTRINGS = ("localhost",)

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


class InvalidUrlError(ValueError):
    """Raised when a URL fails validation (malformed, disallowed scheme/domain, SSRF risk)."""


@dataclass(frozen=True)
class ValidatedUrl:
    raw: str
    normalized: str
    hostname: str
    platform: str


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _is_private_or_reserved_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolves_to_blocked_ip(hostname: str) -> bool:
    """Best-effort DNS resolution check to block SSRF via DNS rebinding.

    Fails closed: if resolution errors out, we treat it as blocked rather
    than silently allowing an unverifiable host through.
    """

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        if _is_private_or_reserved_ip(ip_str):
            return True
    return False


def normalize_and_validate_url(url: str, *, check_dns: bool = True) -> ValidatedUrl:
    """Validate `url` and return a normalized representation.

    Raises InvalidUrlError for anything unsafe or unsupported.
    """

    if not url or not isinstance(url, str):
        raise InvalidUrlError("Empty URL")

    url = url.strip()
    if len(url) > 2048:
        raise InvalidUrlError("URL too long")

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise InvalidUrlError(f"Malformed URL: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise InvalidUrlError(f"Unsupported scheme: {scheme or '(none)'}")

    if not parts.hostname:
        raise InvalidUrlError("URL has no hostname")

    hostname = parts.hostname.lower()

    if any(sub in hostname for sub in _BLOCKED_HOSTNAME_SUBSTRINGS):
        raise InvalidUrlError("Blocked hostname")

    # Literal IP addresses are never allowed — we only accept named
    # platform domains.
    if _is_private_or_reserved_ip(hostname):
        raise InvalidUrlError("Blocked private/reserved IP address")
    try:
        ipaddress.ip_address(hostname)
        raise InvalidUrlError("Literal IP addresses are not allowed")
    except ValueError:
        pass

    if not _HOSTNAME_RE.match(hostname):
        raise InvalidUrlError("Invalid hostname format")

    bare_host = _strip_www(hostname)
    if bare_host not in ALL_ALLOWED_DOMAINS and hostname not in ALL_ALLOWED_DOMAINS:
        raise InvalidUrlError(f"Domain not allowed: {hostname}")

    if check_dns and _resolves_to_blocked_ip(hostname):
        raise InvalidUrlError("Hostname resolves to a blocked address")

    platform = _platform_for_host(bare_host)
    if platform is None:
        raise InvalidUrlError(f"Domain not mapped to a platform: {hostname}")

    # Normalize: keep scheme+host+path+query, force https, drop fragment.
    normalized = urlunsplit(("https", hostname, parts.path or "/", parts.query, ""))

    return ValidatedUrl(raw=url, normalized=normalized, hostname=hostname, platform=platform)


def _platform_for_host(bare_host: str) -> str | None:
    for platform, domains in PLATFORM_DOMAINS.items():
        for domain in domains:
            if bare_host == domain or bare_host.endswith("." + domain):
                return platform
    return None


_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str, *, max_length: int = 150) -> str:
    """Sanitize an arbitrary string into a safe filename component.

    Strips path separators, null bytes, and anything outside a
    conservative allowlist, and rejects traversal sequences.
    """

    name = name.replace("\x00", "")
    name = name.replace("/", "_").replace("\\", "_")
    name = _FILENAME_SAFE_RE.sub("_", name)
    name = name.strip("._")
    if not name:
        name = "file"
    if name in {".", ".."}:
        name = "file"
    return name[:max_length]
