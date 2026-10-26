# Stock-music libraries: access recipes

How to search each library and where its preview audio sits, so `compare.py`
can test a candidate. Checked on 2026-10-24 while identifying 100 Realm
Invader tracks; "matches" counts how many came from each library there.

Previews are watermarked or low bitrate. A watermark raises the BER of a true
match to about 0.15-0.25, still well under the 0.30 threshold.

## Storyblocks (43 matches)

`libsearch.py storyblocks` covers it.

- Plain HTTP with a browser User-Agent works; `agent-browser` gets 403.
- Search: `https://www.storyblocks.com/audio/search/<slug>?media-type=music`,
  48 results per page, `&page=N`. Past the last page it answers 404.
- Every result is embedded in the page as a JSON `"stockItem"` object:
  `title`, `duration` (whole seconds), `composer`, `previewUrl` (an `_NWM`
  MP3), `detailsUrl`, `collapsedSetId`, `numCollapses`.
- `duration_min` / `duration_max` filter server-side. With a mood or genre
  slug ("horror", "drums") they find tracks whose real title differs from the
  game's label. Without any slug they list the whole catalogue at that length
  (about 30 to 900 tracks per second of length). Listed lengths are the real
  length rounded down (13 of 14 known matches), occasionally one second
  longer. A search without results answers 404.
