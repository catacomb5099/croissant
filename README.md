# playlist-curator

Pre-computes weekly "suggested playlists" for [naviseerr](https://github.com/catacomb5099/naviseerr). Each category (for example "80s indie pop") is a Discogs filter (years + genre/style, sorted by most collected); the top albums are looked up on YouTube Music to get per-track play counts, and one playlist of 30-50 songs is built from that pool so the most popular songs surface without one artist or album taking over. Every edition is written as a JSON file naviseerr can read as-is. See [docs/discovery.md](docs/discovery.md) for findings, trade-offs and how naviseerr should consume the output.

## Run it

```sh
uv sync
uv run curate 80s-indie-pop          # writes output/80s-indie-pop/<today>.json, appends history/80s-indie-pop.jsonl
uv run curate current-pop --size 30  # 30 songs instead of the default 40
uv run pytest && uv run ruff check .
```

Categories live in `categories.yaml`. No credentials are needed; setting `DISCOGS_TOKEN`
(free, from discogs.com/settings/developers) only raises the Discogs limit from 25 to 60
requests per minute. Behind a corporate proxy, point `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`
at a bundle that includes the proxy's root certificate.

Each edition excludes songs featured in the last 4 editions (`--exclude-last`) and records the
random seed it used, so the pick can be replayed with `--seed <n> --date <date>` against the same
pool (Discogs ranking and play counts move, so a month later the result will differ). A run stops
without writing anything when the edition file already exists or fewer than `--size` songs are
available.

## Run it as a service

naviseerr does not run the command above itself: once a week it asks this service to do it over
HTTP, then checks back until the run is finished. Start the service with a secret token that both
sides share (`openssl rand -hex 32` makes a good one); it refuses to start without one.

```sh
export CURATOR_TOKEN=<the token>      # required, at least 16 characters
uv run curate-service                 # listens on port 8010
curl localhost:8010/health            # {"status":"ok"} - the only call that needs no token
```

Every other call needs the header `Authorization: Bearer <token>`:

- `POST /v1/runs` with an optional body `{"categories": ["80s-indie-pop"]}` (default: all of them)
  starts a run and answers at once with its `runId`; while a run is going, a second POST just
  returns that same run instead of starting another.
- `GET /v1/runs/<runId>` (or `/v1/runs/latest`) shows progress: the run is `queued`, `running`,
  `succeeded`, `partial` (some categories written, some not) or `failed`, with one line per category (`written`, `exists`, `no_albums`,
  `thin_pool` or `error` plus a plain-language message).
- `GET /v1/editions` lists the latest edition per category (key, title, the category's `year`
  range, edition date, track count); `GET /v1/editions/<category>`
  (optionally `?date=YYYY-MM-DD`) returns the edition JSON itself.

Runs are kept as `runs/<runId>.json`, so a restart does not lose them; a run cut short by a
restart is marked `failed` ("interrupted by restart"). Categories run one after another in a single
worker so YouTube Music is never hit in parallel. `CURATOR_ROOT` relocates `categories.yaml`,
`output/`, `history/` and `runs/` (default: this folder).

With Docker (single process on purpose; mount the three data folders to keep editions across restarts):

```sh
docker build -t playlist-curator .
docker run -d -p 8010:8010 -e CURATOR_TOKEN=<the token> \
  -v curator-output:/app/output -v curator-history:/app/history -v curator-runs:/app/runs playlist-curator
```

Behind a corporate proxy add `-e REQUESTS_CA_BUNDLE=... -e SSL_CERT_FILE=...` pointing at a bundle
that includes the proxy's root certificate, as described above.

