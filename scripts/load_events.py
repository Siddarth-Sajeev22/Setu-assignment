"""Load sample events by calling the running API."""
import json
import os
import sys
from typing import Optional

import httpx


def load_events_from_file(filepath: str, base_url: str, sample_size: Optional[int] = None):
    print(f"Loading events from {filepath} → {base_url}/events ...")

    with open(filepath, "r") as f:
        events = json.load(f)

    if sample_size:
        events = events[:sample_size]

    print(f"Found {len(events)} events to load")

    successful = 0
    duplicates = 0
    errors = 0

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        for i, event_data in enumerate(events):
            try:
                response = client.post("/events", json=event_data)

                if response.status_code == 201:
                    successful += 1
                elif response.status_code == 200:
                    duplicates += 1
                else:
                    errors += 1
                    print(f"Event {i} failed ({response.status_code}): {response.text}")

            except httpx.RequestError as e:
                errors += 1
                print(f"Event {i} request error: {e}")

            if (i + 1) % 1000 == 0:
                print(f"  {i + 1} sent... ({successful} new, {duplicates} duplicates, {errors} errors)")

    print(f"\nLoad complete!")
    print(f"  Successful : {successful}")
    print(f"  Duplicates : {duplicates}")
    print(f"  Errors     : {errors}")
    print(f"  Total      : {successful + duplicates + errors}")


if __name__ == "__main__":
    filepath = os.path.join(os.path.dirname(__file__), "..", "sample_events.json")

    if not os.path.exists(filepath):
        print(f"Error: file not found: {filepath}")
        sys.exit(1)

    base_url = os.getenv("API_URL", "http://localhost:8000")
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else None

    load_events_from_file(filepath, base_url, sample_size)
