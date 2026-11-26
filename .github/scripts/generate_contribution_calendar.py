
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

OUTPUT_DIR = pathlib.Path("profile")
OUTPUT_DIR.mkdir(exist_ok=True)

WIDTH = 960
HEIGHT = 300

LEFT = 72
RIGHT = 28
TOP = 76
BOTTOM = 232

CHART_WIDTH = WIDTH - LEFT - RIGHT
CHART_HEIGHT = BOTTOM - TOP

# ============================================================
# MIDNIGHT BLUE THEMES
# ============================================================

DARK = {
    "background": "#0B1220",
    "foreground": "#CBD5E1",
    "muted": "#64748B",
    "grid": "#243247",
    "line": "#58A6FF",
    "point": "#93C5FD",
    "gradient_start": "#3B82F6",
    "gradient_end": "#3B82F6",
}

LIGHT = {
    "background": "#F8FAFC",
    "foreground": "#334155",
    "muted": "#64748B",
    "grid": "#DCE5F0",
    "line": "#2563EB",
    "point": "#1D4ED8",
    "gradient_start": "#3B82F6",
    "gradient_end": "#3B82F6",
}

# ============================================================
# GITHUB GRAPHQL API
#
# Private/internal contributions require read:user.
# GitHub profile must also have private contribution
# counts enabled.
# ============================================================

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
      restrictedContributionsCount
      hasAnyRestrictedContributions
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
        f"GitHub API HTTP error: "
        f"{error.code} - {error.read().decode()}"
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

# ============================================================
# PRIVATE CONTRIBUTION VERIFICATION
# ============================================================

restricted_count = collection["restrictedContributionsCount"]
has_private_activity = collection["hasAnyRestrictedContributions"]

print("--------------------------------------")
print("PRIVATE CONTRIBUTION DIAGNOSTICS")
print("--------------------------------------")
print(f"Restricted contributions: {restricted_count}")
print(f"Private activity detected: {has_private_activity}")

if restricted_count > 0:
    print("Private contribution counts are included.")
else:
    print(
        "No restricted contributions reported for this period."
    )
    print(
        "If you expect private activity, verify your "
        "read:user token scope and profile visibility setting."
    )

# ============================================================
# EXTRACT DAILY CONTRIBUTIONS
# ============================================================

days = {}

for week in calendar["weeks"]:
    for item in week["contributionDays"]:
        date = dt.date.fromisoformat(item["date"])
        days[date] = item["contributionCount"]

dates = [
    start_date + dt.timedelta(days=i)
    for i in range(31)
]

counts = [
    days.get(date, 0)
    for date in dates
]

# Use GitHub's daily calendar counts.
# These include eligible private contributions when
# read:user and profile visibility requirements are met.

total = sum(counts)
peak = max(counts, default=0)
active_days = sum(count > 0 for count in counts)

# ============================================================
# CHART COORDINATES
# ============================================================

axis_max = max(4, math.ceil(peak / 4) * 4)


def get_x(index):
    return LEFT + (index / 30) * CHART_WIDTH


