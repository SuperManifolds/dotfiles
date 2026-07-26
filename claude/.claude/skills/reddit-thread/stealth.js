// Stealth patches injected before any page JS runs, to defeat Reddit's
// Fastly "js_challenge" bot detection. The decisive tell is
// navigator.webdriver === true on CDP-driven Chrome; the rest remove
// secondary automation signals.

Object.defineProperty(navigator, "webdriver", { get: () => undefined });

if (!window.chrome) {
	window.chrome = { runtime: {} };
}

Object.defineProperty(navigator, "plugins", { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, "languages", { get: () => ["en-US", "en"] });

const originalQuery =
	window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
	window.navigator.permissions.query = (parameters) =>
		parameters && parameters.name === "notifications"
			? Promise.resolve({ state: Notification.permission })
			: originalQuery(parameters);
}
