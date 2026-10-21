"""Exercise live API + separate worker; use a real authorized JPEG/PNG input."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from agrovision.config import get_settings
from agrovision.identity.auth import create_dev_token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--crop", required=True, choices=["wheat", "potato", "tomato"])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("runs/live-e2e.json"))
    args = parser.parse_args()
    settings = get_settings()
    token = create_dev_token(settings, "e2e-demo")
    other = create_dev_token(settings, "e2e-other-user")
    with httpx.Client(base_url=args.url, headers={"Authorization": "Bearer " + token}, timeout=30) as client:
        ready_deadline = time.monotonic() + 20
        while True:
            try:
                health = client.get('/health/ready')
                if health.status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            if time.monotonic() >= ready_deadline:
                raise RuntimeError('API readiness check failed; start API and apply migrations first')
            time.sleep(0.25)
        me = client.get("/v1/me")
        me.raise_for_status()
        catalog = client.get("/v1/catalog")
        catalog.raise_for_status()
        observation = client.post(
            "/v1/observations",
            json={
                "client_observation_id": str(uuid4()),
                "crop_id": args.crop,
                "organ": "leaf",
                "captured_at": datetime.now(UTC).isoformat(),
            },
        )
        assert observation.status_code == 201, observation.text
        oid = observation.json()["id"]
        with args.image.open("rb") as stream:
            photo = client.post(
                f"/v1/observations/{oid}/photos",
                data={"client_photo_id": str(uuid4()), "purpose": "primary"},
                files={"file": (args.image.name, stream, "image/jpeg")},
            )
        assert photo.status_code == 201, photo.text
        pid = photo.json()["id"]
        photo_url = client.get(f"/v1/photos/{pid}/content-url").json()["url"]
        assert client.get(photo_url).status_code == 200
        body = {"observation_id": oid, "primary_photo_id": pid}
        key = str(uuid4())
        queued = client.post("/v1/assessments", json=body, headers={"Idempotency-Key": key})
        assert queued.status_code == 202, queued.text
        aid = queued.json()["id"]
        states = [queued.json()["status"]]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            assessment = client.get("/v1/assessments/" + aid)
            assessment.raise_for_status()
            data = assessment.json()
            if data["status"] != states[-1]:
                states.append(data["status"])
            if data["status"] in {"completed", "failed"}:
                break
            time.sleep(0.5)
        assert data["status"] == "completed", data
        assert data["result"]["outcome"] == "inconclusive", data
        assert data["result"]["prediction"] is None
        replay = client.post("/v1/assessments", json=body, headers={"Idempotency-Key": key})
        assert replay.status_code == 200 and replay.json() == data
        assert replay.headers["Idempotency-Replayed"] == "true"
        for path in [
            f"/v1/observations/{oid}",
            f"/v1/photos/{pid}/content-url",
            photo_url,
            f"/v1/assessments/{aid}",
        ]:
            assert client.get(path, headers={"Authorization": "Bearer " + other}).status_code == 404
        report = {
            "checked_at": datetime.now(UTC).isoformat(),
            "crop": args.crop,
            "processing_states_observed": states,
            "assessment": data,
            "idempotent_replay": "passed",
            "cross_owner_reads": "denied",
            "input_photo": "authorized public research dataset sample; not a user diagnostic case",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(
            f"PASS live {args.crop}: {' → '.join(states)}, {data['result']['outcome']}, "
            f"{len(data['result']['candidates'])} real candidates; replay/ownership passed; report {args.output}"
        )


if __name__ == "__main__":
    main()