def get_y(value):
    return BOTTOM - (value / axis_max) * CHART_HEIGHT


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

    if len(points) == 1:
        x, y = points[0]
        return f"M {x:.2f} {y:.2f}"

    path = (
        f"M {points[0][0]:.2f} "
        f"{points[0][1]:.2f}"
    )

    for i in range(len(points) - 1):

        p0 = points[max(0, i - 1)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(len(points) - 1, i + 2)]

        cp1_x = p1[0] + (p2[0] - p0[0]) / 6
        cp1_y = p1[1] + (p2[1] - p0[1]) / 6

        cp2_x = p2[0] - (p3[0] - p1[0]) / 6
        cp2_y = p2[1] - (p3[1] - p1[1]) / 6

        path += (
            f" C {cp1_x:.2f} {cp1_y:.2f},"
            f" {cp2_x:.2f} {cp2_y:.2f},"
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
# SVG GENERATOR
# ============================================================

def create_svg(theme, filename):

    svg = []

    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'role="img" aria-labelledby="title">'
    )

    svg.append(
        f'<defs>'
        f'<linearGradient id="areaGradient" '
        f'x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" '
        f'stop-color="{theme["gradient_start"]}" '
        f'stop-opacity="0.42"/>'
        f'<stop offset="100%" '
        f'stop-color="{theme["gradient_end"]}" '
        f'stop-opacity="0.015"/>'
        f'</linearGradient>'
        f'</defs>'
    )

    # Background
    svg.append(
        f'<rect width="100%" height="100%" '
        f'rx="14" fill="{theme["background"]}"/>'
    )

    # Title
    svg.append(
        f'<text id="title" x="32" y="34" '
        f'fill="{theme["foreground"]}" '
        f'font-family="Arial, sans-serif" '
        f'font-size="17" font-weight="600">'
        f'GitHub Activity'
        f'</text>'
    )

    # Subtitle
    svg.append(
        f'<text x="32" y="55" '
        f'fill="{theme["muted"]}" '
        f'font-family="Arial, sans-serif" '
        f'font-size="11">'
        f'Last 31 days · {total:,} contributions'
        f'</text>'
    )

    # Grid and Y-axis
    for tick in range(5):

        value = round(axis_max * tick / 4)
        y = get_y(value)

        svg.append(
            f'<line x1="{LEFT}" y1="{y:.2f}" '
            f'x2="{WIDTH - RIGHT}" y2="{y:.2f}" '
            f'stroke="{theme["grid"]}" '
            f'stroke-width="1" stroke-dasharray="3 5"/>'
        )

        svg.append(
            f'<text x="{LEFT - 14}" y="{y + 4:.2f}" '
            f'text-anchor="end" '
            f'fill="{theme["muted"]}" '
            f'font-family="Arial, sans-serif" font-size="10">'
            f'{value}</text>'
        )

    # Gradient area
    svg.append(
        f'<path d="{area_path}" '
        f'fill="url(#areaGradient)" stroke="none"/>'
    )

    # Activity line
    svg.append(
        f'<path d="{line_path}" '
        f'fill="none" '
        f'stroke="{theme["line"]}" '
        f'stroke-width="2.8" '
        f'stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
    )

    # Daily points and hover tooltips
    for i, (date, count, point) in enumerate(
        zip(dates, counts, points)
    ):

        x, y = point

        tooltip = (
            f"{date.strftime('%b %d, %Y')}: "
            f"{count} contributions"
        )

        radius = 3.5 if i == 30 else 2.2

        fill = (
            theme["point"]
            if i == 30
            else theme["line"]
        )

        svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
            f'r="{radius}" fill="{fill}">'
            f'<title>{html.escape(tooltip)}</title>'
            f'</circle>'
        )

    # Latest point highlight
    latest_x, latest_y = points[-1]

    svg.append(
        f'<circle cx="{latest_x:.2f}" '
        f'cy="{latest_y:.2f}" r="7" '
        f'fill="{theme["line"]}" fill-opacity="0.18"/>'
    )

    svg.append(
        f'<circle cx="{latest_x:.2f}" '
        f'cy="{latest_y:.2f}" r="3.5" '
        f'fill="{theme["point"]}"/>'
    )

    # X-axis labels
    for index in [0, 7, 15, 23, 30]:

        date = dates[index]
        x = get_x(index)

        svg.append(
            f'<text x="{x:.2f}" y="258" '
            f'text-anchor="middle" '
            f'fill="{theme["muted"]}" '
            f'font-family="Arial, sans-serif" font-size="10">'
            f'{date.strftime("%b %d")}'
            f'</text>'
        )

    # Footer
    svg.append(
        f'<text x="32" y="285" '
        f'fill="{theme["foreground"]}" '
        f'font-family="Arial, sans-serif" font-size="10">'
        f'{active_days} active days'
        f'</text>'
    )

    svg.append(
        f'<text x="{WIDTH - 32}" y="285" '
        f'text-anchor="end" '
        f'fill="{theme["muted"]}" '
        f'font-family="Arial, sans-serif" font-size="10">'
        f'Peak: {peak} contributions/day'
        f'</text>'
    )

    svg.append("</svg>")

    output_path = OUTPUT_DIR / filename

    output_path.write_text(
        "\n".join(svg),
        encoding="utf-8",
    )

    print(f"Generated: {output_path}")


# ============================================================
# GENERATE DARK AND LIGHT GRAPHS
# ============================================================

create_svg(DARK, "contributions-dark.svg")
create_svg(LIGHT, "contributions-light.svg")

# ============================================================
# SUMMARY
# ============================================================

print("--------------------------------------")
print("GITHUB ACTIVITY GRAPH UPDATED")
print("--------------------------------------")
print(f"Username:                 {USERNAME}")
print(f"Period:                   {start_date} to {today}")
print(f"Days:                     31")
print(f"Contributions:            {total}")
print(f"Active days:              {active_days}")
print(f"Peak per day:             {peak}")
print(f"Restricted contributions: {restricted_count}")
print(f"Private activity found:   {has_private_activity}")
print("Theme:                    Midnight Blue")
print("--------------------------------------")
