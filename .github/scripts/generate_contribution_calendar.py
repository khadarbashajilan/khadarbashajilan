
import datetime as dt
import html
import json
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
year = today.year

OUTPUT_DIR = pathlib.Path("profile")
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================
# BLUE COLOR PALETTE
# ============================================================

DARK = {
    "background": "#0B1220",
    "foreground": "#CBD5E1",
    "empty": "#172033",
    "levels": [
        "#142B4A",
        "#1D4ED8",
        "#3B82F6",
        "#60A5FA",
    ],
}

LIGHT = {
    "background": "#F8FAFC",
    "foreground": "#334155",
    "empty": "#E2E8F0",
    "levels": [
        "#BFDBFE",
        "#93C5FD",
        "#3B82F6",
        "#1D4ED8",
    ],
}

# ============================================================
# GITHUB GRAPHQL API
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
    }
  }
}
"""

payload = {
    "query": QUERY,
    "variables": {
        "login": USERNAME,
        "from": f"{year}-01-01T00:00:00Z",
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
        "User-Agent": "GitHub-Contribution-Calendar",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())

except urllib.error.HTTPError as error:
    raise RuntimeError(
        f"GitHub API HTTP error: {error.code} - {error.read().decode()}"
    ) from error

except urllib.error.URLError as error:
    raise RuntimeError(f"GitHub API connection failed: {error}") from error

if result.get("errors"):
    raise RuntimeError(f"GitHub GraphQL error: {result['errors']}")

user = result["data"]["user"]

if not user:
    raise RuntimeError(f"GitHub user not found: {USERNAME}")

calendar = user["contributionsCollection"]["contributionCalendar"]

total = calendar["totalContributions"]

# ============================================================
# EXTRACT DAILY CONTRIBUTIONS
# ============================================================

days = {}

for week in calendar["weeks"]:
    for item in week["contributionDays"]:
        date = dt.date.fromisoformat(item["date"])
        days[date] = item["contributionCount"]

# ============================================================
# CALENDAR DIMENSIONS
# ============================================================

start = dt.date(year, 1, 1)
end = dt.date(year, 12, 31)

first_monday = start - dt.timedelta(days=start.weekday())
last_sunday = end + dt.timedelta(days=6 - end.weekday())

columns = ((last_sunday - first_monday).days // 7) + 1

CELL = 11
GAP = 3
PITCH = CELL + GAP

LEFT = 42
TOP = 58

WIDTH = LEFT + columns * PITCH + 16
HEIGHT = TOP + 7 * PITCH + 20

# ============================================================
# CONTRIBUTION COLOR INTENSITY
# ============================================================

def get_color(count, palette):
    if count <= 0:
        return palette["empty"]

    if count <= 2:
        return palette["levels"][0]

    if count <= 5:
        return palette["levels"][1]

    if count <= 9:
        return palette["levels"][2]

    return palette["levels"][3]


# ============================================================
# SVG GENERATOR
# ============================================================

def create_svg(theme, filename):

    svg = []

    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img">'
    )

    # Background
    svg.append(
        f'<rect width="100%" height="100%" '
        f'rx="12" fill="{theme["background"]}"/>'
    )

    # Header
    svg.append(
        f'<text x="{LEFT}" y="25" '
        f'fill="{theme["foreground"]}" '
        f'font-family="Arial, sans-serif" '
        f'font-size="16" font-weight="600">'
        f'{total} contributions in {year}'
        f'</text>'
    )

    # Month labels
    for month in range(1, 13):

        first_day = dt.date(year, month, 1)

        col = (first_day - first_monday).days // 7
        x = LEFT + col * PITCH

        svg.append(
            f'<text x="{x}" y="45" '
            f'fill="{theme["foreground"]}" '
            f'font-family="Arial, sans-serif" '
            f'font-size="10">'
            f'{first_day.strftime("%b")}'
            f'</text>'
        )

    # Weekday labels
    for row, label in [
        (0, "Mon"),
        (2, "Wed"),
        (4, "Fri"),
    ]:

        y = TOP + row * PITCH + CELL - 1

        svg.append(
            f'<text x="0" y="{y}" '
            f'fill="{theme["foreground"]}" '
            f'font-family="Arial, sans-serif" '
            f'font-size="9">'
            f'{label}'
            f'</text>'
        )

    # Contribution squares
    current = first_monday

    while current <= last_sunday:

        if start <= current <= end:

            count = days.get(current, 0)

            color = get_color(count, theme)

            col = (current - first_monday).days // 7
            row = current.weekday()

            x = LEFT + col * PITCH
            y = TOP + row * PITCH

            tooltip = (
                f"{current.isoformat()}: "
                f"{count} contributions"
            )

            svg.append(
                f'<rect x="{x}" y="{y}" '
                f'width="{CELL}" height="{CELL}" '
                f'rx="2" fill="{color}">'
                f'<title>{html.escape(tooltip)}</title>'
                f'</rect>'
            )

        current += dt.timedelta(days=1)

    # Footer legend
    legend_y = TOP + 7 * PITCH + 4

    svg.append(
        f'<text x="{LEFT}" y="{legend_y}" '
        f'fill="{theme["foreground"]}" '
        f'font-family="Arial, sans-serif" '
        f'font-size="9">Less</text>'
    )

    for index, color in enumerate(
        [theme["empty"]] + theme["levels"]
    ):

        x = LEFT + 30 + index * 16

        svg.append(
            f'<rect x="{x}" y="{legend_y - 9}" '
            f'width="10" height="10" '
            f'rx="2" fill="{color}"/>'
        )

    svg.append(
        f'<text x="{LEFT + 30 + 5 * 16}" '
        f'y="{legend_y}" '
        f'fill="{theme["foreground"]}" '
        f'font-family="Arial, sans-serif" '
        f'font-size="9">More</text>'
    )

    svg.append("</svg>")

    output_path = OUTPUT_DIR / filename

    output_path.write_text(
        "\n".join(svg),
        encoding="utf-8",
    )

    print(f"Generated: {output_path}")


# ============================================================
# GENERATE DARK AND LIGHT VERSIONS
# ============================================================

create_svg(
    DARK,
    "contributions-dark.svg",
)

create_svg(
    LIGHT,
    "contributions-light.svg",
)

# ============================================================
# SUMMARY
# ============================================================

print("--------------------------------------")
print("GitHub Contribution Calendar Updated")
print("--------------------------------------")
print(f"Username:       {USERNAME}")
print(f"Year:           {year}")
print(f"Contributions:  {total}")
print("Theme:          Midnight Blue")
print("Dark SVG:       profile/contributions-dark.svg")
print("Light SVG:      profile/contributions-light.svg")
print("--------------------------------------")
