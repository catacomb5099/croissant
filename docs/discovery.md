# Discovery: playlist curator (27-09-2026)

Goal: pre-compute a weekly "suggested playlist" per hand-defined category (for example
"80s indie pop") from Discogs popularity and YouTube Music play counts, as a project separate
from naviseerr. naviseerr will later only read the output. Everything below was verified with
real requests on 27-09-2026 unless marked otherwise.

## In short

| Question | Answer |
|---|---|
| Does Discogs search work without a token? | Yes. The docs say authentication is required; a plain request returns results and a `25 requests/minute` limit header. A free token raises that to 60/min and adds cover images. Not needed for this project. |
| Do the filters we need exist? | Year range (`year=1980-1989`), genre, style, master vs release, and `sort=have` (most collected) all work. `decade` does not filter (it behaves like a text search). `format=Album` is required, otherwise singles come back too. There is no "most sold" sort. |
| Can we get per-song play counts? | Yes, from YouTube Music, anonymously. Over 20 sample albums: 20/20 found, 260/262 tracks carried a play count. About 1 second per album. |
| Does the selection do what the brief asked? | Yes: 50/25/25 tiers, one-per-artist/album in the middle tier, playlist-wide caps of 5 per artist and 2 per album, seeded randomness, history log, exclusion of the last 4 editions. 16 automated checks pass. |
| Did it run end to end? | Yes, live, for "80s indie pop" and "current pop". Output files are in `output/`, the log of what was picked and why in `history/`. "90s grime" returns 0 albums (see below). |
| Weekly cost | Per category: 1 Discogs request + about 200 YouTube Music requests, about 1.5 minutes. Three categories fit comfortably in a free GitHub Actions run. |

## 1. Discogs

Verified against `https://api.discogs.com/database/search` with a descriptive `User-Agent`
and no token.

- **Authentication.** Search works without a token. Response headers report
  `x-discogs-ratelimit: 25` unauthenticated. With a personal token
  (`Authorization: Discogs token=...`) the documented limit is 60/min. The code sends the
  token when `DISCOGS_TOKEN` is set in the environment and works without it. Cover images
  (`thumb`, `cover_image`) are empty strings without a token, which we do not need.
- **Filters that work.** `year=1980-1989` returned 100/100 results inside the decade.
  `style=Indie Pop`, `genre=Pop`, `type=master` (one entry per album across all its
  pressings) and `type=release` (every pressing separately, so the same album appears
  many times) behave as documented. `format=Album` drops singles and EPs: without it
  "The Cure - Lullaby" and "The Smiths - Panic" show up as "albums" and later match the wrong
  YouTube Music release.
- **Filters to avoid.** `decade=1980` returned albums from 2012, 2019 and 2024; it is not a
  filter. Use the `year` range.
- **The style filter is loose.** Only 34 of the top 100 "Indie Pop" masters carry that
  exact style tag; the rest are tagged Indie Rock, Jangle Pop, Alternative Rock and so on
  and match through Discogs' search index. For a playlist this is a feature (the pool is
  wider), but the category name should be read as "around indie pop", not a strict tag.
- **Sorting.** `sort=have&sort_order=desc` gives most-collected first (`community.have`);
  `sort=want` also works. Ordering is not perfectly monotonic (16 of 99 neighbouring pairs
  in the top 100 were slightly out of order, a few percent apart), which does not matter
  for a top-100 cut. There is no "most sold" sort in the search API; sales figures exist
  only per release in the marketplace endpoints, one request each, so we use "most
  collected".
- **What a search result gives.** `title` as `"Artist - Album"` (the code splits on the
  first `" - "`), `year`, `master_id`, `genre[]`, `style[]`, `format[]`,
  `community.have/want`. Artist names carry Discogs disambiguation suffixes such as
  `"M.I.A. (2)"` or `"MIA*"`, which the code strips before searching YouTube Music.
  Compilations appear as artist `"Various"` and are dropped.
- **What a master release gives** (`/masters/{id}`, one request each): `title`, `artists[]`,
  `year`, `genres`, `styles`, `tracklist[]` with `position`, `title`, `duration`, plus
  `main_release` and `num_for_sale`. It has no play counts, so we do not fetch it: the
  YouTube Music album carries its own track list and the search result already has
  artist, title and year. Saves 100 requests per category.
- **Categories that return nothing.** "90s grime" returns 0 masters: the oldest grime
  album on Discogs is from 2003 (Dizzee Rascal, "Boy In Da Corner"), which is when the
  genre started. `categories.yaml` keeps the entry as briefed with a comment; changing the
  years to 2000-2009 gives a real playlist.
