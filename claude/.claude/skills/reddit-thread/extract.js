// In-session Reddit thread extractor. Run inside the challenge-passed browser
// via `agent-browser eval --stdin < extract.js`; returns a structured object
// (see reddit-read.sh). Fetches the thread .json same-origin, then recursively
// resolves kind:"more" stubs via /api/morechildren.json (both work with the
// session's challenge cookies).
//
// The driver seeds `globalThis.__REDDIT_LIMIT` (top-level fetch size) before
// this runs; it falls back to 500.
(async () => {
	const linkId = location.pathname.split("/")[4]; // base36 thread id
	const limit = globalThis.__REDDIT_LIMIT || 500;
	const raw = "&raw_json=1";
	// Fetch by canonical id (/comments/<id>.json) rather than the current path,
	// so a wrong/missing slug or an in-flight redirect can't 404 us. Retry a few
	// times in case the fresh-session challenge cookies are still settling.
	const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
	let base = null;
	for (let i = 0; i < 6; i++) {
		const res = await fetch(
			"/comments/" + linkId + ".json?limit=" + limit + raw,
		);
		if (res.status === 200) {
			base = await res.json();
			break;
		}
		await sleep(1200);
	}
	if (!base) throw new Error("thread fetch failed (id " + linkId + ")");
	const post = base[0].data.children[0].data;

	const byId = {};
	const roots = [];
	let moreQueue = [];

	function add(d, parentId) {
		if (byId[d.id]) return;
		byId[d.id] = {
			id: d.id,
			author: d.author,
			score: d.score,
			body: d.body || "",
			kids: [],
		};
		if (parentId && byId[parentId]) byId[parentId].kids.push(d.id);
		else if (!parentId) roots.push(d.id);
	}
	function ingest(children, parentId) {
		for (const c of children) {
			if (c.kind === "t1") {
				add(c.data, parentId);
				if (c.data.replies && c.data.replies.data)
					ingest(c.data.replies.data.children, c.data.id);
			} else if (c.kind === "more") {
				moreQueue.push(...(c.data.children || []));
			}
		}
	}
	ingest(base[1].data.children, null);

	let rounds = 0;
	while (moreQueue.length && rounds < 15) {
		rounds++;
		const batch = moreQueue.splice(0, 100);
		const u =
			"/api/morechildren.json?api_type=json&link_id=t3_" +
			linkId +
			"&children=" +
			batch.join(",") +
			raw;
		let things = [];
		try {
			const m = await (
				await fetch(u, { headers: { Accept: "application/json" } })
			).json();
			things = m.json.data.things || [];
		} catch (e) {
			break;
		}
		for (const t of things) {
			if (t.kind === "t1") {
				const d = t.data;
				const parentId = (d.parent_id || "").replace(/^t\d_/, "");
				add(d, byId[parentId] ? parentId : null);
			} else if (t.kind === "more") {
				moreQueue.push(...(t.data.children || []));
			}
		}
	}

	return {
		url: "https://www.reddit.com" + post.permalink,
		title: post.title,
		author: post.author,
		score: post.score,
		num_comments: post.num_comments,
		selftext: post.selftext || "",
		extracted: Object.keys(byId).length,
		unresolved_more_ids: moreQueue.length,
		roots,
		byId,
	};
})();
