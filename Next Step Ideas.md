# Next Step Ideas

A running list of ideas for future versions of the TRMNL dashboard. Nothing here
is committed to — it's a scratchpad for things worth considering.

---

## 1. User-configurable teams

**Goal:** let people pick their own teams instead of the hardcoded Liverpool /
Toronto / Buffalo list, so the repo is genuinely reusable as a template.

**Where it's hardcoded today:** the `records = [...]` list in `collect_games()`
in `fetch_and_push.py`. Everything downstream (`collect_games`, the horizon
filter, the template's `{% for game in games %}`) is already generic.

**Sketch:**

- Add a committed `teams.json` file the user edits once:
  ```json
  [
    { "provider": "espn", "sport": "football/nfl", "abbr": "BUF", "name": "Buffalo Bills" },
    { "provider": "football-data", "competition": "PL", "match": "liverpool", "name": "Liverpool FC" }
  ]
  ```
- Generalize `get_lfc_next_match` → `get_football_data_next_match(api_key, competition, name_query, display_name)`.
- Rewrite `collect_games()` to load the file and dispatch on `provider`.
- Make `FOOTBALL_DATA_API_KEY` optional — only required if a team actually uses
  the `football-data` provider. ESPN also covers soccer (`soccer/eng.1`), so the
  zero-API-key path should be documented.
- `preview.py` needs no change (its `SAMPLE` stays static).
- Document ESPN sport paths / team abbreviations and football-data competition
  codes in `SETUP.md`.
- Optional: also honor a `TEAMS_JSON` GitHub repo variable so config can be done
  entirely through the web UI without editing files.

---

## 2. (next idea)

_Add here._
