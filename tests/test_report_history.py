import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from history import WeatherHistory
from report import atomic_write_json


def test_atomic_failure_preserves_previous(tmp_path):
    path = tmp_path / 'report.json'
    path.write_text('{"previous":true}')
    with patch('report.os.replace', side_effect=OSError('disk failed')):
        with pytest.raises(OSError):
            atomic_write_json(path, {'new': True})
    assert json.loads(path.read_text()) == {'previous': True}
    assert list(tmp_path.iterdir()) == [path]


def test_nonfinite_json_preserves_previous(tmp_path):
    path = tmp_path / 'report.json'
    path.write_text('previous')
    with pytest.raises(ValueError):
        atomic_write_json(path, {'temp': float('nan')})
    assert path.read_text() == 'previous'


def test_legacy_and_aware_history(tmp_path):
    now = datetime.now(timezone.utc)
    legacy = (now + timedelta(hours=8)).replace(tzinfo=None).isoformat()
    rows = [
        {'timestamp': legacy, 'location': {'timezone': 'Australia/Perth'}, 'current_conditions': {'temperature_c': 22}},
        {'timestamp': now.isoformat().replace('+00:00', 'Z'), 'current_conditions': {'temperature_c': 24}},
        {'timestamp': (now - timedelta(days=9)).isoformat()},
        {'timestamp': 'invalid'},
    ]
    history = WeatherHistory(tmp_path / 'history.json')
    atomic_write_json(history.history_file, rows)
    assert len(history.get_recent_entries(1)) == 2
    assert history.get_temperature_trend(1)['data_points'] == 2
    history.cleanup_old_entries(7)
    assert len(json.loads(history.history_file.read_text())) == 2


def test_corrupt_history_not_overwritten(tmp_path):
    history = WeatherHistory(tmp_path / 'history.json')
    history.history_file.write_text('broken json')
    history.add_entry({'timestamp': datetime.now(timezone.utc).isoformat()})
    assert history.history_file.read_text() == 'broken json'


@pytest.mark.parametrize('payload', [
    '{"headline":"First","headline":"Duplicate"}',
    '{"headline":NaN}',
    '[]',
])
def test_strict_json_rejects_ambiguous_values(payload):
    from report import validate_report
    with pytest.raises(ValueError):
        validate_report(payload)


def test_history_summary_and_freshness(tmp_path):
    history = WeatherHistory(tmp_path / 'history.json')
    now = datetime.now(timezone.utc).isoformat()
    history.add_entry({'generated_at': now, 'observed_at': now, 'timestamp': now,
                       'report': {'headline': 'Quiet skies', 'summary': 'A mild morning.'},
                       'weather_report': 'A longer narrative'})
    entry = history.get_recent_entries()[0]
    assert entry['report_summary'] == 'A mild morning.'
    assert entry['headline'] == 'Quiet skies'
    assert entry['observed_at'] == now


def test_public_json_is_readable_by_static_server(tmp_path):
    import stat
    path = tmp_path / 'weather_report.json'
    atomic_write_json(path, {'report': 'public'})
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
