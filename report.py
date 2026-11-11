"""Grounded report contract and fail-safe JSON publication."""
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict

REPORT_FIELDS = ('headline', 'summary', 'outlook', 'clothing', 'activity', 'color_code')
REPORT_SCHEMA: Dict[str, Any] = {
    'type': 'object', 'additionalProperties': False,
    'properties': {key: {'type': 'string'} for key in REPORT_FIELDS},
    'required': list(REPORT_FIELDS),
}
REPORT_SCHEMA['properties']['color_code']['pattern'] = '^#[0-9a-fA-F]{6}$'


def validate_report(text, max_words=300):
    """Reject incomplete, oversized or non-JSON output rather than publishing it."""
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate report key')
            obj[key] = value
        return obj

    def invalid_constant(value):
        raise ValueError(f'Invalid JSON constant: {value}')

    report = json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if not isinstance(report, dict) or set(report) != set(REPORT_FIELDS):
        raise ValueError('Report must contain exactly the required fields')
    for key, value in report.items():
        if not isinstance(value, str) or not value.strip() or len(value) > 6000:
            raise ValueError(f'Invalid report field: {key}')
        report[key] = value.strip()
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', report['color_code']):
        raise ValueError('Invalid report color')
    narrative = ' '.join(report[key] for key in REPORT_FIELDS if key != 'color_code')
    if len(narrative.split()) > max_words:
        raise ValueError('Report exceeds word budget')
    # This provider does not supply these measurements. Fail closed if mentioned.
    if re.search(r'\b(uv|ultraviolet|air quality|aqi|pollution|pollen|visibility)\b', narrative, re.I):
        raise ValueError('Report mentions an unsupported measurement')
    return report


def atomic_write_json(path, data):
    """Serialize before touching disk; replace only a complete, flushed temp file."""
    path = Path(path)
    payload = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=f'.{path.name}.', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            # Generated artifacts are public static-site files, also read by nginx.
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
