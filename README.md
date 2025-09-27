# Yahoo Realtime gofile scraper

This repository contains a small Python CLI utility for collecting `gofile.io`
links from Yahoo! JAPAN's realtime search results.

## Usage

### Super-easy GUI (recommended)

1. Install the dependency:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the GUI:
   ```bash
   python yahoo_realtime_gui.py
   ```
3. Click **HARファイルをえらぶ** and pick the HAR you exported from your browser
   while viewing the Yahoo realtime page.
4. Press **ワンクリックでヘッダーとクッキーをつくる**. The app writes
   `<name>_headers.json` and `<name>_cookie.txt` next to the HAR and shows their
   contents in the window.
5. Hit **スタート！** to gather links (adjust the keyword or page counts if you
   like). Use **リンクをファイルに保存** to export the list as a text file.

The buttons are big, the labels are written in plain Japanese, and the entire
flow stays inside the window so that even very young users can handle the
scraper without touching the command line.

### CLI scraper

If you prefer the command line you can still run the original script:

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
