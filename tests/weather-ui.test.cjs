const test = require('node:test');
const assert = require('node:assert/strict');
const ui = require('../weather.js');
const fixture = require('./fixtures/report.json');
const now = new Date('2026-11-11T08:30:00Z');

test('only timezone-aware timestamps become instants', () => {
    assert.equal(ui.parseInstant('2026-11-11 16:20:00'), null);
    assert.equal(ui.parseInstant('not a date'), null);
    assert.equal(ui.parseInstant('2026-11-11T16:20:00+08:00').toISOString(), '2026-11-11T08:20:00.000Z');
});
test('times use the report timezone, not the reader timezone', () => {
    assert.match(ui.localTime('2026-11-11T09:00:00Z', 'Australia/Perth', {hour:'numeric'}), /5 pm/);
    assert.match(ui.localTime('2026-11-11T09:00:00Z', 'America/Chicago', {hour:'numeric'}), /3 am/);
    assert.match(ui.generatedLabel({timestamp:'2026-11-11 16:20:00', location:{timezone:'Australia/Perth'}}), /4:20 pm.*Perth time/);
});
test('missing or invalid timezone has a safe UTC fallback', () => {
    assert.doesNotThrow(() => ui.localTime('2026-11-11T09:00:00Z', 'Not/AZone', {hour:'numeric'}));
    assert.match(ui.localTime('2026-11-11T09:00:00Z', undefined, {hour:'numeric'}), /9 am/);
});
test('freshness follows the observation, even if a stale report is regenerated', () => {
    assert.equal(ui.freshness(fixture, now).stale, false);
    assert.match(ui.freshness(fixture, now).label, /12m ago/);
    const stale = {...fixture, observed_at:'2026-11-10T08:00:00Z', generated_at:now.toISOString()};
    assert.equal(ui.freshness(stale, now).stale, true);
    assert.match(ui.freshness(stale, now).message, /getting old/);
});
test('unreliable and future timestamps never imply fresh data', () => {
    assert.equal(ui.freshness({timestamp:'2026-11-11 16:20:00'}, now).stale, true);
    assert.equal(ui.freshness({observed_at:'2026-11-12T00:00:00Z'}, now).stale, true);
});
test('forecast is chronological, upcoming, unique and limited to next 24 hours', () => {
    const periods = fixture.forecast_data.forecast;
    const data = {forecast_data:{forecast:[periods[2], periods[0], periods[0], null, {startTime:'bad'}, {startTime:'2026-11-10T00:00:00Z'}, {startTime:'2026-11-14T00:00:00Z'}]}};
    assert.deepEqual(ui.upcomingForecast(data, now), [periods[0], periods[2]]);
    assert.equal(ui.upcomingForecast(fixture, now).length, 8);
    assert.deepEqual(ui.upcomingForecast(fixture, new Date('2027-01-01T00:00:00Z')), []);
});
test('history isolates location, skips current report and deduplicates', () => {
    const history = require('./fixtures/history.json');
    const result = ui.recentHistory([...history, fixture, history[0], {generated_at:'2026-11-11T08:00:00Z',location:{name:'Katy'}}], fixture);
    assert.equal(result.length, 3);
    assert.ok(result.every(entry => entry.location.name === 'Subiaco'));
    assert.deepEqual(ui.recentHistory({}, fixture), []);
});
test('legacy reports are accepted, empty and malformed reports are not', () => {
    assert.ok(ui.validReport(fixture));
    assert.ok(ui.validReport({weather_report:'A pleasant morning.',forecast_data:{}}));
    assert.ok(!ui.validReport({weather_report:'',forecast_data:{}}));
    assert.ok(!ui.validReport(null));
    assert.ok(!ui.validReport([]));
});
