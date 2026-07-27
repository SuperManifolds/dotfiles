// Stealth patches injected before any page JS runs, to defeat Reddit's
// Fastly "js_challenge" bot detection. Two decisive tells: the
// "HeadlessChrome" token in the User-Agent (blocked at the Fastly edge —
// the driver overrides the HTTP header; this keeps navigator.userAgent in
// sync so a client-side check sees the same value) and
// navigator.webdriver === true on CDP-driven Chrome. The rest remove
// secondary automation signals.

const REAL_UA = navigator.userAgent.replace("HeadlessChrome", "Chrome");
if (REAL_UA !== navigator.userAgent) {
	Object.defineProperty(navigator, "userAgent", { get: () => REAL_UA });
	Object.defineProperty(navigator, "appVersion", {
		get: () => REAL_UA.replace(/^Mozilla\//, ""),
	});
}

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
