// In-session Reddit search. Run inside a challenge-passed session via
// `agent-browser eval --stdin < search.js`. The driver seeds
// `globalThis.__REDDIT_SEARCH_URL` (the search.json path + query to fetch) and
// `globalThis.__REDDIT_QUERY` (the human query, for display). Returns
// { status, query, results:[{title, subreddit, author, score, num_comments, url}] }.
(async () => {
	const path = globalThis.__REDDIT_SEARCH_URL;
	const query = globalThis.__REDDIT_QUERY || "";
	// Retry a few times in case the fresh-session challenge cookies are still
	// settling (a non-200 on the first hit).
	const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

	const extract = (j) =>
		(j.data.children || [])
			.filter((c) => c.kind === "t3")
			.map((c) => {
				const d = c.data;
				return {
					title: d.title,
					subreddit: d.subreddit_name_prefixed,
					author: d.author,
					score: d.score,
					num_comments: d.num_comments,
					url: "https://www.reddit.com" + d.permalink,
				};
			});

	// Retry on a non-200 (challenge cookies still settling) and also on a 200
	// carrying an empty listing: on the first request of a brand-new session
	// Reddit sometimes answers 200 with no children, which is indistinguishable
	// from a genuinely empty search and reads as "no results" downstream. A
	// query that really has no matches just returns empty again, so the only
	// cost is a couple of extra fetches on that path.
	let res = null;
	let results = [];
	for (let i = 0; i < 6; i++) {
		res = await fetch(path);
		if (res.status === 200) {
			results = extract(await res.json());
			if (results.length > 0) break;
		}
		if (i < 5) await sleep(1200);
	}
	if (!res || res.status !== 200) {
		return { status: res ? res.status : 0, query, results: [] };
	}
	return { status: res.status, query, results };
})();
