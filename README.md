# TRMNL Home Dashboard

Combines the date + today's high/low, current weather + condition icon, a next-6-hours strip, a
5-day forecast strip, sunrise/sunset, and a sports panel showing the next game
for Liverpool FC, the Toronto Blue Jays, the Toronto Maple Leafs, the Toronto
Raptors, and the Buffalo Bills — soonest first, with out-of-season teams
dropped — into a single TRMNL screen, using a **private plugin (webhook
strategy)**: a script fetches all the data and pushes it to TRMNL on a schedule
via GitHub Actions; TRMNL renders it through a template you control.

## How it fits together

- [`fetch_and_push.py`](fetch_and_push.py) — pulls weather/sun from Open-Meteo,
  Liverpool's next match from football-data.org, and the next Blue Jays / Maple
  Leafs / Raptors / Bills game from ESPN's public API. `collect_games()` merges
  them into one `games` list, sorted by kickoff and with any team whose next
  game is past the horizon (see `SPORTS_HORIZON_DAYS`) removed. It all goes to
  your TRMNL webhook URL as `merge_variables`.
- [`template.html`](template.html) — the markup you paste into TRMNL's private
  plugin editor; it interpolates the pushed variables.
- [`.github/workflows/update-dashboard.yml`](.github/workflows/update-dashboard.yml) —
  runs the script every 30 minutes for free on GitHub Actions.
- [`preview.py`](preview.py) — renders `template.html` with TRMNL's real
  framework CSS into a local `preview.html` so you can check the layout in a
  browser before the device is set up.

## Previewing the layout without a device

```
python preview.py          # live data if your .env has creds, else sample data
python preview.py --fake    # sample data, no network calls
python preview.py --no-open # write preview.html without opening a browser
```

It loads TRMNL's own `plugins.css` from `trmnl.com`, so spacing and sizing
match the device (just in colour rather than 1-bit black & white). Handy for
deciding whether you've got room for more plugins on the screen.

## One-time setup

> New to this? [`SETUP.md`](SETUP.md) is a step-by-step guide for a first-time
> coder on Windows — installing Git, Python, and VS Code, cloning your own copy,
> and getting a preview running before you touch any of the steps below.

### 1. Create the TRMNL private plugin

1. In the TRMNL dashboard: **Plugins → Private Plugin → Add New**.
2. Strategy: **Webhook**.
3. Save it — TRMNL gives you a **Plugin Settings UUID**. Your webhook URL is:
   `https://usetrmnl.com/api/custom_plugins/<UUID>`
4. Open the plugin's **Markup** editor, switch the view to **Full**, and paste
   in the contents of [`template.html`](template.html). TRMNL's live previewer
   lets you tweak spacing/sizing for the actual OG display — treat the
   provided layout as a first draft.
5. Add the plugin to a playlist (or make it the only plugin) so it's what
   shows on the device.

### 2. Get a football-data.org API key

Free tier, no credit card: <https://www.football-data.org/client/register>.
The free tier covers the Premier League, which is what the script queries.

### 3. Decide your weather location

Grab lat/lon for wherever you want weather/sunrise-sunset for (not
necessarily Liverpool) — e.g. from Google Maps ("what's my lat/lon here").

### 4. Push this to GitHub

```
git add -A
git commit -m "Initial TRMNL dashboard project"
gh repo create trmnl-dashboard --private --source=. --push
```

(Or create the repo on GitHub first and `git remote add origin ...` yourself.)

### 5. Configure GitHub Actions secrets and variables

In the repo: **Settings → Secrets and variables → Actions**.

**Secrets** (sensitive):
- `TRMNL_WEBHOOK_URL`
- `FOOTBALL_DATA_API_KEY`

**Variables** (not sensitive):
- `WEATHER_LAT`, `WEATHER_LON`
- `TIMEZONE` — IANA name, e.g. `Europe/London` or `America/New_York`
- `TEMP_UNIT` — `celsius` or `fahrenheit`
- `SPORTS_HORIZON_DAYS` — optional; hide a team whose next game is more than
  this many days away. Leave it unset to use the default of 30.

### 6. Test it

- Locally (PowerShell): copy `.env.example` to `.env`, fill in your values,
  then install and run. The script auto-loads `.env` via `python-dotenv`
  (`.env` is gitignored — never commit it):
  ```powershell
  pip install -r requirements.txt
  copy .env.example .env   # then edit .env
  python fetch_and_push.py
  ```
  If you'd rather not use a `.env` file, set the same names as `$env:`
  session variables instead — the script reads plain environment variables
  too, and real env vars win over `.env`.
- On GitHub: **Actions → Update TRMNL dashboard → Run workflow** to trigger it
  manually and check the logs.
- Force TRMNL to pull the latest state via the plugin's "Force Refresh" in
  its dashboard if you don't want to wait for the device's normal refresh
  cycle.

## Notes / known limitations

- **Offseasons**: a team with no scheduled game, or whose next game is more
  than `SPORTS_HORIZON_DAYS` (default 30) away, is dropped from the panel
  entirely rather than showing a fixture months out — so once the Blue Jays'
  season ends, they disappear until spring training is within the horizon. If
  every team is out of season the panel shows a "No games in the next N days"
  line. `get_espn_next_game()` also filters to games whose status is `pre` and
  whose start time is still in the future, so a *postponed* game (which ESPN
  leaves looking not-completed) can't show up as the "next" one.
- **Rate limits**: football-data.org free tier is 10 requests/minute; this
  script makes 2 calls per run. `football_data_get()` reads the
  `X-Requests-Available-Minute` / `X-RequestCounter-Reset` response headers
  and backs off on a 429, per football-data.org's guidance. The 4 ESPN calls
  hit an unauthenticated public endpoint with no documented limit. TRMNL
  webhook free tier is 12 pushes/hour — the 30-minute schedule uses well
  under that.
- **Payload size**: TRMNL free tier caps webhook payloads at 2KB. The current
  payload (current conditions + 6 hourly + 5-day forecast + five teams) is
  ~1.4KB — still under, but the margin is thinner now, so watch it if you add
  fields. The weather-icon SVGs live in the template, not the payload, so they
  don't count.
- **Sports panel height**: five teams in season at once fills the right column.
  It's `overflow: hidden`, so adding a sixth team (or very long opponent names)
  would clip the bottom rather than reflow — trim the list or drop to a
  one-line-per-team format if you hit that.
- **Weather icons**: the script sends a keyword (`clear`, `partly`, `cloudy`,
  `fog`, `rain`, `snow`, `storm`) for current conditions and for each hourly /
  daily slot. `template.html` has one `.wx--<keyword>` CSS rule per keyword,
  each a URL-encoded line-icon SVG used as a `mask` and painted in
  `currentColor`. To add a keyword: map it in `WMO_ICONS` (Python) and add one
  `.wx--<keyword>` rule (encode the SVG the same way as the others).
