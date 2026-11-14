"""Local semantic retrieval of the supplied edition, never generated scripture."""
import hashlib
import json
import os
from pathlib import Path
import threading
import numpy as np
import onnxruntime
onnxruntime.disable_telemetry_events()
from fastembed import TextEmbedding

ROOT = Path(__file__).resolve().parent
MODEL = 'BAAI/bge-small-en-v1.5'
CACHE = ROOT / 'search-cache'
_lock = threading.Lock()
_model = None
_vectors = None
_data = None

def initialize(download=False):
    global _model, _vectors, _data
    if _model is not None and _vectors is not None:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    raw = (ROOT / 'quran_text.json').read_bytes()
    data = json.loads(raw)
    fingerprint = hashlib.sha256(raw + MODEL.encode()).hexdigest()
    try:
        model = TextEmbedding(MODEL, cache_dir=str(CACHE / 'model'), threads=2, local_files_only=True)
    except Exception:
        if not download:
            raise
        model = TextEmbedding(MODEL, cache_dir=str(CACHE / 'model'), threads=2)
    path = CACHE / (fingerprint + '.npy')
    if path.exists():
        vectors = np.load(path, allow_pickle=False)
    else:
        texts = [v['heading'] + ' ' + v['text'] + ' ' + ' '.join(n['text'] for n in v['notes'])[:1600] for v in data.values()]
        # Group similar lengths to avoid padding every batch to its longest note.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        batches = []
        for start in range(0, len(texts), 256):
            batches.extend(model.passage_embed([texts[i] for i in order[start:start + 256]], batch_size=32))
            print(f'Semantic index: {min(start + 256, len(texts))}/{len(texts)} verses', flush=True)
        vectors = np.asarray(batches, dtype=np.float32)[np.argsort(order)]
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        temp = path.with_suffix('.tmp')
        with temp.open('wb') as f:
            np.save(f, vectors, allow_pickle=False)
        os.replace(temp, path)
    if vectors.shape[0] != len(data):
        raise RuntimeError('Search index does not match the Quran edition.')
    _data, _vectors, _model = data, vectors, model

def search_verses(query, limit=5):
    query = query.strip()
    if not 2 <= len(query) <= 300:
        raise ValueError('Enter between 2 and 300 characters: words, a phrase, or an idea.')
    with _lock:
        initialize()
        q = np.asarray(next(iter(_model.query_embed(query))), dtype=np.float32)
        q /= max(float(np.linalg.norm(q)), 1e-12)
        scores = _vectors @ q
        # Exact wording gets a small bonus; meaning remains the main signal.
        for i,v in enumerate(_data.values()):
            if query.casefold() in (v['heading'] + ' ' + v['text']).casefold():
                scores[i] += .10
        keys = list(_data)
        return [(keys[i], _data[keys[i]]) for i in np.argsort(-scores, kind='stable')[:limit]]

if __name__ == '__main__':
    with _lock:
        initialize(download=True)
    print('Semantic index ready:', len(_data), 'verses')
