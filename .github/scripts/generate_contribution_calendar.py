
import datetime as dt
import html
import json
import os
import pathlib
import re
import urllib.request

TOKEN = os.environ["STATS_TOKEN"]
USERNAME = os.environ["GITHUB_USERNAME"]

today = dt.datetime.now(dt.timezone.utc).date()
year = today.year

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
            color
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
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitHub-Contribution-Calendar",
    },
    method="POST",
)

with urllib.request.urlopen(request, timeout=30) as response:
    result = json.loads(response.read())

if result.get("errors"):
    raise RuntimeError(f"GitHub GraphQL error: {result['errors']}")

user = result["data"]["user"]
if not user:
    raise RuntimeError(f"GitHub user not found: {USERNAME}")

calendar_data = (
    user["contributionsCollection"]["contributionCalendar"]
)

total = calendar_data["totalContributions"]

days = {}
for week in calendar_data["weeks"]:
    for item in week["contributionDays"]:
        day = dt.date.fromisoformat(item["date"])
        days[day] = item

start = dt.date(year, 1, 1)
end = dt.date(year, 12, 31)

# Monday-aligned calendar, matching GitHub's weekday arrangement.
first_monday = start - dt.timedelta(days=start.weekday())
last_sunday = end + dt.timedelta(days=6 - end.weekday())

columns = ((last_sunday - first_monday).days // 7) + 1

CELL = 11
GAP = 3
PITCH = CELL + GAP
LEFT = 42
TOP = 54

WIDTH = LEFT + columns * PITCH + 12
HEIGHT = TOP + 7 * PITCH + 20

pathlib.Path("profile").mkdir(exist_ok=True)


def create_svg(dark=True):
    background = "#0d1117" if dark else "#ffffff"
    foreground = "#c9d1d9" if dark else "#57606a"
    empty = "#161b22" if dark else "#ebedf0"

    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img">',
        f'<rect width="100%" height="100%" rx="12" fill="{background}"/>',
        (
            f'<text x="{LEFT}" y="23" fill="{foreground}" '
            'font-family="Arial, sans-serif" font-size="16" '
            'font-weight="600">'
            f'{total} contributions in {year}</text>'
        ),
    ]

    # Month labels
    for month in range(1, 13):
        first_day = dt.date(year, month, 1)
        col = (first_day - first_monday).days // 7
        x = LEFT + col * PITCH

        svg.append(
            f'<text x="{x}" y="43" fill="{foreground}" '
            'font-family="Arial, sans-serif" font-size="10">'
            f'{html.escape(first_day.strftime("%b"))}</text>'
        )

    # Weekday labels
    for row, label in [(0, "Mon"), (2, "Wed"), (4, "Fri")]:
        y = TOP + row * PITCH + CELL - 1

        svg.append(
            f'<text x="0" y="{y}" fill="{foreground}" '
            'font-family="Arial, sans-serif" font-size="9">'
            f'{label}</text>'
        )

    # Contribution squares
    current = first_monday

    while current <= last_sunday:
        if start <= current <= end:
            item = days.get(current)
            count = item["contributionCount"] if item else 0

            color = empty

            if count > 0:
                color = item["color"]

                if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    raise ValueError(f"Invalid GitHub color: {color}")

            col = (current - first_monday).days // 7
            row = current.weekday()

            x = LEFT + col * PITCH
            y = TOP + row * PITCH

            tooltip = (
                f"{current.isoformat()}: {count} contributions"
            )

            svg.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" '
                f'height="{CELL}" rx="2" fill="{color}">'
                f'<title>{html.escape(tooltip)}</title>'
                '</rect>'
            )

        current += dt.timedelta(days=1)

    svg.append("</svg>")

    filename = (
        "profile/contributions-dark.svg"
        if dark
        else "profile/contributions-light.svg"
    )

    pathlib.Path(filename).write_text(
        "\n".join(svg),
        encoding="utf-8"
    )

    print(f"Generated {filename}")


create_svg(dark=True)
create_svg(dark=False)

print(f"GitHub contributions for {year}: {total}")
