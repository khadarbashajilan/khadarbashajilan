
import datetime as dt
import json
import math
import os
import pathlib
import urllib.request

TOKEN = os.environ["STATS_TOKEN"]
USERNAME = os.environ["GITHUB_USERNAME"]

today = dt.datetime.now(dt.timezone.utc).date()
start = today - dt.timedelta(days=30)

OUTPUT = pathlib.Path("profile")
OUTPUT.mkdir(exist_ok=True)

WIDTH, HEIGHT = 960, 280
LEFT, RIGHT = 12, 12
TOP, BOTTOM = 12, 238

DARK = {
    "bg": "#0d1117",
    "line": "#58a6ff",
    "point": "#79c0ff",
}

LIGHT = {
    "bg": "#ffffff",
    "line": "#0969da",
    "point": "#0969da",
}

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
      restrictedContributionsCount
    }
  }
}
"""

payload = {
    "query": QUERY,
    "variables": {
        "login": USERNAME,
        "from": f"{start.isoformat()}T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z",
    },
}

request = urllib.request.Request(
    "https://api.github.com/graphql",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Activity-Graph",
    },
)

with urllib.request.urlopen(request, timeout=30) as response:
    result = json.loads(response.read())

if result.get("errors"):
    raise RuntimeError(result["errors"])

user = result["data"]["user"]

if not user:
    raise RuntimeError(f"GitHub user not found: {USERNAME}")

collection = user["contributionsCollection"]
calendar = collection["contributionCalendar"]

print(
    "Restricted contributions:",
    collection["restrictedContributionsCount"]
)

daily = {}

for week in calendar["weeks"]:
    for item in week["contributionDays"]:
        daily[dt.date.fromisoformat(item["date"])] = (
            item["contributionCount"]
        )

dates = [start + dt.timedelta(days=i) for i in range(31)]
counts = [daily.get(date, 0) for date in dates]

peak = max(counts, default=0)
scale = max(4, math.ceil(peak / 4) * 4)

chart_width = WIDTH - LEFT - RIGHT
chart_height = BOTTOM - TOP

points = []

for i, count in enumerate(counts):
    x = LEFT + (i / 30) * chart_width
    y = BOTTOM - (count / scale) * chart_height
    points.append((x, y))


def smooth_path(points):
    path = f"M {points[0][0]:.2f} {points[0][1]:.2f}"

    for i in range(len(points) - 1):
        p0 = points[max(0, i - 1)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(len(points) - 1, i + 2)]

        cp1 = (
            p1[0] + (p2[0] - p0[0]) / 6,
            p1[1] + (p2[1] - p0[1]) / 6,
        )

        cp2 = (
            p2[0] - (p3[0] - p1[0]) / 6,
            p2[1] - (p3[1] - p1[1]) / 6,
        )

        path += (
            f" C {cp1[0]:.2f} {cp1[1]:.2f},"
            f" {cp2[0]:.2f} {cp2[1]:.2f},"
            f" {p2[0]:.2f} {p2[1]:.2f}"
        )

    return path


line = smooth_path(points)

area = (
    line
    + f" L {points[-1][0]:.2f} {BOTTOM}"
    + f" L {points[0][0]:.2f} {BOTTOM} Z"
)


def generate(theme, filename):
    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg"
     width="{WIDTH}"
     height="{HEIGHT}"
     viewBox="0 0 {WIDTH} {HEIGHT}">

  <defs>
    <linearGradient id="area"
                    x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"
            stop-color="{theme['line']}"
            stop-opacity="0.38"/>
      <stop offset="100%"
            stop-color="{theme['line']}"
            stop-opacity="0.01"/>
    </linearGradient>
  </defs>

  <rect width="100%" height="100%"
        fill="{theme['bg']}" rx="12"/>

  <path d="{area}"
        fill="url(#area)"/>

  <path d="{line}"
        fill="none"
        stroke="{theme['line']}"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"/>

  {''.join(
      f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.5" '
      f'fill="{theme["point"]}">'
      f'<title>{date.isoformat()}: {count} contributions</title>'
      f'</circle>'
      for (x, y), date, count in zip(points, dates, counts)
  )}

</svg>
"""

    (OUTPUT / filename).write_text(svg.strip(), encoding="utf-8")
    print(f"Generated {filename}")


generate(DARK, "contributions-dark.svg")
generate(LIGHT, "contributions-light.svg")

print("31-day activity graphs generated successfully.")
