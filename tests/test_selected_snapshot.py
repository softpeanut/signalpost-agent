from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import profiles_from_bulk  # noqa: E402
from norway_company_agent.sampling import iter_bulk  # noqa: E402


def _entity() -> dict:
    return {
        "organisasjonsnummer": "985589003",
        "navn": "ARKITEKTFIRMA JON VIKØREN AS",
        "organisasjonsform": {"kode": "AS"},
        "antallAnsatte": 3,
        "konkurs": False,
        "underAvvikling": False,
        "forretningsadresse": {"kommune": "VIK", "kommunenummer": "4639"},
        "naeringskode1": {"kode": "71.110", "beskrivelse": "Arkitektvirksomhet"},
        "hjemmeside": "https://example.test",
        "sisteInnsendteAarsregnskap": "2025",
    }


def test_selected_json_snapshot_preserves_identity_raw_evidence_and_source() -> None:
    row = _entity()
    body = {
        "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter",
        "_embedded": {"enheter": [row]},
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "snapshot.json"
        raw = json.dumps(body, ensure_ascii=False).encode()
        path.write_bytes(raw)
        profiles, metadata = profiles_from_bulk(path, ["985589003"])

    profile = profiles[0]
    assert profile["organisation_number"] == "985589003"
    assert profile["employees"] == 3
    assert profile["municipality_number"] == "4639"
    registry = profile["evidence"]["registry"]
    assert registry["value"] == row
    assert registry["source_url"] == "https://data.brreg.no/enhetsregisteret/api/enheter"
    assert registry["content_sha256"] == hashlib.sha256(raw).hexdigest()
    assert registry["source_row_key"] == "985589003"
    assert metadata["registry_snapshot_source_urls"] == ["https://data.brreg.no/enhetsregisteret/api/enheter"]


def test_selected_json_snapshot_rejects_missing_embedded_entities() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "snapshot.json"
        path.write_text("{}", encoding="utf-8")
        try:
            list(iter_bulk(path))
        except ValueError as exc:
            assert str(exc) == "Registry JSON snapshot must contain _embedded.enheter"
        else:
            raise AssertionError("expected ValueError")
