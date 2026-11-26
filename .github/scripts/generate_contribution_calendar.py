
import datetime as dt
import html
import json
import math
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request


# ============================================================
# CONFIGURATION
# ============================================================

def required_env(name):
    value = os.environ.get(name)

    if not value or not value.strip():
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value.strip()


TOKEN = required_env("STATS_TOKEN")
USERNAME = required_env("GITHUB_USERNAME")

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

OUTPUT = REPO_ROOT / "profile"
OUTPUT.mkdir(parents=True, exist_ok=True)

UTC_NOW = dt.datetime.now(dt.timezone.utc)
TODAY = UTC_NOW.date()
START_DATE = TODAY - dt.timedelta(days=30)

WIDTH = 960
HEIGHT = 280

LEFT = 12
RIGHT = 12
TOP = 12
BOTTOM = 238

CHART_WIDTH = WIDTH - LEFT - RIGHT
CHART_HEIGHT = BOTTOM - TOP

API_URL = "https://api.github.com/graphql"

MAX_RETRIES = 5
RETRYABLE_HTTP_CODES = {
    429, 500, 502, 503, 504
}


# ============================================================
# THEMES
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
# GITHUB GRAPHQL
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


def fetch_contributions():

    payload = {
        "query": QUERY,
        "variables": {
            "login": USERNAME,
            "from": (
                f"{START_DATE.isoformat()}T00:00:00Z"
            ),
            "to": UTC_NOW.isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z"),
        },
    }

    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHub-Activity-Graph",
        },
        method="POST",
    )

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:

                result = json.loads(
                    response.read().decode("utf-8")
                )

            if result.get("errors"):
                raise RuntimeError(
                    "GitHub GraphQL errors: "
                    + json.dumps(result["errors"])
                )

            data = result.get("data")

            if not data or not data.get("user"):
                raise RuntimeError(
                    f"GitHub user not found: {USERNAME}"
                )

            return data["user"]["contributionsCollection"]

        except urllib.error.HTTPError as error:

            if error.code not in RETRYABLE_HTTP_CODES:
                raise RuntimeError(
                    f"GitHub API HTTP {error.code}: "
                    f"{error.read().decode(errors='replace')}"
                ) from error

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "GitHub API retries exhausted."
                ) from error

            retry_after = error.headers.get("Retry-After")

            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = min(2 ** attempt, 30)

            print(
                f"GitHub API returned HTTP {error.code}. "
                f"Retrying in {delay}s "
                f"({attempt}/{MAX_RETRIES})..."
            )

            time.sleep(delay)

        except urllib.error.URLError as error:

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "GitHub API connection retries exhausted."
                ) from error

            delay = min(2 ** attempt, 30)

            print(
                f"GitHub API connection failed: {error}. "
                f"Retrying in {delay}s..."
            )

            time.sleep(delay)

        except TimeoutError as error:

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "GitHub API timed out after retries."
                ) from error

            time.sleep(min(2 ** attempt, 30))

    raise RuntimeError("Unable to retrieve GitHub contributions.")


# ============================================================
# EXTRACT CONTRIBUTIONS
# ============================================================

collection = fetch_contributions()

calendar = collection["contributionCalendar"]

restricted_count = collection[
    "restrictedContributionsCount"
]

daily = {}

for week in calendar["weeks"]:
    for item in week["contributionDays"]:

        date = dt.date.fromisoformat(item["date"])

        daily[date] = item["contributionCount"]


# Exactly 31 calendar days.

DATES = [
    START_DATE + dt.timedelta(days=i)
    for i in range(31)
]

COUNTS = [
    daily.get(date, 0)
    for date in DATES
]

PEAK = max(COUNTS, default=0)
TOTAL = sum(COUNTS)


# ============================================================
# GRAPH COORDINATES
# ============================================================

SCALE = max(
    4,
    math.ceil(PEAK / 4) * 4
)


def get_x(index):
    return (
        LEFT
        + (index / 30) * CHART_WIDTH
    )


def get_y(value):
    return (
        BOTTOM
        - (value / SCALE) * CHART_HEIGHT
    )


POINTS = [
    (get_x(index), get_y(count))
    for index, count in enumerate(COUNTS)
]


# ============================================================
# BOUNDED MONOTONE SMOOTH CURVE
# ============================================================

