/* Offline browser checks, using a fresh isolated profile and sample data only. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { createServer } = require('../scripts/preview.cjs');
const fixture = require('./fixtures/report.json');
const output = process.env.SCREENSHOT_DIR;

(async () => {
    const server = createServer();
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let browser;
    try {
        // CI uses the runner's packaged Chrome, whose AppArmor profile permits its sandbox.
        // Local checks keep using Playwright Chromium unless a channel is selected.
        browser = await chromium.launch({ headless: true, chromiumSandbox: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
        const url = `http://127.0.0.1:${server.address().port}`;
        const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, timezoneId: 'America/Chicago' });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('https://**/*', route => route.abort());
        await page.goto(url);
        await page.locator('#weather-image.is-loaded').waitFor();
        await page.locator('.forecast-period').last().waitFor();
        assert.equal(await page.locator('.forecast-period').count(), 8);
        assert.match(await page.locator('#notice').textContent(), /sample data, not a live forecast/);
        assert.equal(await page.locator('#location-title').textContent(), 'Subiaco');
        assert.equal(await page.locator('#weather-report h2').textContent(), fixture.report.headline);
        assert.match(await page.locator('#forecast-note').textContent(), /Perth time/);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        await page.locator('#motion-toggle').click();
        assert.equal(await page.locator('html').getAttribute('data-motion'), 'paused');
        if (output) { fs.mkdirSync(output, {recursive:true}); await page.screenshot({ path:path.join(output,'desktop.png'), fullPage:true }); }
        await page.locator('#theme-toggle').click();
        assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
        if (output) await page.screenshot({path:path.join(output,'dark.png'),fullPage:true});
        await page.locator('#scene-toggle').click();
        assert.equal(await page.locator('#forecast-content').isVisible(), false);
        assert.equal(await page.locator('#return-button').isVisible(), true);
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('#forecast-content').isVisible(), true);
        assert.equal(await page.locator('#scene-toggle').evaluate(el => el === document.activeElement), true);
        await page.locator('summary').click();
        assert.equal(await page.locator('#history-list li').count(), 3);
        await page.locator('summary').click();
        await page.keyboard.press('t');
        assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
        await page.reload();
        assert.equal(await page.locator('html').getAttribute('data-motion'), 'paused');

        // A failed refresh keeps the last successful report and offers a retry.
        await page.locator('#weather-report h2').waitFor();
        await page.route('**/weather_report.json?*', route => route.fulfill({status:503,body:'unavailable'}));
        await page.locator('#refresh-button').click();
        await page.locator('#retry-button').waitFor();
        assert.match(await page.locator('#notice').textContent(), /Showing the last report/);
        assert.equal(await page.locator('#weather-report h2').textContent(), fixture.report.headline);
        await page.unroute('**/weather_report.json?*');
        await page.locator('#retry-button').click();
        await page.waitForFunction(() => document.getElementById('retry-button').hidden && !document.getElementById('refresh-button').disabled);

        // Model/location strings are text, never HTML. Missing data is not zero rain.
        const malicious = structuredClone(fixture);
        malicious.location.name = '<img src=x onerror=alert(1)>';
        malicious.report.summary = '<script>window.UNSAFE=true</script>';
        malicious.observed_at = '2020-01-01T00:00:00Z';
        malicious.forecast_data.forecast = [{startTime:new Date(Date.now()+3600000).toISOString(),temperature:22,shortForecast:'cloudy'}];
        malicious.image = {status:'unavailable'};
        await page.route('**/weather_report.json?*', route => route.fulfill({json:malicious}));
        await page.locator('#refresh-button').click();
        await page.waitForFunction(() => document.getElementById('location-title').textContent.startsWith('<img'));
        assert.equal(await page.locator('#location-title img').count(),0);
        assert.equal(await page.locator('#weather-report script').count(),0);
        assert.match(await page.locator('.forecast-rain').textContent(), /—/);
        assert.match(await page.locator('#notice').textContent(), /getting old/);
        assert.equal(await page.locator('#scene-toggle').isVisible(),false);
        await page.unroute('**/weather_report.json?*');

        // Long copy and narrow devices must still wrap without horizontal scrolling.
        const mobile = await browser.newContext({viewport:{width:390,height:844},isMobile:true,deviceScaleFactor:1,reducedMotion:'reduce'});
        const phone = await mobile.newPage();
        await phone.goto(url);
        await phone.locator('#weather-image.is-loaded').waitFor();
        assert.equal(await phone.locator('#motion-toggle').isDisabled(),true);
        assert.equal(await phone.locator('#weather-image').evaluate(el => getComputedStyle(el).animationName),'none');
        assert.equal(await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
        if(output) await phone.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
        await phone.setViewportSize({width:320,height:740});
        await phone.evaluate(() => {document.getElementById('location-title').textContent='A very long location name that must wrap';});
        assert.equal(await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);

        // First-load failure can recover; broken optional history/image never hide weather.
        const empty = await browser.newContext();
        const recover = await empty.newPage();
        await recover.route('**/weather_report.json?*', route => route.fulfill({status:500,body:'fail'}));
        await recover.goto(url);
        await recover.locator('#retry-button').waitFor();
        assert.match(await recover.locator('#weather-report').textContent(), /could not load/);
        await recover.unroute('**/weather_report.json?*');
        await recover.route('**/weather_image.png?*',route => route.fulfill({status:404,body:'missing'}));
        await recover.route('**/weather_history.json?*',route => route.fulfill({status:404,body:'missing'}));
        await recover.locator('#retry-button').click();
        await recover.waitForFunction(() => document.getElementById('scene-caption').textContent.includes('could not load'));
        assert.equal(await recover.locator('#weather-report h2').textContent(), fixture.report.headline);
        assert.match(await recover.locator('#history-list').textContent(), /could not load/);

        // Legacy naive generation time stays in the location's timezone.
        const legacy = structuredClone(fixture);
        delete legacy.report;
        delete legacy.generated_at;
        delete legacy.image;
        legacy.timestamp = '2026-11-11 16:20:00';
        legacy.weather_report = 'A calm afternoon.\n\nA light layer for later.';
        await page.route('**/weather_report.json?*', route => route.fulfill({json:legacy}));
        await page.locator('#refresh-button').click();
        await page.waitForFunction(() => document.getElementById('weather-report').textContent.includes('A calm afternoon.'));
        assert.equal(await page.locator('#weather-report p').count(),2);
        assert.match(await page.locator('#timestamp').textContent(), /4:20 pm.*Perth time/);
        await page.unroute('**/weather_report.json?*');

        // A newer keyboard refresh wins over an interrupted slow response.
        let calls = 0;
        await page.route('**/weather_report.json?*', async route => {
            calls++;
            if(calls === 1) {await new Promise(resolve => setTimeout(resolve,150)); await route.fulfill({json:legacy}).catch(()=>{});}
            else await route.fulfill({json:fixture});
        });
        await page.keyboard.press('r');
        await page.waitForTimeout(25);
        await page.keyboard.press('r');
        await page.waitForFunction(() => document.querySelector('#weather-report h2'));
        await page.waitForTimeout(180);
        assert.equal(await page.locator('#weather-report h2').textContent(),fixture.report.headline);
        await page.unroute('**/weather_report.json?*');

        // Blocking storage does not prevent the initial page from working.
        const privateContext = await browser.newContext();
        await privateContext.addInitScript(() => Object.defineProperty(window,'localStorage',{get(){throw new Error('disabled');}}));
        const privatePage = await privateContext.newPage();
        await privatePage.goto(url);
        await privatePage.locator('#weather-report h2').waitFor();
        assert.equal(await privatePage.locator('#location-title').textContent(),'Subiaco');
        assert.deepEqual(errors,[]);
        console.log('PASS: desktop/mobile, dark theme, reduced motion, persistence, scene-only/escape, history, refresh/retry, stale/missing data, XSS, long copy, unavailable image/history, disabled storage.');
    } finally {
        await browser?.close();
        await new Promise(resolve => server.close(resolve));
    }
})().catch(error => {console.error(error);process.exitCode=1;});
