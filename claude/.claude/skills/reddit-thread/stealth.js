// Stealth patches injected before any page JS runs, to defeat Reddit's
// Fastly "js_challenge" bot detection.
//
// The decisive tells, in order of importance:
//
//  1. Brand identity. Chromium (the distro build) advertises itself as
//     "Chromium" in both the Sec-CH-UA request header and
//     navigator.userAgentData.brands. Overriding only navigator.userAgent
//     leaves those saying Chromium while the UA string claims Chrome — a
//     contradiction that is free to detect. Both must claim Google Chrome.
//  2. Self-consistency. The UA string, navigator.platform, and the
//     Sec-CH-UA-Arch/Bitness hints must describe one machine. A UA claiming
//     aarch64 next to a platform of x86_64 is a giveaway, so present the
//     common case: Chrome on Linux x86_64.
//  3. navigator.webdriver === true on CDP-driven Chrome.
//
// browser.sh sets the matching request headers; this file keeps the
// JS-visible surface in agreement. Keep UA_* here in sync with browser.sh.

const UA_VERSION = "148";
const UA =
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) " +
	`Chrome/${UA_VERSION}.0.0.0 Safari/537.36`;

Object.defineProperty(navigator, "userAgent", { get: () => UA });
Object.defineProperty(navigator, "appVersion", {
	get: () => UA.replace(/^Mozilla\//, ""),
});
Object.defineProperty(navigator, "platform", { get: () => "Linux x86_64" });

Object.defineProperty(navigator, "webdriver", { get: () => undefined });

// Client hints. Order mirrors what Chrome emits; the GREASE brand stays first.
const BRANDS = [
	{ brand: "Not/A)Brand", version: "99" },
	{ brand: "Google Chrome", version: UA_VERSION },
	{ brand: "Chromium", version: UA_VERSION },
];

if (navigator.userAgentData) {
	Object.defineProperty(navigator.userAgentData, "brands", {
		get: () => BRANDS,
	});
	// getHighEntropyValues() is a separate code path from .brands and would
	// otherwise still report Chromium and the real architecture.
	const highEntropy = navigator.userAgentData.getHighEntropyValues.bind(
		navigator.userAgentData,
	);
	navigator.userAgentData.getHighEntropyValues = async (hints) => ({
		...(await highEntropy(hints)),
		brands: BRANDS,
		fullVersionList: BRANDS,
		architecture: "x86",
		bitness: "64",
		platform: "Linux",
	});
}

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