def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def smooth_path(points):

    if not points:
        return ""

    path = (
        f"M {points[0][0]:.2f} "
        f"{points[0][1]:.2f}"
    )

    for index in range(len(points) - 1):

        p0 = points[max(0, index - 1)]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[min(len(points) - 1, index + 2)]

        # Catmull-Rom control points.
        cp1_x = p1[0] + (p2[0] - p0[0]) / 6
        cp2_x = p2[0] - (p3[0] - p1[0]) / 6

        cp1_y = p1[1] + (p2[1] - p0[1]) / 6
        cp2_y = p2[1] - (p3[1] - p1[1]) / 6

        # Keep control points inside the segment's
        # Y range, preventing overshoot.
        segment_min = max(
            TOP,
            min(p1[1], p2[1])
        )

        segment_max = min(
            BOTTOM,
            max(p1[1], p2[1])
        )

        cp1_y = clamp(
            cp1_y,
            segment_min,
            segment_max
        )

        cp2_y = clamp(
            cp2_y,
            segment_min,
            segment_max
        )

        # Keep X coordinates inside chart bounds.
        cp1_x = clamp(
            cp1_x,
            LEFT,
            WIDTH - RIGHT
        )

        cp2_x = clamp(
            cp2_x,
            LEFT,
            WIDTH - RIGHT
        )

        path += (
            f" C {cp1_x:.2f} {cp1_y:.2f},"
            f" {cp2_x:.2f} {cp2_y:.2f},"
            f" {p2[0]:.2f} {p2[1]:.2f}"
        )

    return path


LINE_PATH = smooth_path(POINTS)

AREA_PATH = (
    LINE_PATH
    + f" L {POINTS[-1][0]:.2f} {BOTTOM}"
    + f" L {POINTS[0][0]:.2f} {BOTTOM} Z"
)


# ============================================================
# SVG GENERATOR
# ============================================================

def generate_svg(theme, filename):

    svg = []

    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}">'
    )

    # Gradient.
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

    # Background.
    svg.append(
        f'<rect width="100%" height="100%" '
        f'rx="12" fill="{theme["bg"]}"/>'
    )

    # Gradient area.
    svg.append(
        f'<path d="{AREA_PATH}" '
        f'fill="url(#areaGradient)" '
        f'stroke="none"/>'
    )

    # Smooth line.
    svg.append(
        f'<path d="{LINE_PATH}" '
        f'fill="none" '
        f'stroke="{theme["line"]}" '
        f'stroke-width="2.5" '
        f'stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
    )

    # ========================================================
    # DATA POINTS AND HOVER METADATA
    # ========================================================

    for index, (date, count, point) in enumerate(
        zip(DATES, COUNTS, POINTS)
    ):

        x, y = point

        tooltip = (
            f"Date: {date.strftime('%d %b %Y')} | "
            f"Contributions: {count} | "
            f"X: {index} | "
            f"Y: {count} | "
            f"SVG X: {x:.2f} | "
            f"SVG Y: {y:.2f}"
        )

        escaped_tooltip = html.escape(tooltip)

        # Invisible hover area.
        svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
            f'r="11" fill="#ffffff" '
            f'fill-opacity="0" '
            f'pointer-events="all">'
            f'<title>{escaped_tooltip}</title>'
            f'</circle>'
        )

        # Visible point.
        svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
            f'r="2.5" fill="{theme["point"]}" '
            f'pointer-events="none"/>'
        )

    # No headings, axes, labels, or footer.
    svg.append("</svg>")

    output_path = OUTPUT / filename

    output_path.write_text(
        "\n".join(svg),
        encoding="utf-8"
    )

    print(f"Generated: {output_path}")


# ============================================================
# GENERATE BOTH THEMES
# ============================================================

generate_svg(
    DARK,
    "contributions-dark.svg"
)

generate_svg(
    LIGHT,
    "contributions-light.svg"
)


# ============================================================
# SUMMARY
# ============================================================

print("--------------------------------------")
print("GITHUB ACTIVITY GRAPH UPDATED")
print("--------------------------------------")
print(f"Username: {USERNAME}")
print(f"Period: {START_DATE} to {TODAY}")
print(f"Days: 31")
print(f"Total contributions: {TOTAL}")
print(f"Peak per day: {PEAK}")
print(f"Restricted contributions: {restricted_count}")
print(f"Output directory: {OUTPUT}")
print("--------------------------------------")
