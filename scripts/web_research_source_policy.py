from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import control_data

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH = PROJECT_DIR / "data" / "control" / "web_research_supplement.json"
DEFAULT_SUPPLEMENTAL = PROJECT_DIR / "data" / "input" / "supplemental_showtime_sources.json"
DEFAULT_SOCIAL = PROJECT_DIR / "data" / "input" / "social_showtime_sources.json"
ATMOVIES_CODE_RE = re.compile(r"/showtime/(t[0-9a-z]+)/", re.IGNORECASE)
NUMERIC_ID_RE = re.compile(r"\d{6,}")


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def normalized_host(value: str) -> str:
    host = (urlparse(value).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def clean_template(value: str) -> str:
    return value.replace("{date}", "").strip()


def build_location_source_policy(
    master: dict,
    supplemental: dict | None = None,
    social: dict | None = None,
) -> dict[int, list[str]]:
    chains = {int(chain["id"]): chain for chain in master.get("chains", [])}
    policy: dict[int, list[str]] = defaultdict(list)

    def add(location_id: int, value: object) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        cleaned = clean_template(value)
        if cleaned not in policy[location_id]:
            policy[location_id].append(cleaned)

    for location in master.get("locations", []):
        if not location.get("active"):
            continue
        location_id = int(location["id"])
        chain = chains.get(int(location.get("chain_id", -1))) or {}
        for value in (
            location.get("location_url"),
            location.get("source_url"),
            chain.get("official_url"),
            chain.get("crawl_url"),
            chain.get("booking_url"),
        ):
            add(location_id, value)

    for source in (supplemental or {}).get("sources", []):
        if source.get("enabled", True):
            add(int(source["location_id"]), source.get("url_template"))

    for source in (social or {}).get("sources", []):
        location_id = int(source["location_id"])
        add(location_id, source.get("official_url"))
        add(location_id, source.get("deterministic_fallback"))
        for value in source.get("social_urls") or []:
            add(location_id, value)

    return dict(policy)


def source_url_allowed(candidate: str, configured_urls: list[str]) -> bool:
    if not isinstance(candidate, str) or not candidate.strip():
        return False
    candidate = candidate.strip()
    parsed_candidate = urlparse(candidate)
    candidate_host = normalized_host(candidate)
    if parsed_candidate.scheme not in {"http", "https"} or not candidate_host:
        return False

    for configured in configured_urls:
        parsed_base = urlparse(configured)
        base_host = normalized_host(configured)
        if not base_host or base_host != candidate_host:
            continue

        if base_host.endswith("atmovies.com.tw"):
            base_match = ATMOVIES_CODE_RE.search(parsed_base.path + "/")
            candidate_match = ATMOVIES_CODE_RE.search(parsed_candidate.path + "/")
            if base_match and candidate_match and base_match.group(1).lower() == candidate_match.group(1).lower():
                return True
            continue

        if base_host.endswith("facebook.com"):
            base_path = parsed_base.path.rstrip("/")
            candidate_path = parsed_candidate.path.rstrip("/")
            if base_path and candidate_path.startswith(base_path):
                return True
            base_ids = set(NUMERIC_ID_RE.findall(configured))
            candidate_ids = set(NUMERIC_ID_RE.findall(candidate))
            if base_ids and base_ids.intersection(candidate_ids):
                return True
            base_query_ids = set(sum(parse_qs(parsed_base.query).values(), []))
            candidate_query_ids = set(sum(parse_qs(parsed_candidate.query).values(), []))
            if base_query_ids and base_query_ids.intersection(candidate_query_ids):
                return True
            continue

        if base_host.endswith("instagram.com"):
            base_path = parsed_base.path.rstrip("/")
            candidate_path = parsed_candidate.path.rstrip("/")
            if base_path and candidate_path.startswith(base_path):
                return True
            if candidate_path.startswith(("/p/", "/reel/", "/tv/")):
                return True
            continue

        # For a cinema's configured official/ticketing domain, any HTTPS path on the same
        # host is acceptable. Location-specific third-party fallbacks such as @movies are
        # handled more strictly above.
        return True

    return False


def validate_payload_sources(payload: dict, master: dict, policy: dict[int, list[str]]) -> int:
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("web research supplement records must be a list")

    active_location_ids = {
        int(location["id"])
        for location in master.get("locations", [])
        if location.get("active")
    }

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record[{index}] must be an object")
        try:
            location_id = int(record.get("location_id"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"record[{index}] has invalid location_id") from exc
        if location_id not in active_location_ids:
            raise ValueError(f"record[{index}] references inactive/missing location_id={location_id}")

        source_url = str(record.get("source_url") or "").strip()
        configured = policy.get(location_id) or []
        if not source_url_allowed(source_url, configured):
            raise ValueError(
                f"record[{index}] source_url is not authorized for location_id={location_id}: {source_url!r}"
            )
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Require every 06:00 web-research source URL to match the target cinema's configured source policy."
    )
    parser.add_argument("--research", type=Path, default=DEFAULT_RESEARCH)
    parser.add_argument("--supplemental", type=Path, default=DEFAULT_SUPPLEMENTAL)
    parser.add_argument("--social", type=Path, default=DEFAULT_SOCIAL)
    args = parser.parse_args()

    research_path = args.research if args.research.is_absolute() else PROJECT_DIR / args.research
    supplemental_path = args.supplemental if args.supplemental.is_absolute() else PROJECT_DIR / args.supplemental
    social_path = args.social if args.social.is_absolute() else PROJECT_DIR / args.social

    payload = load_json(research_path)
    master = control_data.load_cinema_master()
    supplemental = load_json(supplemental_path) if supplemental_path.exists() else {"sources": []}
    social = load_json(social_path) if social_path.exists() else {"sources": []}
    policy = build_location_source_policy(master, supplemental, social)
    count = validate_payload_sources(payload, master, policy)
    print(f"[web research source policy] PASS records={count} locations_with_policy={len(policy)}")


if __name__ == "__main__":
    main()
