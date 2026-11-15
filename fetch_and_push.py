"""
Gathers time/date, weather, sunrise/sunset, and each team's next game (as
configured in teams.json), then pushes them as merge_variables to a TRMNL
private plugin via its webhook URL.

Required environment variables:
  TRMNL_WEBHOOK_URL      https://usetrmnl.com/api/custom_plugins/<UUID>
  WEATHER_LAT            latitude for weather/sunrise-sunset, e.g. "53.4084"
  WEATHER_LON            longitude for weather/sunrise-sunset, e.g. "-2.9916"
  FOOTBALL_DATA_API_KEY  free key from https://www.football-data.org/client/register
                         — only required if teams.json has a "football-data"
                         provider entry; not needed for ESPN-only setups.

Optional:
  TIMEZONE   IANA tz name for displayed times, default "Europe/London"
  TEMP_UNIT  "celsius" or "fahrenheit", default "celsius"

Teams are configured in teams.json (see SETUP.md) rather than hardcoded here.
"""

import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

TIMEZONE = os.environ.get("TIMEZONE", "Europe/London")
TEMP_UNIT = os.environ.get("TEMP_UNIT", "celsius")
TEMP_UNIT_SHORT = "F" if TEMP_UNIT == "fahrenheit" else "C"

SPORTS_HORIZON_DAYS = int(os.environ.get("SPORTS_HORIZON_DAYS") or "30")

WMO_WEATHER_CODES = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain",
    67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm w/ hail", 99: "Severe thunderstorm w/ hail",
}

# WMO code -> icon keyword the template's {% case %} block draws an SVG for.
WMO_ICONS = {
    0: "clear", 1: "partly", 2: "partly", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain", 56: "rain", 57: "rain",
    61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "rain", 81: "rain", 82: "rain",
    85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}


def make_session():
    """A requests session that retries transient failures.

    GitHub-hosted runners share IPs with many other projects calling the same
    free APIs (Open-Meteo especially), so timeouts, 429s, 5xxs and dropped TLS
    handshakes are routine. Up to 3 retries with backoff (0s, 4s, 8s), honouring
    Retry-After on 429/503. Only idempotent methods (GET) retry on read
    timeouts/bad statuses; the webhook POST still retries on connect failures.
    """
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,  # hand back the last response; raise_for_status() reports it
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


HTTP = make_session()


def get_json(url, attempts=3, **kwargs):
    """GET JSON via the retrying session. Also retries when a 200 comes back
    with a non-JSON body (an overloaded upstream occasionally does this)."""
    for attempt in range(1, attempts + 1):
        resp = HTTP.get(url, timeout=15, **kwargs)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            if attempt == attempts:
                raise
            print(f"Non-JSON response from {url}; retrying ({attempt}/{attempts - 1})")
            time.sleep(5)


def wmo_icon(code):
    return WMO_ICONS.get(code, "cloudy")


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def get_env(name, required=True, default=None):
    value = os.environ.get(name, default)
    if required and not value:
        fail(f"missing required environment variable {name}")
    return value


