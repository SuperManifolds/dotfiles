// YouTube playlist helper. Paste into a signed-in youtube.com tab with the
// Chrome extension's javascript_tool; it defines window.yt.
//
// Calls the same InnerTube endpoints the YouTube web app uses, authenticated
// with the page's own session cookies (SAPISIDHASH). Nothing leaves the
// browser except requests to youtube.com. Works for Watch Later ("WL"), which
// the official Data API no longer exposes.
window.yt = (() => {
  const ORIGIN = 'https://www.youtube.com';
  // Any permanent public video works: get_add_to_playlist needs one to report
  // membership, and its answer lists every playlist the account can edit.
  const PROBE_VIDEO_ID = 'jNQXAC9IVRw';
  const EDIT_BATCH_SIZE = 50;
  const PRIVACY = ['PRIVATE', 'UNLISTED', 'PUBLIC'];
  const SETTLE_TIMEOUT_MS = 30000;
  const SETTLE_POLL_MS = 2000;
  // Removing more entries than this takes a snapshot first.
  const BULK_REMOVE_THRESHOLD = 3;
  const SNAPSHOT_PREFIX = 'yt-playlists:snapshot:';
  const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;
  // Long-lived public videos for selftest().
  const SELFTEST_VIDEOS = ['jNQXAC9IVRw', 'dQw4w9WgXcQ', '9bZkp7q19f0', 'kJQP7kiw5Fk'];

  async function sha1(text) {
    const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(text));
    return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
  }

  async function call(endpoint, body) {
    const sapisid = (document.cookie.match(/(?:^|; )(?:__Secure-3PAPISID|SAPISID)=([^;]+)/) || [])[1];
    if (!sapisid) throw new Error('not signed in: no SAPISID cookie on this tab');
    const ts = Math.floor(Date.now() / 1000);
    const resp = await fetch(`/youtubei/v1/${endpoint}?prettyPrint=false`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `SAPISIDHASH ${ts}_${await sha1(`${ts} ${sapisid} ${ORIGIN}`)}`,
        'X-Origin': ORIGIN,
        'X-Goog-AuthUser': String(window.ytcfg.get('SESSION_INDEX') ?? 0),
      },
      body: JSON.stringify({ context: window.ytcfg.get('INNERTUBE_CONTEXT'), ...body }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(`${endpoint} HTTP ${resp.status}: ${JSON.stringify(data.error || data).slice(0, 300)}`);
    return data;
  }

  function walk(node, visit) {
    if (!node || typeof node !== 'object') return;
    visit(node);
    for (const child of Object.values(node)) walk(child, visit);
  }

  const text = t => t?.simpleText ?? t?.runs?.map(r => r.text).join('') ?? t?.content ?? null;
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  // Accepts a bare id or a youtube.com / youtu.be / music.youtube.com URL
  // (watch, shorts, live, embed).
  function videoIdOf(input) {
    const value = String(input).trim();
    if (VIDEO_ID.test(value)) return value;
    let url;
    try {
      url = new URL(value);
    } catch {
      throw new Error(`not a video id or URL: ${value}`);
    }
    const candidate = url.hostname.endsWith('youtu.be')
      ? url.pathname.slice(1)
      : url.searchParams.get('v') ?? url.pathname.match(/^\/(?:shorts|live|embed)\/([^/?#]+)/)?.[1];
    if (!candidate || !VIDEO_ID.test(candidate)) throw new Error(`no video id in URL: ${value}`);
    return candidate;
  }

  // Polls fn() until check(result) is true and returns the result. Reads lag
  // writes by a few seconds, and a new playlist answers "does not exist"
  // briefly, so errors are retried too. On timeout throws with the last error
  // or describe(last result).
  async function until(fn, check, describe, timeoutMs = SETTLE_TIMEOUT_MS) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      let last;
      try {
        const current = await fn();
        if (check(current)) return current;
        last = describe(current);
      } catch (error) {
        last = `error: ${error.message}`;
      }
      if (Date.now() > deadline) throw new Error(`state not reached within ${timeoutMs} ms; last: ${last}`);
      await sleep(SETTLE_POLL_MS);
    }
  }

  // Playlists the account can edit, with privacy. Includes Watch Later.
  async function mine() {
    const data = await call('playlist/get_add_to_playlist', { videoIds: [PROBE_VIDEO_ID], excludeWatchLater: false });
    const out = [];
    walk(data, n => {
      const r = n.playlistAddToOptionRenderer;
      if (r) out.push({ id: r.playlistId, title: text(r.title), privacy: r.privacy });
    });
    return out;
  }

  // Everything on the Library > Playlists page, including saved playlists
  // owned by others and Liked videos ("LL"). No privacy or ownership info.
  async function library() {
    const data = await call('browse', { browseId: 'FEplaylist_aggregation' });
    const out = [];
    walk(data, n => {
      const l = n.lockupViewModel;
      if (l) out.push({ id: l.contentId, title: l.metadata?.lockupMetadataViewModel?.title?.content, type: l.contentType?.replace('LOCKUP_CONTENT_TYPE_', '') });
    });
    return out;
  }

  // Resolve an editable playlist by exact title (case-insensitive). Throws on
  // zero or several matches, because titles are not unique.
  async function find(title) {
    const hits = (await mine()).filter(p => p.title.toLowerCase() === title.toLowerCase());
    if (hits.length !== 1) throw new Error(`${hits.length} editable playlists titled "${title}": ${JSON.stringify(hits)}`);
    return hits[0];
  }

  // A nonexistent playlist answers 200 with an ERROR alert, while an empty
  // one has neither list nor alert, so the alert is the only signal.
  function throwOnErrorAlert(data, playlistId) {
    walk(data, n => {
      if (n.alertRenderer?.type === 'ERROR') throw new Error(`playlist ${playlistId}: ${text(n.alertRenderer.text)}`);
    });
  }

  // The direct children of the playlist's own list: the first page's
  // playlistVideoListRenderer, or a continuation's appended items. Short
  // playlists also get a "recommended videos" shelf with the same video
  // renderer and its own continuation, so nothing outside this list is read.
  function listChildren(data) {
    let children = null;
    walk(data, n => {
      if (children) return;
      if (n.playlistVideoListRenderer) children = n.playlistVideoListRenderer.contents ?? [];
      else if (n.appendContinuationItemsAction) children = n.appendContinuationItemsAction.continuationItems ?? [];
    });
    return children ?? [];
  }

  function collectItems(data, items) {
    let token = null;
    for (const child of listChildren(data)) {
      const r = child.playlistVideoRenderer;
      if (child.continuationItemRenderer) walk(child.continuationItemRenderer, n => { token ??= n.continuationCommand?.token; });
      if (!r) continue;
      const resume = r.thumbnailOverlays?.find(o => o.thumbnailOverlayResumePlaybackRenderer)?.thumbnailOverlayResumePlaybackRenderer;
      items.push({
        index: items.length,
        videoId: r.videoId,
        setVideoId: r.setVideoId,
        title: text(r.title),
        channel: text(r.shortBylineText),
        duration: text(r.lengthText),
        watchedPct: resume?.percentDurationWatched ?? 0,
        // Private and deleted entries omit isPlayable entirely.
        playable: r.isPlayable === true,
      });
    }
    return token;
  }

  // The "Show unavailable videos" menu entry carries the browse params that
  // include private and deleted entries. Absent when nothing is hidden.
  function showUnavailableParams(data) {
    let params = null;
    walk(data, n => {
      const m = n.menuNavigationItemRenderer;
      if (!params && m && /unavailable/i.test(text(m.text) ?? '')) params = m.navigationEndpoint?.browseEndpoint?.params ?? null;
    });
    return params;
  }

  // Some entries have no byline (seen on multi-creator videos); oEmbed is
  // same-origin and unauthenticated.
  async function fillChannels(list) {
    for (const item of list.filter(i => i.channel === null && i.playable)) {
      const resp = await fetch(`/oembed?format=json&url=${encodeURIComponent(`${ORIGIN}/watch?v=${item.videoId}`)}`);
      if (resp.ok) item.channel = (await resp.json()).author_name ?? null;
    }
    return list;
  }

  // Every entry of a playlist, all pages, in playlist order. setVideoId is the
  // per-entry id that remove and the moves need. includeUnavailable adds the
  // private and deleted entries YouTube hides by default.
  async function items(playlistId, { includeUnavailable = false } = {}) {
    const browseId = `VL${playlistId}`;
    let first = await call('browse', { browseId });
    throwOnErrorAlert(first, playlistId);
    const params = includeUnavailable && showUnavailableParams(first);
    if (params) first = await call('browse', { browseId, params });
    const out = [];
    let token = collectItems(first, out);
    while (token) token = collectItems(await call('browse', { continuation: token }), out);
    return fillChannels(out);
  }

  const unavailable = async playlistId => (await items(playlistId, { includeUnavailable: true })).filter(i => !i.playable);

  const order = list => list.map(i => i.videoId).join(',');

  // Polls items() until check(items) is true and returns them.
  const waitFor = (playlistId, check, timeoutMs) =>
    until(() => items(playlistId, { includeUnavailable: true }), check, order, timeoutMs);

  async function edit(playlistId, actions) {
    for (let i = 0; i < actions.length; i += EDIT_BATCH_SIZE) {
      const data = await call('browse/edit_playlist', { playlistId, actions: actions.slice(i, i + EDIT_BATCH_SIZE) });
      if (data.status !== 'STATUS_SUCCEEDED') {
        throw new Error(`edit_playlist batch ${i / EDIT_BATCH_SIZE} returned ${data.status} after ${i} of ${actions.length} actions applied: ${JSON.stringify(data).slice(0, 300)}`);
      }
    }
    return { status: 'STATUS_SUCCEEDED', actions: actions.length };
  }

  // Saves every entry (unavailable included) to this origin's localStorage,
  // which survives tab and browser restarts. Returns the record so it can
  // also be written to disk.
  async function snapshot(playlistId) {
    const list = await items(playlistId, { includeUnavailable: true });
    const title = (await mine()).find(p => p.id === playlistId)?.title ?? null;
    const record = { playlistId, title, takenAt: new Date().toISOString(), videoIds: list.map(i => i.videoId) };
    const key = `${SNAPSHOT_PREFIX}${playlistId}:${record.takenAt}`;
    localStorage.setItem(key, JSON.stringify(record));
    return { key, ...record };
  }

  function snapshots(playlistId) {
    return Object.keys(localStorage)
      .filter(k => k.startsWith(SNAPSHOT_PREFIX + (playlistId ? `${playlistId}:` : '')))
      .sort()
      .map(key => {
        const { title, takenAt, videoIds } = JSON.parse(localStorage.getItem(key));
        return { key, title, takenAt, count: videoIds.length };
      });
  }

  const dropSnapshot = key => localStorage.removeItem(key);

  // Appends to the end of the playlist. Accepts ids or URLs.
  const add = (playlistId, videos) =>
    edit(playlistId, videos.map(v => ({ action: 'ACTION_ADD_VIDEO', addedVideoId: videoIdOf(v) })));

  // Removes entries by setVideoId. Bulk removals snapshot first; the key is
  // in the result.
  async function remove(playlistId, setVideoIds, { snapshotFirst = setVideoIds.length > BULK_REMOVE_THRESHOLD } = {}) {
    const saved = snapshotFirst ? (await snapshot(playlistId)).key : null;
    const result = await edit(playlistId, setVideoIds.map(setVideoId => ({ action: 'ACTION_REMOVE_VIDEO', setVideoId })));
    return { ...result, snapshot: saved };
  }

  // Move one entry directly after or before another entry. To move to the
  // top, move before the current first entry.
  const moveAfter = (playlistId, setVideoId, afterSetVideoId) =>
    edit(playlistId, [{ action: 'ACTION_MOVE_VIDEO_AFTER', setVideoId, movedSetVideoIdPredecessor: afterSetVideoId }]);
  const moveBefore = (playlistId, setVideoId, beforeSetVideoId) =>
    edit(playlistId, [{ action: 'ACTION_MOVE_VIDEO_BEFORE', setVideoId, movedSetVideoIdSuccessor: beforeSetVideoId }]);

  // Puts the given videos (ids or URLs, in the wanted order) at the top of
  // the playlist in that order; entries not listed keep their relative order
  // after them. A video listed twice claims two of its entries. Only moves
  // what is out of place, simulating each move locally.
  async function reorder(playlistId, videos) {
    const current = await items(playlistId, { includeUnavailable: true });
    const pools = new Map();
    for (const item of current) pools.set(item.videoId, [...(pools.get(item.videoId) ?? []), item.setVideoId]);
    const wanted = videos.map(videoIdOf).map(id => {
      const setVideoId = pools.get(id)?.shift();
      if (!setVideoId) throw new Error(`reorder: ${id} is not in playlist ${playlistId} (or listed more often than it appears)`);
      return setVideoId;
    });
    const seq = current.map(i => i.setVideoId);
    const actions = [];
    wanted.forEach((setVideoId, k) => {
      if (seq[k] === setVideoId) return;
      seq.splice(seq.indexOf(setVideoId), 1);
      seq.splice(k, 0, setVideoId);
      actions.push(k === 0
        ? { action: 'ACTION_MOVE_VIDEO_BEFORE', setVideoId, movedSetVideoIdSuccessor: seq[1] }
        : { action: 'ACTION_MOVE_VIDEO_AFTER', setVideoId, movedSetVideoIdPredecessor: seq[k - 1] });
    });
    if (!actions.length) return { status: 'ALREADY_IN_ORDER', actions: 0 };
    return edit(playlistId, actions);
  }

  // Removes every repeat of a video, keeping its first entry.
  async function dedupe(playlistId) {
    const seen = new Set();
    const repeats = (await items(playlistId, { includeUnavailable: true }))
      .filter(i => seen.has(i.videoId) || !seen.add(i.videoId))
      .map(i => i.setVideoId);
    if (!repeats.length) return { status: 'NO_DUPLICATES', actions: 0 };
    return remove(playlistId, repeats, { snapshotFirst: true });
  }

  // Re-adds what a snapshot has and the playlist lacks, then restores the
  // snapshot's order. Entries added since the snapshot are kept, at the end.
  // Private or deleted videos cannot be re-added and are reported.
  async function restore(key) {
    const raw = localStorage.getItem(key);
    if (!raw) throw new Error(`no snapshot ${key}; see snapshots()`);
    const { playlistId, videoIds } = JSON.parse(raw);
    const have = new Map();
    for (const i of await items(playlistId, { includeUnavailable: true })) have.set(i.videoId, (have.get(i.videoId) ?? 0) + 1);
    const missing = [];
    for (const id of videoIds) {
      if (have.get(id)) have.set(id, have.get(id) - 1);
      else missing.push(id);
    }
    const added = [];
    const failed = [];
    for (const id of missing) {
      try {
        await add(playlistId, [id]);
        added.push(id);
      } catch (error) {
        failed.push({ videoId: id, error: error.message.slice(0, 120) });
      }
    }
    const target = videoIds.filter(id => !failed.some(f => f.videoId === id));
    const covers = list => {
      const counts = new Map();
      for (const i of list) counts.set(i.videoId, (counts.get(i.videoId) ?? 0) + 1);
      return target.every(id => {
        const left = counts.get(id) ?? 0;
        counts.set(id, left - 1);
        return left > 0;
      });
    };
    await waitFor(playlistId, covers);
    const reordered = await reorder(playlistId, target);
    return { added: added.length, failed, reordered: reordered.actions };
  }

  const rename = (playlistId, playlistName) => edit(playlistId, [{ action: 'ACTION_SET_PLAYLIST_NAME', playlistName }]);
  const describe = (playlistId, playlistDescription) => edit(playlistId, [{ action: 'ACTION_SET_PLAYLIST_DESCRIPTION', playlistDescription }]);

  function checkPrivacy(privacy) {
    if (!PRIVACY.includes(privacy)) throw new Error(`privacy must be one of ${PRIVACY.join(', ')}, got ${privacy}`);
  }

  const setPrivacy = (playlistId, privacy) => {
    checkPrivacy(privacy);
    return edit(playlistId, [{ action: 'ACTION_SET_PLAYLIST_PRIVACY', playlistPrivacy: privacy }]);
  };

  async function create(title, privacy = 'PRIVATE', videos = []) {
    checkPrivacy(privacy);
    const data = await call('playlist/create', { title, privacyStatus: privacy, videoIds: videos.map(videoIdOf) });
    if (!data.playlistId) throw new Error(`playlist/create returned no playlistId: ${JSON.stringify(data).slice(0, 300)}`);
    // Returns only once the playlist can be read; until then it answers
    // "does not exist".
    await until(() => items(data.playlistId), () => true, () => 'not readable yet');
    return { id: data.playlistId, title, privacy };
  }

  async function deletePlaylist(playlistId) {
    if (playlistId === 'WL' || playlistId === 'LL') throw new Error(`${playlistId} is a system playlist and cannot be deleted`);
    await call('playlist/delete', { playlistId });
    return { deleted: playlistId };
  }

  // Adds every playable video of `from` that `to` does not already contain,
  // in order.
  async function copy(from, to) {
    const present = new Set((await items(to, { includeUnavailable: true })).map(i => i.videoId));
    const missing = (await items(from)).filter(i => i.playable && !present.has(i.videoId)).map(i => i.videoId);
    if (!missing.length) return { status: 'NOTHING_TO_ADD', actions: 0 };
    return add(to, [...new Set(missing)]);
  }

  // Entries watched to at least minPct percent (YouTube's own resume marker).
  async function watched(playlistId, minPct = 90) {
    return (await items(playlistId)).filter(i => i.watchedPct >= minPct);
  }

  // End-to-end check of every operation on two throwaway private playlists,
  // deleted afterwards whatever happens. Run after YouTube changes or when an
  // operation misbehaves.
  async function selftest() {
    const [v0, v1, v2, v3] = SELFTEST_VIDEOS;
    const steps = [];
    const created = [];
    const step = async (name, fn) => {
      try {
        steps.push({ step: name, ok: true, detail: await fn() ?? null });
      } catch (error) {
        steps.push({ step: name, ok: false, detail: error.message.slice(0, 300) });
        throw error;
      }
    };
    const expect = (id, want) => waitFor(id, list => order(list) === want.join(',')).then(order);
    const stamp = new Date().toISOString().slice(0, 19);
    let a;
    let b;
    try {
      await step('videoIdOf rejects junk', async () => {
        try { videoIdOf('https://example.com/nope'); } catch { return 'threw'; }
        throw new Error('accepted a URL without a video id');
      });
      await step('items rejects a nonexistent playlist', async () => {
        try { await items('PLRIB68DXBTOzzzzzzzzzzzzzzzzzzzzzz'); } catch (error) { return error.message.slice(0, 80); }
        throw new Error('nonexistent playlist listed as empty');
      });
      await step('create from URL', async () => {
        a = await create(`yt-playlists selftest ${stamp}`, 'PRIVATE', [`https://youtu.be/${v0}`]);
        created.push(a.id);
        return expect(a.id, [v0]);
      });
      await step('add ids and URLs, with a repeat', async () => {
        await add(a.id, [`https://www.youtube.com/watch?v=${v1}&t=5`, `https://www.youtube.com/shorts/${v2}`, v3, v1]);
        return expect(a.id, [v0, v1, v2, v3, v1]);
      });
      await step('dedupe', async () => {
        const result = await dedupe(a.id);
        if (result.snapshot) dropSnapshot(result.snapshot);
        return expect(a.id, [v0, v1, v2, v3]);
      });
      await step('reorder (moves before and after)', async () => {
        await reorder(a.id, [v3, v1, v0]);
        return expect(a.id, [v3, v1, v0, v2]);
      });
      await step('reorder already in order', async () => (await reorder(a.id, [v3, v1])).status);
      await step('bulk remove snapshots, restore brings back order', async () => {
        const list = await items(a.id);
        const result = await remove(a.id, list.map(i => i.setVideoId));
        if (!result.snapshot) throw new Error('bulk remove took no snapshot');
        await expect(a.id, []);
        await restore(result.snapshot);
        dropSnapshot(result.snapshot);
        return expect(a.id, [v3, v1, v0, v2]);
      });
      await step('copy, then copy again is a no-op', async () => {
        b = await create(`yt-playlists selftest ${stamp} copy`, 'PRIVATE');
        created.push(b.id);
        await copy(a.id, b.id);
        const copied = await expect(b.id, [v3, v1, v0, v2]);
        const again = await copy(a.id, b.id);
        if (again.status !== 'NOTHING_TO_ADD') throw new Error(`second copy added ${again.actions}`);
        return copied;
      });
      await step('watched and unavailable run', async () => `${(await watched(a.id)).length} watched, ${(await unavailable(a.id)).length} unavailable`);
      await step('rename, describe, privacy', async () => {
        await rename(a.id, `yt-playlists selftest ${stamp} renamed`);
        await describe(a.id, 'selftest');
        await setPrivacy(a.id, 'UNLISTED');
        const hit = await until(mine, all => all.some(p => p.id === a.id && p.privacy === 'UNLISTED' && p.title.endsWith('renamed')),
          all => JSON.stringify(all.find(p => p.id === a.id)));
        return hit.find(p => p.id === a.id).privacy;
      });
      await step('deletePlaylist refuses WL', async () => {
        try { await deletePlaylist('WL'); } catch { return 'threw'; }
        throw new Error('WL delete was attempted');
      });
    } catch {
      // The failing step is already recorded; cleanup still runs below.
    } finally {
      await step('delete test playlists', async () => {
        for (const id of created) await deletePlaylist(id);
        await until(mine, all => !all.some(p => created.includes(p.id)), () => 'test playlists still listed');
        for (const id of created) snapshots(id).forEach(s => dropSnapshot(s.key));
        return `${created.length} deleted`;
      }).catch(() => {});
    }
    return { pass: steps.every(s => s.ok), steps };
  }

  return {
    call, videoIdOf, mine, library, find, items, unavailable, waitFor, edit, add, remove, moveAfter, moveBefore,
    reorder, dedupe, snapshot, snapshots, dropSnapshot, restore, rename, describe, setPrivacy, create, deletePlaylist,
    copy, watched, selftest,
  };
})();
'yt helper loaded';
