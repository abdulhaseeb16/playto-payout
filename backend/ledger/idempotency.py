import hashlib
import json


def get_request_hash(body):
    canonical = json.dumps(body, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()