def load_teams(path="teams.json"):
    """Load and validate the user-editable team list.

    Structural problems here (missing file, bad JSON, bad shape) are config
    errors, not per-team runtime errors, so they're fatal via fail() — unlike
    a single team's API call failing later, which is only ever skipped.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        fail(f"{path} not found — see SETUP.md for how to configure teams")
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")

    if not isinstance(raw, list) or not raw:
        fail(f"{path} must be a non-empty JSON array of team objects")

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            fail(f"{path}[{i}] must be an object")
        provider = entry.get("provider")
        if provider not in ("espn", "football-data"):
            fail(f'{path}[{i}]: "provider" must be "espn" or "football-data", got {provider!r}')
        if not entry.get("name"):
            fail(f'{path}[{i}]: missing required field "name"')
        if provider == "espn":
            for field in ("sport", "abbr"):
                if not entry.get(field):
                    fail(f'{path}[{i}] ({entry["name"]}): missing required field "{field}"')
        else:  # football-data
            for field in ("competition", "match"):
                if not entry.get(field):
                    fail(f'{path}[{i}] ({entry["name"]}): missing required field "{field}"')

    return raw


def to_local(iso_or_dt, tz_name=TIMEZONE):
    """Parse an ISO string (or pass through a datetime) and convert to tz_name."""
    if isinstance(iso_or_dt, str):
        dt = datetime.fromisoformat(iso_or_dt.replace("Z", "+00:00"))
    else:
        dt = iso_or_dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


def fmt_time(dt):
    """e.g. '9:05 AM' — no leading-zero hour, portable across OSes."""
    hour12 = ((dt.hour + 11) % 12) + 1
    return f"{hour12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def fmt_hour(dt):
    """e.g. '3 PM' — hour only, for the hourly strip."""
    hour12 = ((dt.hour + 11) % 12) + 1
    return f"{hour12} {'AM' if dt.hour < 12 else 'PM'}"


def fmt_date(dt):
    """e.g. 'Sat Sep 6'."""
    return f"{dt.strftime('%a %b')} {dt.day}"


def fmt_kickoff(iso_or_dt, tz_name=TIMEZONE):
    """e.g. 'Sat Sep 6, 3:00 PM'."""
    local = to_local(iso_or_dt, tz_name)
    return f"{fmt_date(local)}, {fmt_time(local)}"


WET_ICONS = {"rain": "Rain", "snow": "Snow", "storm": "Storms"}
HEADS_UP_HOURS = 12
TEMP_SWING_ALERT = 5  # degrees between today's and tomorrow's high


def heads_up(current_icon, upcoming, today_hi, tomorrow_hi):
    """One short line for the title bar: the most useful thing to know that
    the rest of the screen doesn't already say outright.

    `upcoming` is [(datetime, icon)] for the next HEADS_UP_HOURS hours.
    Priority: rain/snow/storms starting or stopping soon, then a big
    temperature swing tomorrow, then a reassuring "dry" note.
    Returns (text, icon) — icon is a weather keyword, or "" for none."""
    if current_icon in WET_ICONS:
        dry = next((t for t, icon in upcoming if icon not in WET_ICONS), None)
        word = WET_ICONS[current_icon]
        if dry:
            return f"{word} until {fmt_hour(dry)}", current_icon
        return f"{word} for the next {HEADS_UP_HOURS} hrs", current_icon

    wet = next(((t, icon) for t, icon in upcoming if icon in WET_ICONS), None)
    if wet:
        return f"{WET_ICONS[wet[1]]} from {fmt_hour(wet[0])}", wet[1]

    swing = tomorrow_hi - today_hi
    if abs(swing) >= TEMP_SWING_ALERT:
        return f"Tomorrow {abs(swing)}° {'warmer' if swing > 0 else 'colder'}", ""

    return f"Dry for the next {HEADS_UP_HOURS} hrs", ""


class WeatherUnavailable(Exception):
    """Every weather source failed. main() skips the push rather than failing,
    so the device simply keeps showing its last good data."""


WEATHER_ERRORS = (requests.RequestException, ValueError, KeyError, IndexError, TypeError)


def fetch_open_meteo(lat, lon):
    """Primary source. Returns {current, hourly, daily} in Open-Meteo's own
    shape, which is also the shape fetch_met_norway() normalises to."""
    data = get_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code",
            "hourly": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
            "temperature_unit": TEMP_UNIT,
            "timezone": TIMEZONE,
            "forecast_days": 6,  # today + next 5
        },
    )
    return {"current": data["current"], "hourly": data["hourly"], "daily": data["daily"]}


# MET Norway (api.met.no): free, keyless, separate infrastructure from
# Open-Meteo. Its terms require a User-Agent identifying the app.
MET_HEADERS = {"User-Agent": "trmnl-dashboard/1.0 https://github.com/JamesD9406/trmnl-dashboard"}


def met_symbol_to_wmo(symbol):
    """Map a MET symbol_code (e.g. 'lightrainshowers_day') to the nearest WMO
    code, so descriptions and icons reuse the Open-Meteo tables above. Rule
    based rather than a lookup, since MET's list includes misspelled codes
    like 'lightssleetshowersandthunder'."""
    base = symbol.split("_")[0]
    if "thunder" in base:
        return 95
    fixed = {"clearsky": 0, "fair": 1, "partlycloudy": 2, "cloudy": 3, "fog": 45}
    if base in fixed:
        return fixed[base]
    level = 0 if "light" in base else 2 if "heavy" in base else 1
    showers = "showers" in base
    if "snow" in base:
        return (85, 85, 86)[level] if showers else (71, 73, 75)[level]
    if "sleet" in base:
        return 66 if level == 0 else 67  # closest WMO: freezing rain
    return (80, 81, 82)[level] if showers else (61, 63, 65)[level]


def met_symbol(data, *periods):
    """First available symbol_code among the given forecast periods."""
    for period in periods:
        if period in data:
            return data[period]["summary"]["symbol_code"]
    raise KeyError(f"no symbol_code in any of {periods}")


def apparent_temperature(temp_c, humidity, wind_ms):
    """Australian apparent temperature (Steadman), the formula Open-Meteo
    uses for its own `apparent_temperature`, so the fallback matches."""
    vapour = humidity / 100 * 6.105 * math.exp(17.27 * temp_c / (237.7 + temp_c))
    return temp_c + 0.33 * vapour - 0.70 * wind_ms - 4.00


def fetch_met_norway(lat, lon):
    """Fallback source, normalised to fetch_open_meteo()'s shape.

    Differences from Open-Meteo: hourly steps only run ~2.5 days ahead (then
    6-hourly), so later days' hi/lo come from fewer samples; and today's hi/lo
    covers only the hours remaining, not the whole day."""
    tz = ZoneInfo(TIMEZONE)
    lat, lon = round(float(lat), 4), round(float(lon), 4)  # MET asks for <= 4 decimals

    def unit(celsius):  # MET is always Celsius
        return celsius * 9 / 5 + 32 if TEMP_UNIT == "fahrenheit" else celsius

    series = get_json(
        "https://api.met.no/weatherapi/locationforecast/2.0/compact",
        params={"lat": lat, "lon": lon},
        headers=MET_HEADERS,
    )["properties"]["timeseries"]
    # (naive local time, entry data), matching Open-Meteo's local wall-clock times.
    rows = [(to_local(e["time"]).replace(tzinfo=None), e["data"]) for e in series]

    now_data = rows[0][1]
    now = now_data["instant"]["details"]
    current = {
        "temperature_2m": unit(now["air_temperature"]),
        "apparent_temperature": unit(
            apparent_temperature(now["air_temperature"], now["relative_humidity"], now.get("wind_speed", 0))
        ),
        "relative_humidity_2m": round(now["relative_humidity"]),
        "weather_code": met_symbol_to_wmo(met_symbol(now_data, "next_1_hours", "next_6_hours")),
    }

    hourly_rows = [(t, d) for t, d in rows if "next_1_hours" in d]
    hourly = {
        "time": [t.isoformat() for t, _ in hourly_rows],
        "temperature_2m": [unit(d["instant"]["details"]["air_temperature"]) for _, d in hourly_rows],
        "weather_code": [met_symbol_to_wmo(met_symbol(d, "next_1_hours")) for _, d in hourly_rows],
    }

    dates = sorted({t.date() for t, _ in rows})[:6]  # today + next 5
    daily = {"time": [], "weather_code": [], "temperature_2m_max": [], "temperature_2m_min": []}
    for day in dates:
        day_rows = [(t, d) for t, d in rows if t.date() == day]
        temps = [unit(d["instant"]["details"]["air_temperature"]) for _, d in day_rows]
        # The day's icon: the forecast period starting closest to midday.
        midday = datetime.combine(day, datetime.min.time()).replace(hour=12)
        _, noon_data = min(day_rows, key=lambda r: abs(r[0] - midday))
        daily["time"].append(day.isoformat())
        daily["weather_code"].append(
            met_symbol_to_wmo(met_symbol(noon_data, "next_6_hours", "next_12_hours", "next_1_hours"))
        )
        daily["temperature_2m_max"].append(max(temps))
        daily["temperature_2m_min"].append(min(temps))

    # Sunrise/sunset live on a separate endpoint; only today's are displayed.
    offset_min = int(datetime.now(tz).utcoffset().total_seconds() // 60)
    sign = "+" if offset_min >= 0 else "-"
    sun = get_json(
        "https://api.met.no/weatherapi/sunrise/3.0/sun",
        params={
            "lat": lat,
            "lon": lon,
            "date": dates[0].isoformat(),
            "offset": f"{sign}{abs(offset_min) // 60:02d}:{abs(offset_min) % 60:02d}",
        },
        headers=MET_HEADERS,
    )["properties"]
    daily["sunrise"], daily["sunset"] = (
        [datetime.fromisoformat(sun[key]["time"]).astimezone(tz).replace(tzinfo=None).isoformat()]
        for key in ("sunrise", "sunset")
    )

    return {"current": current, "hourly": hourly, "daily": daily}


def fetch_weather(lat, lon):
    """Open-Meteo, falling back to MET Norway. Raises WeatherUnavailable if both fail."""
    try:
        return fetch_open_meteo(lat, lon)
    except WEATHER_ERRORS as exc:
        print(f"WARNING: Open-Meteo failed ({exc}); falling back to MET Norway", file=sys.stderr)
    try:
        data = fetch_met_norway(lat, lon)
    except WEATHER_ERRORS as exc:
        raise WeatherUnavailable(f"Open-Meteo and MET Norway both failed; last error: {exc}") from exc
    print("Weather from MET Norway (fallback)")
    return data


def get_weather_and_sun(lat, lon):
    data = fetch_weather(lat, lon)
    current = data["current"]
    daily = data["daily"]
    hourly_src = data["hourly"]

    # daily[...][0] is today; [1:] are the upcoming days for the forecast strip.
    forecast = [
        {
            "day": datetime.fromisoformat(daily["time"][i]).strftime("%a"),
            "hi": round(daily["temperature_2m_max"][i]),
            "lo": round(daily["temperature_2m_min"][i]),
            "icon": wmo_icon(daily["weather_code"][i]),
        }
        for i in range(1, len(daily["time"]))
    ]

    # Upcoming whole hours. Open-Meteo hourly times are naive local wall-clock
    # strings (we passed `timezone`), so compare against a naive local now.
    # The strip shows the next 6; the title-bar heads-up looks further ahead.
    now_naive = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    upcoming = [
        (datetime.fromisoformat(t), round(temp), wmo_icon(code))
        for t, temp, code in zip(
            hourly_src["time"], hourly_src["temperature_2m"], hourly_src["weather_code"]
        )
        if datetime.fromisoformat(t) > now_naive
    ][:HEADS_UP_HOURS]
    hourly = [
        {"hour": fmt_hour(slot), "temp": temp, "icon": icon}
        for slot, temp, icon in upcoming[:6]
    ]

    alert_text, alert_icon = heads_up(
        wmo_icon(current["weather_code"]),
        [(slot, icon) for slot, _, icon in upcoming],
        round(daily["temperature_2m_max"][0]),
        round(daily["temperature_2m_max"][1]),
    )

    return {
        "heads_up": alert_text,
        "heads_up_icon": alert_icon,
        "weather_temp": round(current["temperature_2m"]),
        "weather_feels_like": round(current["apparent_temperature"]),
        "weather_humidity": current["relative_humidity_2m"],
        "weather_description": WMO_WEATHER_CODES.get(current["weather_code"], "Unknown"),
        "weather_icon": wmo_icon(current["weather_code"]),
        "temp_unit_short": TEMP_UNIT_SHORT,
        # daily[...][0] is today; the `forecast` strip above starts at [1].
        "today_hi": round(daily["temperature_2m_max"][0]),
        "today_lo": round(daily["temperature_2m_min"][0]),
        # Open-Meteo already returns these in the requested `timezone`, as naive
        # local wall-clock strings — parse directly, no further tz conversion.
        "sunrise_time": fmt_time(datetime.fromisoformat(daily["sunrise"][0])),
        "sunset_time": fmt_time(datetime.fromisoformat(daily["sunset"][0])),
        "forecast": forecast,
        "hourly": hourly,
    }


def football_data_get(url, api_key, params=None, _attempt=1):
    """GET from football-data.org, honouring its rate-limit response headers.

    Free tier caps requests per minute and advertises the state on every
    response: `X-Requests-Available-Minute` (how many you have left) and
    `X-RequestCounter-Reset` (seconds until the window resets). On a 429 the
    body says how long to wait. We back off on 429 (once), then pause if the
    remaining-request count has hit zero so the next call doesn't trip it.
    """
    resp = requests.get(url, headers={"X-Auth-Token": api_key}, params=params, timeout=15)

    if resp.status_code == 429 and _attempt <= 2:
        reset = resp.headers.get("X-RequestCounter-Reset")
        wait = int(reset) if reset and reset.isdigit() else 60
        print(f"football-data.org rate-limited; waiting {wait}s then retrying")
        time.sleep(wait + 1)
        return football_data_get(url, api_key, params, _attempt + 1)

    resp.raise_for_status()

    remaining = resp.headers.get("X-Requests-Available-Minute")
    reset = resp.headers.get("X-RequestCounter-Reset")
    if remaining is not None and remaining.isdigit() and int(remaining) <= 0:
        wait = int(reset) if reset and reset.isdigit() else 60
        print(f"football-data.org minute quota exhausted; pausing {wait}s")
        time.sleep(wait + 1)

    return resp.json()


def get_football_data_next_match(api_key, competition, name_query, display_name):
    """A football-data.org team's next fixture as {team, opponent, kickoff_dt},
    or None. `name_query` is matched case-insensitively as a substring against
    team names in `competition` (e.g. "liverpool" against competition "PL")."""
    teams = football_data_get(
        f"https://api.football-data.org/v4/competitions/{competition}/teams", api_key
    )["teams"]
    team = next((t for t in teams if name_query in t["name"].lower()), None)
    if not team:
        print(
            f"WARNING: no team matching {name_query!r} found in {competition} teams list",
            file=sys.stderr,
        )
        return None

    today = datetime.now(timezone.utc).date()
    matches = football_data_get(
        f"https://api.football-data.org/v4/teams/{team['id']}/matches",
        api_key,
        params={
            "status": "SCHEDULED",
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=SPORTS_HORIZON_DAYS + 10)).isoformat(),
        },
    )["matches"]
    if not matches:
        return None

    match = min(matches, key=lambda m: m["utcDate"])
    is_home = match["homeTeam"]["id"] == team["id"]
    opponent = match["awayTeam"]["name"] if is_home else match["homeTeam"]["name"]
    return {
        "team": display_name,
        "opponent": f"{'vs' if is_home else '@'} {opponent}",
        "kickoff_dt": datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")),
    }


def get_espn_next_game(sport_path, team_abbr, team_name):
    """Next game for an ESPN team as {team, opponent, kickoff_dt}, or None.

    `sport_path` e.g. "football/nfl", "hockey/nhl", "baseball/mlb"; `team_abbr`
    is ESPN's abbreviation (e.g. "BUF", "TOR").

    We keep only games whose status is "pre" (scheduled, not started) and whose
    start time is still in the future — postponed/finished games report other
    states, and postponed ones in particular keep a stale future-looking flag.
    """
    events = get_json(
        f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}"
        f"/teams/{team_abbr.lower()}/schedule",
    ).get("events", [])

    now = datetime.now(timezone.utc)

    def kickoff_dt(event):
        return datetime.fromisoformat(event["date"].replace("Z", "+00:00"))

    upcoming = [
        e for e in events
        if e.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("state") == "pre"
        and kickoff_dt(e) >= now
    ]
    if not upcoming:
        return None

    game = min(upcoming, key=kickoff_dt)
    competition = game["competitions"][0]
    team_side = next(
        (c for c in competition["competitors"]
         if c["team"]["abbreviation"].upper() == team_abbr.upper()),
        None,
    )
    if team_side is None:
        print(
            f"WARNING: abbreviation {team_abbr!r} not found among competitors for {team_name}",
            file=sys.stderr,
        )
        return None
    opp_side = next(c for c in competition["competitors"] if c is not team_side)
    return {
        "team": team_name,
        "opponent": f"{'vs' if team_side.get('homeAway') == 'home' else '@'} {opp_side['team']['displayName']}",
        "kickoff_dt": kickoff_dt(game),
    }


def collect_games(football_data_key, teams_path="teams.json"):
    """Every followed team's next game, soonest first, dropping teams whose
    next game is beyond SPORTS_HORIZON_DAYS (i.e. their season is over).

    Teams come from teams.json. A single team's error (network failure, bad
    abbreviation, etc.) is logged as a warning and skipped — it does not
    abort the run, so one bad entry can't block everyone else's games from
    being pushed."""
    teams = load_teams(teams_path)
    records = []
    for entry in teams:
        try:
            if entry["provider"] == "espn":
                record = get_espn_next_game(entry["sport"], entry["abbr"], entry["name"])
            else:  # football-data
                record = get_football_data_next_match(
                    football_data_key, entry["competition"], entry["match"], entry["name"]
                )
            records.append(record)
        except requests.RequestException as exc:
            print(f"WARNING: skipping {entry['name']}: request failed: {exc}", file=sys.stderr)
        except (KeyError, ValueError) as exc:
            print(f"WARNING: skipping {entry['name']}: unexpected response shape: {exc}", file=sys.stderr)

    horizon = datetime.now(timezone.utc) + timedelta(days=SPORTS_HORIZON_DAYS)
    games = sorted(
        (r for r in records if r and r["kickoff_dt"] <= horizon),
        key=lambda r: r["kickoff_dt"],
    )
    return {
        "sports_horizon_days": SPORTS_HORIZON_DAYS,
        "games": [
            {
                "team": g["team"],
                "opponent": g["opponent"],
                "kickoff": fmt_kickoff(g["kickoff_dt"]),
                # The template compares these against its render clock to
                # show "Today 7:00 PM" / "Tomorrow 7:00 PM".
                "kickoff_ts": int(g["kickoff_dt"].timestamp()),
                "kickoff_time": fmt_time(to_local(g["kickoff_dt"])),
            }
            for g in games
        ],
    }


def build_merge_variables(football_data_key, lat, lon):
    """Gather every variable the template interpolates. Shared with preview.py."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    return {
        # The big date in the template is rendered by Liquid from TRMNL's render
        # clock, not from here, so it stays correct between pushes. `updated_at`
        # is still stamped here — it's meant to show data freshness.
        "updated_at": fmt_time(now),
        **get_weather_and_sun(lat, lon),
        **collect_games(football_data_key),
    }


def main():
    webhook_url = get_env("TRMNL_WEBHOOK_URL")
    lat = get_env("WEATHER_LAT")
    lon = get_env("WEATHER_LON")

    teams = load_teams()
    needs_football_data = any(t["provider"] == "football-data" for t in teams)
    football_data_key = get_env("FOOTBALL_DATA_API_KEY", required=needs_football_data)

    try:
        merge_variables = build_merge_variables(football_data_key, lat, lon)
    except WeatherUnavailable as exc:
        # Not worth a red run: skipping the push leaves the device showing its
        # last good data, and the next scheduled run will try again.
        print(f"::warning::Skipped push, weather unavailable: {exc}")
        return

    resp = HTTP.post(webhook_url, json={"merge_variables": merge_variables}, timeout=15)
    resp.raise_for_status()
    print("Pushed to TRMNL:", merge_variables)


if __name__ == "__main__":
    main()
