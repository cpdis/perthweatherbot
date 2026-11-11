"""Grounded report contract and fail-safe JSON publication."""
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)
DEFAULT_REPORT_COLOR = '#426350'

REPORT_FIELDS = ('headline', 'summary', 'outlook', 'clothing', 'activity', 'color_code')
REPORT_SCHEMA: Dict[str, Any] = {
    'type': 'object', 'additionalProperties': False,
    'properties': {key: {'type': 'string'} for key in REPORT_FIELDS},
    'required': list(REPORT_FIELDS),
}
REPORT_SCHEMA['properties']['color_code'].update(
    pattern='^#[0-9a-fA-F]{6}$',
    description='Decorative accent only. Exactly #RRGGBB, for example #87CEEB.',
)


def normalize_report_color(value):
    """Keep decorative model output from blocking an otherwise valid forecast."""
    if isinstance(value, str) and len(value) <= 64:
        color = value.strip()
        if re.fullmatch(r'#?[0-9a-fA-F]{6}', color):
            return '#' + color.lstrip('#').upper()
        if re.fullmatch(r'#[0-9a-fA-F]{3}', color):
            return '#' + ''.join(character * 2 for character in color[1:]).upper()
    # Never pass arbitrary CSS through or log untrusted model output.
    logger.warning('Invalid decorative report color; using default accent')
    return DEFAULT_REPORT_COLOR


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
        if key == 'color_code':
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > 6000:
            raise ValueError(f'Invalid report field: {key}')
        report[key] = value.strip()
    narrative = ' '.join(report[key] for key in REPORT_FIELDS if key != 'color_code')
    if len(narrative.split()) > max_words:
        raise ValueError('Report exceeds word budget')
    # This provider does not supply these measurements. Fail closed if mentioned.
    if re.search(r'\b(uv|ultraviolet|air quality|aqi|pollution|pollen|visibility)\b', narrative, re.I):
        raise ValueError('Report mentions an unsupported measurement')
    report['color_code'] = normalize_report_color(report['color_code'])
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
