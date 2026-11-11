/* Local preview only. No credentials, external API calls, or production file writes. */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const contentTypes = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };
const files = {
  '/': 'index.html', '/index.html': 'index.html', '/weather.css': 'weather.css', '/weather.js': 'weather.js',
  '/weather_report.json': 'tests/fixtures/report.json', '/weather_history.json': 'tests/fixtures/history.json',
  '/weather_image.png': 'tests/fixtures/scene-preview.png',
};
function createServer() {
  return http.createServer((req, res) => {
    const name = files[new URL(req.url, 'http://localhost').pathname];
    if (!name) { res.writeHead(404); res.end('Not found'); return; }
    fs.readFile(path.join(root, name), (error, body) => {
      if (error) { res.writeHead(500); res.end('Preview file unavailable'); return; }
      if (name === 'index.html') body = Buffer.from(body.toString().replace(/<script src="https:\/\/cdn\.usefathom\.com[^>]*><\/script>/, ''));
      // Keep sample time relative to now so the preview shows all eight forecast slots.
      if (name === 'tests/fixtures/report.json') {
        const data = JSON.parse(body);
        const now = Date.now();
        data.generated_at = new Date(now - 10 * 60000).toISOString();
        data.observed_at = data.forecast_data.current_conditions.timestamp = new Date(now - 12 * 60000).toISOString();
        data.timestamp = data.generated_at;
        data.forecast_data.forecast.forEach((period, index) => { period.startTime = new Date(now + (index * 3 + 1) * 3600000).toISOString(); });
        body = Buffer.from(JSON.stringify(data));
      }
      res.writeHead(200, { 'Content-Type': contentTypes[path.extname(name)] || 'text/plain', 'Cache-Control': 'no-store' });
      res.end(body);
    });
  });
}
module.exports = { createServer };
if (require.main === module) {
  const server = createServer();
  server.listen(Number(process.env.PORT || 4173), '127.0.0.1', () => {
    console.log(`Weather Vibes design preview: http://127.0.0.1:${server.address().port}`);
    console.log('Illustrative data only. No live API calls. Press Ctrl-C to stop.');
  });
}
