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
	let res = null;
	for (let i = 0; i < 6; i++) {
		res = await fetch(path);
		if (res.status === 200) break;
		await sleep(1200);
	}
	if (!res || res.status !== 200) {
		return { status: res ? res.status : 0, query, results: [] };
	}
	const j = await res.json();
	const results = (j.data.children || [])
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
	return { status: res.status, query, results };
})();
