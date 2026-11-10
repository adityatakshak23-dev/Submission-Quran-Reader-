"""Persistent host-confirmed study progress, independent of verification data."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from source import parse_reference, reference_label

PATH = Path(os.getenv('READER_DATA_DIR', '/data')) / 'study.json'

def load():
    if not PATH.exists():
        return {'history': []}
    return json.loads(PATH.read_text(encoding='utf-8'))

def record(verse, host_id):
    first, last = parse_reference(verse)
    state = load()
    entry = {'passage': reference_label(first, last), 'last_verse': last,
             'host_id': host_id, 'recorded_at': datetime.now(timezone.utc).isoformat()}
    state['history'].append(entry)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, PATH)
    return entry
