/* Playwright browser_run_code entry point. Run in an authenticated local test session.
   This smoke check navigates and resizes only; it does not save operational data.
   Mutation and error-recovery evidence is recorded in docs/VISOR_UI_REDESIGN.md. */
async (page) => {
  const url = new URL(page.url());
  if (!['127.0.0.1', 'localhost'].includes(url.hostname)) throw Error('Use a local test session.');
  if (!await page.locator('[data-page="control"]').count()) throw Error('Sign in to an isolated test account before running.');
  await page.reload();
  await page.locator('[data-page="control"]').waitFor();
  const failures = [], results = [];
  const onError = error => failures.push(error.message);
  page.on('pageerror', onError);
  const onConsole = message => { if (message.type() === 'error') failures.push(message.text()); };
  page.on('console', onConsole);
  try {
    for (const width of [1440, 1280, 768, 375]) {
      await page.setViewportSize({width, height: 900});
      for (const id of ['control', 'live', 'incidents', 'analysis', 'modules', 'overview', 'settings']) {
        if (width <= 900) await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
        await page.locator(`[data-page="${id}"]`).click();
        await page.locator('main h1').waitFor();
        await page.waitForTimeout(300);
        const dimensions = await page.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth}));
        if (dimensions.document > dimensions.viewport) failures.push(`${id} overflows at ${width}px`);
        results.push({page: id, width, heading: await page.locator('main h1').textContent(), overflow: dimensions.document > dimensions.viewport});
      }
    }
    await page.setViewportSize({width: 1440, height: 900});
    await page.locator('[data-page="control"]').click();
    await page.locator('main h1').waitFor();
    if (failures.length) throw Error(failures.join('\n'));
    return {checks: results.length, pageErrors: failures.length, results};
  } finally {
    page.removeListener('pageerror', onError);
    page.removeListener('console', onConsole);
  }
}
