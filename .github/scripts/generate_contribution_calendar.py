
import datetime as dt
import html
import json
import math
import os
import pathlib
import urllib.request
import urllib.error

# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.environ["STATS_TOKEN"]
USERNAME = os.environ["GITHUB_USERNAME"]

today = dt.datetime.now(dt.timezone.utc).date()
start_date = today - dt.timedelta(days=30)

OUTPUT = pathlib.Path("profile")
OUTPUT.mkdir(exist_ok=True)

WIDTH = 960
HEIGHT = 280

LEFT = 12
RIGHT = 12
TOP = 12
BOTTOM = 238

CHART_WIDTH = WIDTH - LEFT - RIGHT
CHART_HEIGHT = BOTTOM - TOP

# ============================================================
# MIDNIGHT BLUE THEMES
# ============================================================

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

# ============================================================
# GITHUB GRAPHQL API
# ============================================================

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
        "from": f"{start_date.isoformat()}T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z",
    },
}

request = urllib.request.Request(
    "https://api.github.com/graphql",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitHub-Activity-Graph",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())

except urllib.error.HTTPError as error:
    raise RuntimeError(
        f"GitHub API error {error.code}: "
        f"{error.read().decode()}"
    ) from error

except urllib.error.URLError as error:
    raise RuntimeError(
        f"GitHub API connection failed: {error}"
    ) from error

if result.get("errors"):
    raise RuntimeError(
        f"GitHub GraphQL error: {result['errors']}"
    )

user = result["data"]["user"]

if not user:
    raise RuntimeError(f"GitHub user not found: {USERNAME}")

collection = user["contributionsCollection"]
calendar = collection["contributionCalendar"]

restricted_count = collection["restrictedContributionsCount"]

print(f"Private/restricted contributions: {restricted_count}")

# ============================================================
# EXTRACT DAILY CONTRIBUTIONS
# ============================================================

daily = {}

for week in calendar["weeks"]:
    for item in week["contributionDays"]:
        date = dt.date.fromisoformat(item["date"])
        daily[date] = item["contributionCount"]

# Exactly 31 days
dates = [
    start_date + dt.timedelta(days=i)
    for i in range(31)
]

counts = [
    daily.get(date, 0)
    for date in dates
]

peak = max(counts, default=0)

# ============================================================
# GRAPH COORDINATES
# ============================================================

scale = max(4, math.ceil(peak / 4) * 4)

def get_x(index):
    return LEFT + (index / 30) * CHART_WIDTH


def get_y(value):
    return BOTTOM - (value / scale) * CHART_HEIGHT


points = [
    (get_x(i), get_y(count))
    for i, count in enumerate(counts)
]

# ============================================================
# SMOOTH CURVE
# ============================================================

def smooth_path(points):

    if not points:
        return ""

    path = (
        f"M {points[0][0]:.2f} "
        f"{points[0][1]:.2f}"
    )

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


line_path = smooth_path(points)

area_path = (
    line_path
    + f" L {points[-1][0]:.2f} {BOTTOM}"
    + f" L {points[0][0]:.2f} {BOTTOM} Z"
)

# ============================================================
# GENERATE SVG
# ============================================================

def generate(theme, filename):

    svg = []

    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}">'
    )

    # Gradient
    svg.append(
        f'<defs>'
        f'<linearGradient id="areaGradient" '
        f'x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" '
        f'stop-color="{theme["line"]}" '
        f'stop-opacity="0.38"/>'
        f'<stop offset="100%" '
        f'stop-color="{theme["line"]}" '
        f'stop-opacity="0.01"/>'
        f'</linearGradient>'
        f'</defs>'
    )

    # Background
    svg.append(
        f'<rect width="100%" height="100%" '
        f'rx="12" fill="{theme["bg"]}"/>'
    )

    # Gradient area
    svg.append(
        f'<path d="{area_path}" '
        f'fill="url(#areaGradient)" '
        f'stroke="none"/>'
    )

    # Smooth activity line
    svg.append(
        f'<path d="{line_path}" '
        f'fill="none" '
        f'stroke="{theme["line"]}" '
        f'stroke-width="2.5" '
        f'stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
    )

    # ========================================================
    # INTERACTIVE DATA POINTS
    # ========================================================

    for index, (date, count, point) in enumerate(
        zip(dates, counts, points)
    ):

        x, y = point

        date_text = date.strftime("%d %b %Y")

        # Actual data coordinates:
        # X = day index (0 to 30)
        # Y = contribution count

        tooltip = (
            f"Date: {date_text}\n"
            f"Contributions: {count}\n"
            f"X coordinate: {index}\n"
            f"Y coordinate: {count}\n"
            f"SVG X: {x:.2f} viewBox units\n"
            f"SVG Y: {y:.2f} viewBox units"
        )

        escaped_tooltip = html.escape(tooltip)

        # Invisible hover target with a 22-unit diameter
        # The SVG title is displayed as a native tooltip.
        svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
            f'r="11" fill="#ffffff" fill-opacity="0" '
            f'pointer-events="all">'
            f'<title>{escaped_tooltip}</title>'
            f'</circle>'
        )

        # Visible point
        svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
            f'r="2.5" fill="{theme["point"]}" '
            f'pointer-events="none"/>'
        )

    # No title, labels, axes, legend or footer.
    svg.append("</svg>")

    output_path = OUTPUT / filename

    output_path.write_text(
        "\n".join(svg),
        encoding="utf-8",
    )

    print(f"Generated: {output_path}")


# ============================================================
# DARK AND LIGHT GRAPHS
# ============================================================

generate(DARK, "contributions-dark.svg")
generate(LIGHT, "contributions-light.svg")

# ============================================================
# SUMMARY
# ============================================================

print("--------------------------------------")
print("ACTIVITY GRAPH GENERATED")
print("--------------------------------------")
print(f"Username: {USERNAME}")
print(f"Period: {start_date} to {today}")
print(f"Days: 31")
print(f"Contributions: {sum(counts)}")
print(f"Peak/day: {peak}")
print(f"Restricted contributions: {restricted_count}")
print("Theme: Midnight Blue")
print("Hover: Date, count, X/Y and SVG position")
print("--------------------------------------")
