# Yahoo Realtime gofile scraper

This repository contains a small Python CLI utility for collecting `gofile.io`
links from Yahoo! JAPAN's realtime search results.

## Usage

1. Install the dependency:
   ```bash
   pip install -r requirements.txt
   ```

2. (Optional) Export a cookie string captured from your browser session if Yahoo
   blocks anonymous traffic:
   ```bash
   export YAHOO_COOKIE='B=...; XA=...;'
   ```

3. Run the scraper:
   ```bash
   python scrape_gofile_links.py --pages 2 --batch-size 20 --output links.txt
   ```

   * `--pages` controls how many pagination requests are performed.
   * `--batch-size` should match the number of tweets Yahoo returns per page.
   * `--output` writes the collected links to a file (otherwise the links are
     printed to stdout).
   * Use `--proxy https=http://proxy:8080` to force a proxy or `--no-env-proxies`
     to bypass inherited proxy variables when necessary.

You can supply additional headers through `--headers headers.json` (a JSON file
with a simple key-value mapping) or a raw cookie string via `--cookies`.

### Automatically derive browser headers and cookies

Export a HAR file from your browser (Network tab → Save all as HAR) while the
realtime search page is open and run:

```bash
python har_session_extractor.py session.har --headers-json headers.json --print-cookie
```

The helper will locate Yahoo realtime API requests in the HAR, write a headers
JSON file compatible with `--headers`, and print the cookie string for
`--cookies` or the `YAHOO_COOKIE` environment variable. Use `--index` if multiple
matching requests exist, or `--pattern` to target a different endpoint.
