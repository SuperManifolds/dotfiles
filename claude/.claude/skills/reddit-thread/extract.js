// In-session Reddit thread extractor. Run inside the challenge-passed browser
// via `agent-browser eval --stdin < extract.js`; returns a structured object
// (see reddit-read.sh). Fetches the thread .json same-origin, then recursively
// resolves kind:"more" stubs via /api/morechildren.json (both work with the
// session's challenge cookies).
//
// The driver seeds `globalThis.__REDDIT_LIMIT` (top-level fetch size) before
// this runs; it falls back to 500.
(async () => {
	const permalink = location.pathname.replace(/\/$/, "");
	const linkId = permalink.split("/")[4];
	const limit = globalThis.__REDDIT_LIMIT || 500;
	const raw = "&raw_json=1";
	const base = await (
		await fetch(permalink + ".json?limit=" + limit + raw)
	).json();
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
		url: location.origin + permalink,
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
