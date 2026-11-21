
import json
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://fantasy.premierleague.com/api/"
LEAGUE_ID = 1188591

TEAMS = {
    "KoraKor FC": 5556298,
    "kermitspor": 1713117,
    "Al Habibi FC": 5478165,
    "Munich JK": 6240087,
    "titalyano": 8868593,
    "SV Cheesebaden": 5870944
}


def fetch(endpoint):
    url = BASE_URL + endpoint
    print(f"Downloading: {url}", flush=True)

    for attempt in range(3):
        try:
            result = subprocess.run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--max-time", "60",
                    url
                ],
                capture_output=True,
                text=True,
                check=True
            )

            data = json.loads(result.stdout)
            print("OK", flush=True)
            time.sleep(1)
            return data

        except Exception as error:
            print(f"Attempt {attempt + 1}: {error}")

            if attempt == 2:
                raise

            time.sleep(5)


def main():
    bootstrap = fetch("bootstrap-static/")
    fixtures = fetch("fixtures/")

    events = bootstrap["events"]

    completed = [
        e["id"] for e in events
        if e.get("finished")
    ]

    gameweek = max(completed, default=0)

    upcoming = next(
        (e for e in events if e.get("is_next")),
        None
    )

    league = fetch(
        f"leagues-classic/{LEAGUE_ID}/standings/"
    )

    report = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "completed_gameweek": gameweek,
        "next_gameweek": upcoming,
        "league": league,
        "managers": {},
        "players": bootstrap["elements"],
        "clubs": bootstrap["teams"],
        "positions": bootstrap["element_types"],
        "events": events,
        "fixtures": fixtures
    }

    for name, team_id in TEAMS.items():
        manager = {
            "team_id": team_id,
            "profile": fetch(
                f"entry/{team_id}/"
            ),
            "history": fetch(
                f"entry/{team_id}/history/"
            ),
            "transfers": fetch(
                f"entry/{team_id}/transfers/"
            )
        }

        if gameweek:
            manager["picks"] = fetch(
                f"entry/{team_id}/event/"
                f"{gameweek}/picks/"
            )

        report["managers"][name] = manager

    Path("data").mkdir(exist_ok=True)

    with open(
        "data/fpl_data.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("SUCCESS: FPL data collected!")


if __name__ == "__main__":
    main()
