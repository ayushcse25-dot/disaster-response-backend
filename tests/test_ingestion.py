"""SACHET ingestion: parser on a saved real payload, dedupe, failure, association."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.flood_event import FloodEvent
from app.services.ingestion import sachet
from app.services.ingestion.association import candidate_event, match_event
from app.services.ingestion.fetcher import FetchError
from app.services.ingestion.runner import run_ingestion

FIXTURES = Path(__file__).parent / "fixtures"
CAP_BY_GUID = {
    "1791716545393016": "sachet_cap_flood_en.xml",
    "1791693599563013": "sachet_cap_flood_multilang.xml",
}


async def fake_fetch(url: str) -> bytes:
    if url == sachet.FEED_URL:
        return (FIXTURES / "sachet_rss_sample.xml").read_bytes()
    guid = url.rsplit("=", 1)[-1]
    return (FIXTURES / CAP_BY_GUID.get(guid, "sachet_cap_thunderstorm.xml")).read_bytes()


async def failing_fetch(url: str) -> bytes:
    raise FetchError("URLError")


def test_parser_reads_saved_payload_and_filters_floods():
    items = sachet.parse_rss((FIXTURES / "sachet_rss_sample.xml").read_bytes())
    assert len(items) == 4
    flood_guids = [i.guid for i in items if sachet.is_flood_text(i.title)]
    assert flood_guids == ["1791716545393016", "1791693599563013"]

    alert = sachet.parse_cap((FIXTURES / "sachet_cap_flood_multilang.xml").read_bytes())
    assert alert.event == "Flood" and alert.headline.startswith("River Ghaghra")  # English block
    now = datetime.now(timezone.utc)
    observation = sachet.to_observation(items[1], sachet.parse_cap(
        (FIXTURES / "sachet_cap_flood_en.xml").read_bytes()), now)
    assert (observation.state, observation.district) == ("Bihar", "Madhubani")
    assert observation.source_id == "ndma-sachet-cap" and not observation.is_sample
    assert observation.dedupe_key == "ndma-sachet-cap:1791716545393016"

    storm = sachet.parse_cap((FIXTURES / "sachet_cap_thunderstorm.xml").read_bytes())
    assert sachet.to_observation(items[2], storm, now) is None


def test_association_needs_same_district_and_never_uses_sample_events():
    now = datetime.now(timezone.utc)
    items = sachet.parse_rss((FIXTURES / "sachet_rss_sample.xml").read_bytes())
    alert = sachet.parse_cap((FIXTURES / "sachet_cap_flood_en.xml").read_bytes())
    observation = sachet.to_observation(items[1], alert, now)

    def event(event_id, district, sample=False, age=timedelta(hours=1)):
        return FloodEvent(event_id=event_id, title="Flood", location_name=district, state="Bihar",
                          district=district, is_sample=sample, last_observed_at=alert.sent - age)

    assert match_event(observation, [event("other", "Patna")]) is None
    assert match_event(observation, [event("s", "Madhubani", sample=True)]) is None
    assert match_event(observation, [event("old", "Madhubani", age=timedelta(days=5))]) is None
    assert match_event(observation, [event("m", "Madhubani")]).event_id == "m"
    new = candidate_event(observation, now)
    assert (new.status, new.verification_status) == ("CANDIDATE", "UNVERIFIED")


@pytest.mark.asyncio
async def test_rerun_does_not_duplicate(live_db):
    first = await run_ingestion(live_db, fetch=fake_fetch)
    counts = first["sources"][0]["last_counts"]
    assert counts["inserted"] == 2 and counts["events_created"] == 2
    second = await run_ingestion(live_db, fetch=fake_fetch)
    assert second["sources"][0]["last_counts"]["already_stored"] == 2
    assert await live_db["flood_observations"].count_documents({}) == 2
    assert await live_db["flood_events"].count_documents({"verification_status": "VERIFIED"}) == 0
    source = await live_db["sources"].find_one({"_id": "ndma-sachet-cap"})
    assert source["approval_status"] == "APPROVED" and source["is_sample"] is False


@pytest.mark.asyncio
async def test_failure_keeps_previous_data(live_db):
    await run_ingestion(live_db, fetch=fake_fetch)
    before = await live_db["flood_observations"].find({}).sort("_id").to_list()
    status = (await run_ingestion(live_db, fetch=failing_fetch))["sources"][0]
    assert status["status"] == "UNAVAILABLE" and status["last_error"] == "URLError"
    assert status["last_success_at"]
    assert await live_db["flood_observations"].find({}).sort("_id").to_list() == before
