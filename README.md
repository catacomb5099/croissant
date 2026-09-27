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
random seed it used, so a week can be reproduced with `--seed <n> --date <date>`.
