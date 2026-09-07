"""
Gathers time/date, weather, sunrise/sunset, Liverpool FC's next match, and the
Buffalo Bills' next game, then pushes them as merge_variables to a TRMNL
private plugin via its webhook URL.

Required environment variables:
  TRMNL_WEBHOOK_URL      https://usetrmnl.com/api/custom_plugins/<UUID>
  FOOTBALL_DATA_API_KEY  free key from https://www.football-data.org/client/register
  WEATHER_LAT            latitude for weather/sunrise-sunset, e.g. "53.4084"
  WEATHER_LON            longitude for weather/sunrise-sunset, e.g. "-2.9916"

Optional:
  TIMEZONE   IANA tz name for displayed times, default "Europe/London"
  TEMP_UNIT  "celsius" or "fahrenheit", default "celsius"
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

try:
    # Optional: load a local .env for convenience. In GitHub Actions the values
    # come from the workflow env block, so python-dotenv isn't needed there.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

TIMEZONE = os.environ.get("TIMEZONE", "Europe/London")
TEMP_UNIT = os.environ.get("TEMP_UNIT", "celsius")
TEMP_UNIT_SHORT = "F" if TEMP_UNIT == "fahrenheit" else "C"

# A team whose next game is further away than this many days is treated as
# "out of season" and dropped from the Sportsball panel, rather than showing a
# fixture months out. In-season schedule gaps (byes, international breaks) are
# well under 30 days for every league here.
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


def fmt_full_date(dt):
    """e.g. 'Saturday, September 6'."""
    return f"{dt.strftime('%A, %B')} {dt.day}"


def fmt_kickoff(iso_or_dt, tz_name=TIMEZONE):
    """e.g. 'Sat Sep 6, 3:00 PM'."""
    local = to_local(iso_or_dt, tz_name)
    return f"{fmt_date(local)}, {fmt_time(local)}"


def get_weather_and_sun(lat, lon):
    resp = requests.get(
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
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
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

    # Next 6 whole hours. Open-Meteo hourly times are naive local wall-clock
    # strings (we passed `timezone`), so compare against a naive local now.
    now_naive = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    hourly = []
    for t, temp, code in zip(
        hourly_src["time"], hourly_src["temperature_2m"], hourly_src["weather_code"]
    ):
        slot = datetime.fromisoformat(t)
        if slot <= now_naive:
            continue
        hourly.append({"hour": fmt_hour(slot), "temp": round(temp), "icon": wmo_icon(code)})
        if len(hourly) == 6:
            break

    return {
        "weather_temp": round(current["temperature_2m"]),
        "weather_feels_like": round(current["apparent_temperature"]),
        "weather_humidity": current["relative_humidity_2m"],
        "weather_description": WMO_WEATHER_CODES.get(current["weather_code"], "Unknown"),
        "weather_icon": wmo_icon(current["weather_code"]),
        "temp_unit_short": TEMP_UNIT_SHORT,
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


def get_lfc_next_match(api_key):
    """Liverpool's next fixture as {team, opponent, kickoff_dt}, or None."""
    teams = football_data_get(
        "https://api.football-data.org/v4/competitions/PL/teams", api_key
    )["teams"]
    liverpool = next((t for t in teams if "liverpool" in t["name"].lower()), None)
    if not liverpool:
        fail("could not find Liverpool FC in PL teams list from football-data.org")

    today = datetime.now(timezone.utc).date()
    matches = football_data_get(
        f"https://api.football-data.org/v4/teams/{liverpool['id']}/matches",
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
    is_home = match["homeTeam"]["id"] == liverpool["id"]
    opponent = match["awayTeam"]["name"] if is_home else match["homeTeam"]["name"]
    return {
        "team": "Liverpool FC",
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
    resp = requests.get(
        f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}"
        f"/teams/{team_abbr.lower()}/schedule",
        timeout=15,
    )
    resp.raise_for_status()
    events = resp.json().get("events", [])

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
    team_side = next(c for c in competition["competitors"] if c["team"]["abbreviation"] == team_abbr)
    opp_side = next(c for c in competition["competitors"] if c["team"]["abbreviation"] != team_abbr)
    return {
        "team": team_name,
        "opponent": f"{'vs' if team_side.get('homeAway') == 'home' else '@'} {opp_side['team']['displayName']}",
        "kickoff_dt": kickoff_dt(game),
    }


def collect_games(football_data_key):
    """Every followed team's next game, soonest first, dropping teams whose
    next game is beyond SPORTS_HORIZON_DAYS (i.e. their season is over)."""
    records = [
        get_lfc_next_match(football_data_key),
        get_espn_next_game("baseball/mlb", "TOR", "Toronto Blue Jays"),
        get_espn_next_game("hockey/nhl", "TOR", "Toronto Maple Leafs"),
        get_espn_next_game("basketball/nba", "TOR", "Toronto Raptors"),
        get_espn_next_game("football/nfl", "BUF", "Buffalo Bills"),
    ]
    horizon = datetime.now(timezone.utc) + timedelta(days=SPORTS_HORIZON_DAYS)
    games = sorted(
        (r for r in records if r and r["kickoff_dt"] <= horizon),
        key=lambda r: r["kickoff_dt"],
    )
    return {
        "sports_horizon_days": SPORTS_HORIZON_DAYS,
        "games": [
            {"team": g["team"], "opponent": g["opponent"], "kickoff": fmt_kickoff(g["kickoff_dt"])}
            for g in games
        ],
    }


def build_merge_variables(football_data_key, lat, lon):
    """Gather every variable the template interpolates. Shared with preview.py."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    return {
        "current_time": fmt_time(now),
        "current_date": fmt_full_date(now),
        "updated_at": fmt_time(now),
        **get_weather_and_sun(lat, lon),
        **collect_games(football_data_key),
    }


def main():
    webhook_url = get_env("TRMNL_WEBHOOK_URL")
    football_data_key = get_env("FOOTBALL_DATA_API_KEY")
    lat = get_env("WEATHER_LAT")
    lon = get_env("WEATHER_LON")

    merge_variables = build_merge_variables(football_data_key, lat, lon)

    resp = requests.post(webhook_url, json={"merge_variables": merge_variables}, timeout=15)
    resp.raise_for_status()
    print("Pushed to TRMNL:", merge_variables)


if __name__ == "__main__":
    main()
