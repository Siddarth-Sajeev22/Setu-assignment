"""Script to load sample events into the database."""
import json
import os
import sys
from datetime import datetime
from typing import Optional

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.schemas.requests import EventPayloadRequest
from app.services.event_processor import EventProcessor
from app.schemas.exceptions import APIException


def load_events_from_file(filepath: str, sample_size: Optional[int] = None):
    """
    Load events from JSON file into the database.
    
    Args:
        filepath: Path to sample_events.json file
        sample_size: Limit number of events to load (None = all)
    """
    print(f"Loading events from {filepath}...")

    # Read JSON file
    with open(filepath, "r") as f:
        events = json.load(f)

    if sample_size:
        events = events[:sample_size]

    print(f"Found {len(events)} events to load")

    # Load events into database
    db = SessionLocal()
    processor = EventProcessor(db)
    
    successful = 0
    duplicates = 0
    errors = 0

    for i, event_data in enumerate(events):
        try:
            # Parse event data
            request = EventPayloadRequest(
                event_id=event_data["event_id"],
                transaction_id=event_data["transaction_id"],
                merchant_id=event_data["merchant_id"],
                merchant_name=event_data["merchant_name"],
                event_type=event_data["event_type"],
                amount=event_data["amount"],
                currency=event_data["currency"],
                timestamp=event_data["timestamp"]
            )

            # Process event
            event, status_code = processor.process_event(request)

            if status_code == 201:
                successful += 1
            elif status_code == 200:
                duplicates += 1

            if (i + 1) % 1000 == 0:
                print(f"Loaded {i + 1} events... ({successful} new, {duplicates} duplicates)")

        except APIException as e:
            errors += 1
            print(f"Error processing event {i}: {str(e.message)}")
        except Exception as e:
            errors += 1
            print(f"Error processing event {i}: {str(e)}")

    db.close()

    print(f"\n✓ Load complete!")
    print(f"  Successful: {successful}")
    print(f"  Duplicates: {duplicates}")
    print(f"  Errors: {errors}")
    print(f"  Total: {successful + duplicates + errors}")


if __name__ == "__main__":

    filepath = os.path.join(os.path.dirname(__file__), "..", "sample_events.json")

    # Check if file exists
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    # Load with optional sample size
    sample_size = None
    if len(sys.argv) > 1:
        sample_size = int(sys.argv[1])

    load_events_from_file(filepath, sample_size)