- **Live albums pass the `format=Album` filter** ("Lover (Live From Paris)", "Live From
  Glastonbury"). Harmless so far (most are not on YouTube Music as albums), and excluding
  them is a one-line follow-up if they show up in playlists.
- **Current pop confirms the problem the brief describes.** The 10 most-collected pop
  albums from 2024-2026 include two Taylor Swift and two Sabrina Carpenter albums; without
  caps they would fill the top of the playlist.

## 2. YouTube Music (ytmusicapi 1.12.2, anonymous)

For each Discogs album: `search("<artist> <album>", filter="albums")`, take the first hit,
`get_album(browseId)`, read `tracks[].views` (a display string like `"38M plays"`) and turn
it into a number (`38000000`). K/M/B suffixes and comma-separated plain numbers are handled.

Measured over the 20 most-collected 80s indie pop masters:

- 20/20 searches returned an album; 260/262 tracks had a play count (the two missing were
  hidden/unavailable tracks; they count as 0 plays and never get picked).
- 20 seconds for 20 albums, 40 requests: about 1 second per album.
- 3 of the 20 matches were wrong, all caused by Discogs singles ("Lullaby" resolved to a
  2001 Greatest Hits, "This Charming Man" and "Panic" to other Smiths albums). Two fixes:
  `format=Album` on the Discogs side, and a year check on the YouTube Music side (a match
  whose album year is outside the category's year range is discarded).
- Play counts are album-track figures, so the same song on a standard and a deluxe edition
  has two different ids and two counts. The selection keeps only the most played copy of a
  given artist + title.

No token, cookie or browser session is used, in line with ytmusic-adapter's "anonymous only"
rule. Corporate proxy: the process needs `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` pointing at a
bundle that includes the proxy root certificate; a plain server or GitHub Actions does not.

## 3. Selection (implemented in `curator/picker.py`, pure, no network)

Input: the pool of tracks (about 1000 for 100 albums) with artist, album and plays.
Output: one playlist of N songs (default 40; 30-50 by `--size`).

1. Drop songs featured in the last K editions (default 4) and duplicate songs.
2. **Top tier, 50%:** walk the pool from most to least played; take a song if its artist has
   fewer than 5 songs and its album fewer than 2 in the playlist so far.
3. **Middle tier, 25%:** from what is left, take the top quarter by plays (well known, but
   not the hits), shuffle it with the edition's seed, and pick with one per artist and one
   per album within this tier (the playlist-wide caps still apply).
4. **Random tier, 25%:** shuffle everything left and pick under the playlist-wide caps.
5. If the pool is too thin to fill a tier, top up by popularity; final order is shuffled so
   the playlist does not open with 20 hits followed by 20 unknowns.

Every song records its tier and a reason (for example `#3 of 1048 by plays` or
`random pick (seed 1234) from 812 remaining`). The seed is fresh each run unless `--seed`
is given and is written into the edition, so any week can be reproduced exactly.

Why editions differ week to week even though the top tier is deterministic: last week's
20 hits are excluded, so the next 20 move up; the other 20 depend on the seed.

Checks (`uv run pytest`, 16 passed): playlist-wide caps hold across tiers; no duplicates;
excluded songs never reappear; sizes 30/40/50 come out exact; tier counts are 20/10/10 at
size 40 and within one of each other at size 30; same seed reproduces, different seeds
differ; the top tier really is the most-played set the caps allow; a deluxe-edition copy of
a song is kept once; a thin pool returns what the caps allow rather than breaking them.

## 4. Live run (27-09-2026)

`uv run curate 80s-indie-pop --date 2026-09-27` and `uv run curate current-pop --date 2026-09-27`,
then a second "80s indie pop" edition dated 2026-10-04 to prove the exclusion.

| Edition | Albums found on YouTube Music | Pool | Wall time | Result |
|---|---|---|---|---|
| 80s indie pop, 2026-09-27 (seed 1738171583) | 79 of 100 | 1040 songs | 81 s | 40 songs, tiers 20/10/10, 19 artists, 26 albums, at most 2 per album. Most present: The Smiths 5, The Housemartins 4, The Replacements 4, Galaxie 500 3. Plays: hits 3M-197M, middle 103K-1M, random 816-180K. |
| Current pop, 2026-09-27 (seed 1012094420) | 96 of 100 | 1255 songs | 92 s | 40 songs, tiers 20/10/10, 34 artists, 28 albums, at most 2 per album. Most present: Sabrina Carpenter 3, Bruno Mars 3, Ariana Grande 2, Dua Lipa 2. Plays: hits 399M-4.3B, middle 15M-319M, random 49K-30M. |
| 90s grime | - | - | 1 s | Stops with "Discogs returned no albums ... widen the category". |
| 80s indie pop, 2026-10-04 (seed 364416323) | 79 of 100 | 1040 songs | 75 s | 40 songs excluded from the previous edition, 0 songs in common with it, 27 artists, 32 albums. Most present: The Smiths 5, Prefab Sprout 3, The Orchids 2, Deacon Blue 2. Plays: hits 1M-60M, middle 102K-455K, random 2K-200K. |

Reading the numbers: the caps are what keep "current pop" varied (34 artists in 40 songs; Taylor
Swift, with two albums in the top 10 most collected, gets at most 4 songs and in this edition
fewer). In "80s indie pop" the second edition's hits are visibly a tier down (the top-20 by
plays were used up the week before), which is the intended weekly rotation; after 4 editions
the first edition's songs become eligible again.

Misses: 21 of the 80s albums returned no songs (not on YouTube Music as an album, or the
match failed the year check); 4 of the current pop albums (live recordings and one
compilation-like release). Both rates are fine for a pool of about 1000 songs.

## 5. Cost of a weekly run

Per category: 1 Discogs request (100 results per page; 2 if compilations push it over) and
2 YouTube Music requests per album, so about 200. Wall time 81 seconds for 80s indie pop and 96 seconds for current pop, dominated
by YouTube Music latency; the selection itself takes milliseconds. Three categories: about
600 YouTube Music requests and about 5 minutes per week. Discogs' 25/min limit is
irrelevant at this volume; YouTube Music has no published limit and this is far below what
the ytmusic-adapter already sends. The risk is the same as for the adapter: an IP that
YouTube starts to challenge. Running on the owner's server keeps it on an IP that already
works.

## 6. Popularity versus variety

The 80s indie pop pool is wide (about 80 distinct artists in the top 100 albums, the
biggest artist has 4 albums), so caps rarely bind. Current pop is narrow: a handful of
artists own most of the plays, and the album cap of 2 is what actually shapes the list.

| Option | Tiers (top/mid/random) | Caps (artist/album) | Feel |
|---|---|---|---|
| A. As briefed (implemented default) | 50/25/25 | 5/2 | Recognisable: half the list is the hits you expect, with breathing room. |
| B. More variety | 40/30/30 | 3/1 | No artist gets more than 3 songs and no two songs share an album; more discovery, fewer sing-alongs. |
| C. More hits | 60/20/20 | 5/3 | Closer to a "best of the genre" list; big artists dominate current pop. |

Recommendation: keep A as the default and try B for "current pop" only, where the pool is
top-heavy. Both are two numbers in the call (`max_per_artist`, `max_per_album`) and could
become per-category settings in `categories.yaml` if the owner wants to tune them after
listening to a few editions; not added yet because one default may turn out to be enough.

## 7. How naviseerr should consume this

Proposal, not built:

- naviseerr reads the JSON editions from a URL. Simplest: raw GitHub, for example
  `https://raw.githubusercontent.com/catacomb5099/playlist-curator/main/output/80s-indie-pop/2026-09-27.json`.
  Alternative: a folder on the owner's server mounted into the naviseerr container. Either
  way, naviseerr needs one small extra file to know what exists: `output/index.json` listing
  each category and its latest edition date (follow-up in this repo, a few lines in the CLI).
- naviseerr shows a "Suggested playlists" section: one card per category with the title,
  edition date and the 40 songs; the `tier`/`reason` fields can back a small "why this
  song" hint.
- Downloading one is a new job type in naviseerr. Today naviseerr downloads YouTube
  playlists by playlist id; these editions are lists of individual `videoId`s with no
  YouTube playlist behind them, so a "custom list" download type (a list of videoIds plus a
  name) is required. Follow-up in naviseerr.

Output shape per edition:

```json
{"title": "80s indie pop", "category": {"title": "...", "year": "1980-1989", "style": "Indie Pop"},
 "editionDate": "2026-09-27", "seed": 123456789,
 "tracks": [{"videoId": "...", "title": "...", "artists": ["The Smiths"], "album": "The Queen Is Dead",
             "albumYear": 1986, "popularity": 38000000, "tier": "top", "reason": "#1 of 1048 by plays"}]}
```

## 8. Weekly scheduler

| Option | For | Against |
|---|---|---|
| GitHub Actions cron that runs `curate` for every category and commits `output/` and `history/` back to `main` | No server to maintain; free at this volume (about 10 minutes a week); output is immediately at a raw GitHub URL; the commit history is the audit trail. | GitHub's runner IPs are shared and YouTube may challenge them (unverified; ytmusic-adapter's live tests would show the same). The workflow needs permission to push to `main`. |
| cron on the owner's server (where naviseerr runs) writing to a folder naviseerr mounts | Same network as naviseerr, an IP that already works with YouTube Music; no GitHub write permission needed. | One more thing to keep alive on the server; no public URL unless it also pushes to GitHub; history lives only on that box unless backed up. |

Recommendation: start with GitHub Actions because it needs nothing new; if YouTube blocks
the runner, move the same command to the server. In both cases a run is idempotent per
date (rerunning the same day overwrites that day's file but would append a second history
line, so schedule it once).

## Not included / follow-ups

- `output/index.json` (latest edition per category) for naviseerr to discover editions.
- The GitHub Actions workflow file itself (decision first: see section 8).
- Per-category tier ratios and caps in `categories.yaml` (see section 6).
- "Current pop" year range does not roll automatically; bump it each January.
- Discogs master tracklists are not fetched; if a category ever needs them (for example
  to catch albums missing from YouTube Music) it is one request per album.
- Live tests are not part of the default `pytest` run (`-m 'not live'`); there are none yet.
