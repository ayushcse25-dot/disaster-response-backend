"""Pure parsing and rule-based filtering for the NDMA SACHET CAP feed.

Feed: https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml (RSS 2.0,
<copyright>public domain</copyright>). Each RSS item links to a CAP 1.2 alert
with the event type, area description and timestamps.

No network access and no guessing here: an alert whose state cannot be read
from its area description is skipped, not assigned a location.
"""

import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict

from app.models.enums import EventVerificationStatus, ObservationType
from app.models.flood_observation import FloodObservation

SOURCE_ID = "ndma-sachet-cap"
FEED_URL = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}

# Flood terms (English and Hindi). "Heavy rain" alone is not treated as a flood.
FLOOD_PATTERN = re.compile(
    r"\bflood|inundat|waterlog|water-log|danger level|warning level|flash flood|बाढ़|जलभराव",
    re.IGNORECASE,
)

INDIAN_STATES = {
    s.casefold(): s for s in [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
        "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
        "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
        "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
        "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
        "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
        "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
    ]
}


class FeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guid: str
    title: str
    link: str
    author: str | None
    published_at: datetime | None


class CapAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str
    sender: str
    sent: datetime
    event: str
    severity: str | None
    headline: str
    description: str
    area_desc: str
    expires: datetime | None


class ParsedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    district: str | None
    location_name: str


def is_flood_text(*texts: str | None) -> bool:
    return any(t and FLOOD_PATTERN.search(t) for t in texts)


def parse_rss(payload: bytes) -> list[FeedItem]:
    root = ElementTree.fromstring(payload)
    items = []
    for node in root.iter("item"):
        guid = (node.findtext("guid") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not guid or not link:
            continue
        published = node.findtext("pubDate")
        try:
            published_at = parsedate_to_datetime(published) if published else None
        except (TypeError, ValueError):
            published_at = None
        items.append(FeedItem(
            guid=guid, title=" ".join((node.findtext("title") or "").split()), link=link,
            author=node.findtext("author"), published_at=published_at,
        ))
    return items


def _text(node: ElementTree.Element, path: str) -> str:
    return " ".join((node.findtext(path, default="", namespaces=CAP_NS) or "").split())


def parse_cap(payload: bytes) -> CapAlert | None:
    """Parse a CAP 1.2 alert, preferring the English info block. None if incomplete."""
    root = ElementTree.fromstring(payload)
    infos = root.findall("cap:info", CAP_NS)
    if not infos:
        return None
    info = next((i for i in infos if _text(i, "cap:language").lower().startswith("en")), infos[0])
    sent = _text(root, "cap:sent")
    area = _text(info, "cap:area/cap:areaDesc")
    if not sent or not area:
        return None
    try:
        sent_at = datetime.fromisoformat(sent)
        expires_text = _text(info, "cap:expires")
        expires = datetime.fromisoformat(expires_text) if expires_text else None
    except ValueError:
        return None
    if sent_at.tzinfo is None:
        return None
    return CapAlert(
        identifier=_text(root, "cap:identifier"), sender=_text(root, "cap:sender"), sent=sent_at,
        event=_text(info, "cap:event"), severity=_text(info, "cap:severity") or None,
        headline=_text(info, "cap:headline"), description=_text(info, "cap:description"),
        area_desc=area, expires=expires,
    )


def parse_location(area_desc: str) -> ParsedLocation | None:
    """Read state (and district when unambiguous) from a CAP areaDesc.

    "Kamla Balan, Jhanjarpur, Madhubani, Bihar" -> Bihar / Madhubani.
    "Ambala, Kaithal districts of Haryana" -> Haryana, no single district.
    """
    parts = [p.strip() for p in area_desc.split(",") if p.strip()]
    if not parts:
        return None
    last = parts[-1].casefold()
    if last in INDIAN_STATES:
        state = INDIAN_STATES[last]
        district = parts[-2] if len(parts) >= 2 else None
        return ParsedLocation(state=state, district=district, location_name=district or state)
    match = re.search(r"districts? of ([A-Za-z &]+)$", parts[-1])
    if match and match.group(1).strip().casefold() in INDIAN_STATES:
        state = INDIAN_STATES[match.group(1).strip().casefold()]
        return ParsedLocation(state=state, district=None, location_name=area_desc[:200])
    return None


def dedupe_key(item: FeedItem) -> str:
    return f"{SOURCE_ID}:{item.guid}"


def to_observation(item: FeedItem, alert: CapAlert, retrieved_at: datetime) -> FloodObservation | None:
    """Build an observation for a flood alert, or None if it is not a flood or has no state."""
    if "flood" not in alert.event.casefold() and not is_flood_text(alert.headline, alert.description):
        return None
    location = parse_location(alert.area_desc)
    if location is None:
        return None
    observation_type = (
        ObservationType.RIVER_LEVEL if alert.sender.upper() == "CWC" else ObservationType.FLOOD_FORECAST
    )
    title = alert.headline or item.title or alert.event
    return FloodObservation(
        observation_id="sachet-" + hashlib.sha1(item.guid.encode()).hexdigest()[:20],
        source_id=SOURCE_ID,
        observation_type=observation_type,
        title=title[:300] if len(title) >= 3 else f"{alert.event} alert",
        description=(alert.description or title)[:5000],
        summary=f"{alert.event} ({alert.severity or 'severity not given'}) — {alert.area_desc}"[:1000],
        location_name=location.location_name,
        state=location.state,
        district=location.district,
        observed_at=alert.sent,
        received_at=retrieved_at,
        retrieved_at=retrieved_at,
        source_url=item.link,
        verification_status=EventVerificationStatus.UNVERIFIED,
        evidence_reference=f"CAP {alert.identifier} from {alert.sender}"[:500],
        dedupe_key=dedupe_key(item),
        is_sample=False,
    )
