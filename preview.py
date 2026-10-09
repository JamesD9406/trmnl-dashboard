"""
Render template.html the way TRMNL would, into a standalone preview.html you can
open in a browser. Lets you eyeball the layout (and how much spare room you have
for more plugins) before the device is set up.

Usage:
  python preview.py            # real data if creds are present, else sample data
  python preview.py --fake     # always use sample data, no network calls
  python preview.py --no-open  # write preview.html but don't open a browser

The device is an 800x480 1-bit e-ink panel. TRMNL's own framework CSS/JS
(loaded from trmnl.com) does the real rendering, so this is a faithful preview
of spacing and sizing, just in colour instead of grayscale.
"""

import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from liquid import Template
except ImportError:
    sys.exit(
        "preview.py needs python-liquid. Run:  pip install -r requirements.txt"
    )

import fetch_and_push as app

HERE = Path(__file__).parent
TEMPLATE = HERE / "template.html"
OUTPUT = HERE / "preview.html"

SAMPLE = {
    "updated_at": "9:05 AM",
    "weather_temp": 18,
    "weather_feels_like": 17,
    "weather_humidity": 64,
    "weather_icon": "partly",
    "temp_unit_short": "C",
    "today_hi": 19,
    "today_lo": 11,
    "sunrise_time": "6:52 AM",
    "sunset_time": "7:56 PM",
    "forecast": [
        {"day": "Mon", "hi": 19, "lo": 11, "icon": "partly"},
        {"day": "Tue", "hi": 22, "lo": 12, "icon": "clear"},
        {"day": "Wed", "hi": 17, "lo": 13, "icon": "rain"},
        {"day": "Thu", "hi": 16, "lo": 10, "icon": "cloudy"},
        {"day": "Fri", "hi": 18, "lo": 9, "icon": "storm"},
    ],
    "hourly": [
        {"hour": "10 AM", "temp": 18, "icon": "partly"},
        {"hour": "11 AM", "temp": 19, "icon": "partly"},
        {"hour": "12 PM", "temp": 21, "icon": "clear"},
        {"hour": "1 PM", "temp": 22, "icon": "clear"},
        {"hour": "2 PM", "temp": 22, "icon": "cloudy"},
        {"hour": "3 PM", "temp": 21, "icon": "rain"},
    ],
    # Already sorted soonest-first, the way collect_games() emits it. The Blue
    # Jays are absent here to show an out-of-season team dropping off.
    "sports_horizon_days": 30,
    "games": [
        {"team": "Liverpool FC", "opponent": "vs Everton", "kickoff": "Sat Sep 13, 12:30 PM"},
        {"team": "Buffalo Bills", "opponent": "@ Miami Dolphins", "kickoff": "Sun Sep 14, 1:00 PM"},
        {"team": "Toronto Maple Leafs", "opponent": "vs Montreal Canadiens", "kickoff": "Mon Sep 29, 7:00 PM"},
        {"team": "Toronto Raptors", "opponent": "vs Miami Heat", "kickoff": "Fri Oct 3, 7:00 PM"},
    ],
}

# TRMNL's real framework assets. `screen--og screen--1bit` = 800x480, 1-bit panel.
PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>TRMNL dashboard preview</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap">
<link rel="stylesheet" href="https://trmnl.com/css/latest/plugins.css">
<script src="https://trmnl.com/js/latest/plugins.js"></script>
<style>
  body {{ background:#3a3a3a; margin:0; padding:32px; font-family:Inter,system-ui,sans-serif;
         display:flex; flex-direction:column; align-items:center; gap:14px; }}
  .frame {{ width:800px; height:480px; background:#fff; box-shadow:0 8px 40px rgba(0,0,0,.55);
            outline:1px solid #000; overflow:hidden; }}
  .caption {{ color:#bbb; font-size:12px; }}
  .caption b {{ color:#fff; }}
</style>
</head>
<body class="environment trmnl">
  <div class="caption">800 &times; 480 &mdash; TRMNL OG &mdash; data: <b>{source}</b></div>
  <div class="frame">
    <div class="screen screen--og screen--1bit">
      <div class="view view--full">
{body}
      </div>
    </div>
  </div>
  <div class="caption">Rendered with TRMNL's live framework CSS. On the device this is 1-bit black &amp; white.</div>
</body>
</html>
"""


def get_variables():
    if "--fake" in sys.argv:
        return SAMPLE, "sample (--fake)"

    key = os.environ.get("FOOTBALL_DATA_API_KEY")
    lat = os.environ.get("WEATHER_LAT")
    lon = os.environ.get("WEATHER_LON")
    if not (key and lat and lon):
        print("No FOOTBALL_DATA_API_KEY / WEATHER_LAT / WEATHER_LON set — using sample data.")
        return SAMPLE, "sample (no creds)"

    try:
        return app.build_merge_variables(key, lat, lon), "live"
    except Exception as exc:  # network hiccup, rate limit, offseason, etc.
        print(f"Live fetch failed ({exc}); falling back to sample data.")
        return SAMPLE, "sample (fetch failed)"


def trmnl_context():
    """Mimic the `trmnl.*` object TRMNL injects into every plugin render, so the
    Liquid-rendered date in template.html resolves during local preview too.
    The template gets "now" from Liquid itself; it only needs the tz offset."""
    now = datetime.now(ZoneInfo(app.TIMEZONE))
    return {"user": {"utc_offset": int(now.utcoffset().total_seconds())}}


def main():
    variables, source = get_variables()
    variables = {**variables, "trmnl": trmnl_context()}
    rendered = Template(TEMPLATE.read_text(encoding="utf-8")).render(**variables)
    OUTPUT.write_text(PAGE.format(body=rendered, source=source), encoding="utf-8")
    print(f"Wrote {OUTPUT}  (data: {source})")

    if "--no-open" not in sys.argv:
        webbrowser.open(OUTPUT.as_uri())


if __name__ == "__main__":
    main()
