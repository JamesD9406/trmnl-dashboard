# Next Step Ideas

A running list of ideas for future versions of the TRMNL dashboard. Nothing here
is committed to — it's a scratchpad for things worth considering.

---

## 1. User-configurable teams — ✅ Implemented

**Goal:** let people pick their own teams instead of the hardcoded Liverpool /
Toronto / Buffalo list, so the repo is genuinely reusable as a template.

Done via a committed `teams.json` (see [SETUP.md](SETUP.md) → "Making it
yours"). `collect_games()` loads it, dispatches per entry on `provider`
(`espn` or `football-data`), and skips-with-a-warning any entry that errors
instead of crashing the whole run. `FOOTBALL_DATA_API_KEY` is only required
if a `football-data` entry is present.

**Still just a sketch, not built:** a `TEAMS_JSON` GitHub repo variable so
config could be done entirely through the GitHub web UI without editing a
file. Low priority — editing a committed file works fine for two people.

---

## 2. Generic/config-driven API provider

**Goal:** today, adding a team whose sport uses a provider other than ESPN or
football-data.org (e.g. BBC Sport for cricket, or any other API) still
requires writing a small Python function — see [SETUP.md](SETUP.md) → "Using
a provider that isn't built in yet" for exactly what that involves. This idea
is about removing that requirement so `teams.json` alone is enough, for
anyone willing to describe the API's shape in JSON.

**Why it's a bigger lift than it sounds:** every sports API differs in ways
that are easy to parameterize individually but awkward to cover generically
all at once — URL structure, auth scheme (no auth / header token / query-param
key), how "upcoming" is determined (status strings, date filtering), and
where the team/opponent/kickoff fields live in a differently-nested response
each time.

**Sketch:**

- A third `provider: "generic"` entry shape, something like:
  ```json
  {
    "provider": "generic",
    "name": "England Cricket",
    "url": "https://api.example.com/teams/{team_id}/fixtures",
    "auth": { "type": "header", "header": "X-Api-Key", "env_var": "CRICKET_API_KEY" },
    "events_path": "fixtures",
    "status_path": "status",
    "status_upcoming_value": "scheduled",
    "kickoff_path": "start_time",
    "opponent_path": "opponent.name",
    "home_away_path": "venue"
  }
  ```
  — a dotted-path mini-language (think a tiny subset of JSONPath) for
  `events_path`/`status_path`/`kickoff_path`/`opponent_path` so a generic
  Python function can walk an arbitrary response shape without new code per
  API.
- A new `get_generic_next_game(entry)` function in `fetch_and_push.py` that:
  substitutes any `{placeholder}` fields in `url` from the entry, applies the
  configured `auth`, fetches, walks `events_path` to get the event list,
  filters by `status_path == status_upcoming_value`, sorts by `kickoff_path`,
  and pulls `opponent_path` for the opponent name — returning the same
  `{"team", "opponent", "kickoff_dt"}` shape every other provider returns.
- `load_teams()` needs new validation for the `generic` shape (required vs.
  optional sub-fields, valid `auth.type` values).
- Error handling follows the same skip-and-continue pattern already in
  `collect_games()` — a malformed path expression or unexpected response
  shape for one `generic` entry warns and drops that team, same as today.
- Worth deciding upfront: is a tiny dotted-path walker (split on `.`, index
  into dicts/lists) enough, or do we actually want a dependency like
  `jsonpath-ng`? A hand-rolled walker covers the common "list of events, each
  a flat-ish dict" shape most sports APIs use; something more deeply nested
  or requiring filters (`events[?status=='scheduled']`) would need a real
  JSONPath library — decide based on what provider actually prompts this.
