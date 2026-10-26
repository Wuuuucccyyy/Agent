"""Resumable source-to-profile coordination and atomic snapshot publication."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .cran import collect_locked
from .kb_agents import fingerprint, profile_document
from .kb_store import checksum


def build_database(database, lock_path, cache, client, *, refresh=False, progress=None):
    started = time.perf_counter()
    documents = collect_locked(lock_path, cache)
    lock_hash = checksum(json.loads(Path(lock_path).read_text(encoding='utf-8')))
    before = dict(client.usage)
    records, events = [], []
    for document in documents:
        tick = time.perf_counter()
        event = {'function_id': document['function_id']}
        try:
            record = None if refresh else database.cached(fingerprint(document, client), include_needs_review=True)
            event['cached'] = record is not None
            if record is None:
                record = database.save_profile(profile_document(document, client))
            records.append(record)
            event.update(status=record['status'], revision=record['revision'],
                         attempts=0 if event['cached'] else len(record['attempts']))
        except (ValueError, OSError, KeyError) as exc:
            event.update(status='error', error=f'{type(exc).__name__}: {exc}')
        event['seconds'] = time.perf_counter()-tick
        events.append(event)
        if progress:
            progress(event)
    errors = sum(e['status'] == 'error' for e in events)
    # A partial failure never changes the currently active complete snapshot.
    snapshot = None if errors else database.publish(records, lock_hash)
    result = {'build_id': uuid4().hex, 'started_at': datetime.now(timezone.utc).isoformat(),
              'source_lock_sha256': lock_hash, 'source_lock_hash_format': 'canonical JSON SHA256',
              'status': 'error' if errors else 'needs_review' if any(r['status'] != 'machine_checked' for r in records) else 'success',
              'function_count': len(documents), 'machine_checked': sum(r['status'] == 'machine_checked' for r in records),
              'needs_review': sum(r['status'] == 'needs_review' for r in records), 'errors': errors,
              'snapshot': snapshot, 'events': events, 'elapsed_seconds': time.perf_counter()-started,
              'usage': {k: v-before.get(k, 0) for k, v in client.usage.items()}, 'api_cost_usd': None,
              'limitations': ['Same DeepSeek model in extraction and review roles; no independent human audit.',
                             'Exact evidence quotes validate location, not truth of all semantic interpretations.',
                             'Source code and examples were not executed. Candidate search does not authorize execution.']}
    database.save_build(result)
    return result