- The length listing shows one version per set (the set's representative):
  Life Ahead's stems, at the right length, never appeared in it.
- **Hidden versions.** A result stands for a set of versions (vocal,
  instrumental, "no voc", loops, stems, edits). List them with
  `&collapsed-set-id=<collapsedSetId>`. Several Realm Invader matches were
  only in the set: Dream Garden was the "Instrumental Backtrack", You Know was
  the vocal mix, and African was the "full loop".
- **Artist catalogue.** A track page links its artist as
  `portal_artist_ids=<id>`; `?media-type=music&portal_artist_ids=<id>` lists
  the whole catalogue (Jon Presstone: about 1,000 tracks), and the duration
  filters narrow it.
- Track pages carry the watermarked `_WM` preview in `og:audio`; the search
  result's `_NWM` preview is cleaner.

## stockmusic.net (34 matches)

`libsearch.py stockmusic`, `stockmusic-dump` and `catalog` cover it.

- Open JSON API, no key:
  `https://stockmusic.net/api/music/search?productable=track&text=<q>&page=N`
  (24 per page). `https://stockmusic.net/api/products/<UPC>` gives one product.
- The demo MP3 is the `media` entry of type `demomp3` (`url_slug`). Duration
  is `waveform.length * samples_per_pixel / sample_rate`.
- The API serves at most 416 pages (9,984 results) and answers 400 beyond
  that, whatever the total says. Page 1 of the default order is shuffled on
  every request; later pages are stable. `sortType=oldest` reads from the
  other end, so the default order plus `oldest` covers the whole catalogue
  (about 12,100 tracks). `sort=` is ignored.
- Vocal and instrumental mixes are separate products with neighbouring UPCs
  (TRA-MAS3291 and TRA-MAS3292). Test both.
- Files tagged `genre=Blues`, `date=2005` and an `IENG` name came from its
  legacy collections (WorldPulse, FilmEdge, MalePop): Tango, French Fried,
  Counting On You, My Indigo.
- The composer whose catalogue held the most matches: The Sound Room (Marshall
  Smith).

## Uppbeat (4 matches; earlier passes found many more)

- The API answers 429 to plain HTTP. Use `agent-browser`:
  `https://uppbeat.io/search?search=<title>&type=music`.
- Track pages play a "main version" preview; alternate versions are listed
  under it.
- Search runs on a Typesense index with a public search-only key that the
  page sends (watch the browser's network requests for
  `*.typesense.net/multi_search?x-typesense-api-key=...`; take the key from
  there each time rather than storing it). POST to that URL with collection
  `tracksWithEngagement`, `q: "*"` and `filter_by: "version_length:[lo..hi]"`
  lists the whole catalogue by length; fields include `version_preview_uri`,
  `contributor_name`, `mood`, `genre`, `is_alternative`. It held only main
  versions when tried.

## Pixabay (3 matches)

- Browser and plain HTTP get a Cloudflare challenge. Firecrawl `scrape` with
  `formats: ["rawHtml"]` returns the page; the preview is the
  `https://cdn.pixabay.com/download/audio/...mp3` URL in it.
- Search pages take a length filter, `?duration=240-480` (seconds), and
  carry no previews themselves; they name a `__BOOTSTRAP_URL__` whose JSON
  lists every result with `duration`, `user.username`, `name` and
  `sources.src` (the preview MP3). Fetch it with Firecrawl or with `fetch()`
  inside a Pixabay tab of the user's own Chrome (the Claude in Chrome tools),
  which passes the challenge. Seduction 2 ("Sexy Sensation") came from a
  4-8 min "sultry" search this way.
- YouTube titles like `some-track-name-117997` are Pixabay filenames; the
  source page is `https://pixabay.com/music/id-<n>/`.

## iTunes Search API (indie releases on streaming)

`libsearch.py itunes` covers it.

- `https://itunes.apple.com/search?term=<q>&entity=song&limit=200` gives
  `trackTimeMillis` and a 30 s `previewUrl`. compare.py matches a 30 s
  preview directly.
- Found Jazzscape ("Jazz Scape" by Boomer) by its duration, 160.8 s.

## AudD (5 matches on 7 leftovers)

- `identify.py` sends one clip per file. About ten anonymous requests a day.
  It returns Spotify, Deezer and lis.tn links for indie releases Shazam does
  not have. Prove each hit: `libsearch.py preview <spotify or deezer link>`,
  then `compare.py`.

## Deezer

- Open API, no key: `https://api.deezer.com/search?q=<terms>` and
  `https://api.deezer.com/track/<id>` give `duration` and a 30 s `preview`
  MP3 (`libsearch.py deezer`, `libsearch.py preview`). Some tracks are
  `readable: false` with no preview.

## Spotify

- The embed page `https://open.spotify.com/embed/track/<id>` works without an
  account: its `__NEXT_DATA__` JSON has `duration` (milliseconds) and
  `audioPreview.url`, a 30 s MP3 (`libsearch.py preview`). Region-restricted
  tracks (`playabilityReason: COUNTRY_RESTRICTED`) have no preview, from a US
  location too. An exact duration match (to the
  millisecond) plus Shazam agreement makes a candidate *likely*. That is not
  proof, so keep it out of the identified count.
- Tags `n=Converted by SpotiDownloader.com` plus `TSRC` (an ISRC) mean the
  developer ripped the file from Spotify. The artist's YouTube "Topic" channel
  usually has the upload.

## Envato: AudioJungle and Elements (1 match, through YouTube)

- **Envato Elements** works with plain curl: 
  `https://elements.envato.com/royalty-free-music[/<term>]/min-length-MM:SS/max-length-MM:SS[/pg-N]`,
  24 cards per page, 50 pages at most, each with an open MP3 preview
  (`data-testid="audio-card"`). Its catalogue is far smaller than
  AudioJungle's.
- **AudioJungle** answers 403 to curl; Firecrawl `scrape` returns it.
  `https://audiojungle.net/category/music?term=<mood>&length_min=M:SS&length_max=M:SS&sort=sales`
  gives 30 results per page with length, BPM and a signed preview MP3 that
  `compare.py` fetches directly. The length filter also matches alternate
  versions inside multi-version items.

## Others that produced one or two matches

- **Motion Array.** The preview is a signed `?Expires=` URL in the page HTML.
  Motion Array's own YouTube channel uploads its tracks and links the page.
- **Purple Planet.** It has "Sonic Search", which takes an audio upload and
  returns similar tracks. It is a page form, so drive it with `agent-browser`
  (`upload "#FileUploader_0" <mp3>`).
- **Incompetech / Kevin MacLeod** (incompetech.filmmusic.io), **Icons8**,
  **AudioSparx** (often found through YouTube descriptions), **Shutterstock**
  (plain HTML with preview MP3s), **The Artist Union**.
- **Music Vine.** `https://api.musicvine.com/api/tracks/<artist>/artists/<track>/track`
  returns preview URLs.
