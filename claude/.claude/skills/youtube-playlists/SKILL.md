---
name: youtube-playlists
description: View and edit the user's own YouTube playlists, including Watch Later, through their signed-in Chrome session. Use whenever the user asks to list, show, count or search their YouTube playlists or Watch Later, add videos (by id or URL), remove, reorder or deduplicate entries, copy one playlist into another, clear watched or unavailable videos from Watch Later, back up or restore a playlist, create, rename, describe, change privacy of, or delete a playlist. Runs in a youtube.com tab via the Claude in Chrome extension; no API key or OAuth app.
allowed-tools:
  - Read
  - Write(~/youtube-playlist-backups/**)
  - mcp__claude-in-chrome__tabs_context_mcp
  - mcp__claude-in-chrome__tabs_create_mcp
  - mcp__claude-in-chrome__navigate
  - mcp__claude-in-chrome__javascript_tool
  - mcp__claude-in-chrome__tabs_close_mcp
---

# youtube-playlists

Reads and edits playlists with the same InnerTube endpoints the YouTube web
app uses, signed with the page's own session cookies (`SAPISIDHASH`). The
cookies never leave the browser. This is the only working route to Watch
Later: the official Data API has returned it empty since 2016, `ytmusicapi`
does not support it, and reading Chrome's cookie store from the shell is
blocked by macOS.

## Setup (once per page load)

1. `tabs_context_mcp`, then `tabs_create_mcp` and `navigate` to
   `https://www.youtube.com/`.
2. Read `yt-playlists.js` from this skill dir and pass its **exact** text to
   `javascript_tool`. Do not shorten or retype it; a hand-edited copy drifts
   from the tested file. It defines `window.yt` and returns
   `'yt helper loaded'`. Operations can follow in the same call after it.
3. Navigating the tab drops `window.yt`; inject again after any navigation.
4. Close the tab when done.

If `call` throws `not signed in`, ask the user to sign in to YouTube in
Chrome. Do not try to read cookies from disk.

If an operation misbehaves, run `await yt.selftest()` first. It exercises
every operation on two throwaway private playlists, deletes them whatever
happens, and returns `{pass, steps}` (about a minute). A failing step points
at what YouTube changed.

## API (`window.yt`, all async unless noted)

| Call | Does |
|---|---|
| `mine()` | Editable playlists `{id, title, privacy}`, including `WL`. |
| `library()` | Library > Playlists: also saved playlists of others, podcasts, `LL` (Liked). No privacy. |
| `find(title)` | One editable playlist by exact title (case-insensitive). Throws on 0 or several matches. |
| `items(id, {includeUnavailable})` | Every entry, all pages, in order: `{index, videoId, setVideoId, title, channel, duration, watchedPct, playable}`. Throws on a nonexistent playlist. `includeUnavailable: true` adds the private and deleted entries YouTube hides. |
| `unavailable(id)` | Only the private and deleted entries. |
| `watched(id, minPct = 90)` | Entries whose resume marker is at least `minPct`. |
| `add(id, videos)` | Append videos; ids or URLs (`youtu.be`, `watch?v=`, `/shorts/`, `/live/`, `/embed/`, music.youtube.com). 50 per request. |
| `remove(id, setVideoIds)` | Remove entries. Takes `setVideoId`, not `videoId`. More than 3 entries snapshots first; the key is in the result. |
| `reorder(id, videos)` | Put these videos at the top in this order; unlisted entries keep their order after them. Moves only what is out of place. |
| `moveAfter(id, set, afterSet)` / `moveBefore(id, set, beforeSet)` | Single moves. |
| `dedupe(id)` | Remove repeats, keeping each video's first entry. Always snapshots first. |
| `copy(from, to)` | Append every playable video of `from` that `to` lacks, in order. Idempotent. |
| `snapshot(id)` | Save every entry to youtube.com localStorage. Returns `{key, playlistId, title, takenAt, videoIds}`. |
| `snapshots(id?)` (sync) / `restore(key)` / `dropSnapshot(key)` (sync) | List, restore (re-add missing, then reorder; later additions stay at the end; private videos cannot be re-added and are reported), delete. |
| `create(title, privacy = 'PRIVATE', videos = [])` | Returns `{id, title, privacy}` once the playlist is readable. |
| `rename(id, name)`, `describe(id, text)`, `setPrivacy(id, 'PRIVATE'\|'UNLISTED'\|'PUBLIC')` | Playlist metadata. |
| `deletePlaylist(id)` | Delete a playlist. Refuses `WL` and `LL`. |
| `waitFor(id, check)` | Poll until `check(items)` is true (30 s limit, retries transient errors). |
| `videoIdOf(input)` (sync) | Video id from an id or URL; throws if none. |
| `call(endpoint, body)` | Raw InnerTube POST for anything not covered. |

Watch Later's id is `WL`. Liked videos is `LL` and is read-only here.

## Rules

- **Resolve playlists by title inside the page.** Use `find('Title')` in the
  same script as the edit. The extension blanks some playlist ids in tool
  output as `[BLOCKED: Base64 encoded data]`, so ids copied out of a result
  are unreliable. Titles are not unique (the account has two "Work"
  playlists); when `find` throws, show the matches with privacy and ask.
- **Verify every write with `waitFor`.** Reads lag writes by a few seconds; a
  `STATUS_SUCCEEDED` alone proves nothing. Re-list, compare the order or
  count you expect, and report the verified state.
- **Back up to disk before destructive changes.** Before a bulk remove,
  dedupe, or delete, run `snapshot(id)` and write the returned record with
  `Write` to `~/youtube-playlist-backups/<title>-<takenAt>.json`.
  localStorage is lost if the user clears site data. To restore from a file,
  `localStorage.setItem(key, JSON.stringify(record))` then `restore(key)`.
- **Look up `setVideoId`s fresh** with `items()` right before a remove or
  move. They are per entry, so a video in the list twice has two.
- **Ask before destructive or bulk changes:** deleting a playlist, removing
  more than a handful of entries (show the list first, for example the
  `watched()` or `unavailable()` result), or making a playlist public. Adds,
  single removes the user named, and reorders need no second confirmation.
- Keep request volume human-scale. The yt-dlp project warns that accounts
  used for automation risk bans; use the batched calls instead of looping
  single ones.

## Known behaviour

- Watch Later's header count includes hidden private and deleted entries;
  `items('WL')` leaves them out unless `includeUnavailable` is set (273 vs
  275 on 2026-10-14, the 2 being `[Private video]`).
- A new playlist answers "The playlist does not exist." for a few seconds;
  `create` waits it out and `waitFor` retries through it.
- Short playlists include a "recommended videos" shelf in the browse
  response. `items()` reads only the playlist's own list.
- Some entries have no byline (multi-creator videos); `items()` fills
  `channel` from oEmbed for those.
- `ACTION_MOVE_VIDEO_BEFORE` without a successor id is accepted and does
  nothing; the helper always passes one.

## Example

```js
const ri = await yt.find('RI (Unofficial)');
const wanted = ['https://youtu.be/fwjac5bVYnc', 'MAq_C_2e2dU'];
await yt.add(ri.id, wanted);
const after = await yt.waitFor(ri.id, list => wanted.map(yt.videoIdOf).every(v => list.some(i => i.videoId === v)));
after.map(i => `${i.index + 1}. ${i.title} (${i.channel})`);
```
