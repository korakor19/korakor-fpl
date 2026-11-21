
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


    # Compact, readable snapshot for ChatGPT.
    # All picks are from the most recently FINISHED gameweek,
    # not necessarily the manager's current pre-deadline squad.
    player_by_id = {p["id"]: p for p in bootstrap["elements"]}
    club_by_id = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    summary = {
        "updated_at": report["updated_at"],
        "data_note": (
            "Squads/picks reflect the latest finished gameweek only. "
            "Unconfirmed pre-deadline transfers, free transfers, "
            "bank balance and chip selection are not available here."
        ),
        "completed_gameweek": gameweek,
        "next_gameweek": {
            "id": upcoming.get("id"),
            "deadline_time": upcoming.get("deadline_time"),
            "name": upcoming.get("name")
        } if upcoming else None,
        "league": {
            "id": LEAGUE_ID,
            "standings": [
                {
                    "entry": x.get("entry"),
                    "entry_name": x.get("entry_name"),
                    "player_name": x.get("player_name"),
                    "rank": x.get("rank"),
                    "total": x.get("total"),
                    "event_total": x.get("event_total")
                }
                for x in league.get("standings", {}).get("results", [])
            ]
        },
        "managers": {},
        "upcoming_fixtures": [],
        "players": {}
    }

    relevant_ids = set()
    for name, manager in report["managers"].items():
        picks_data = manager.get("picks", {})
        picks = []
        for pick in picks_data.get("picks", []):
            pid = pick["element"]
            relevant_ids.add(pid)
            p = player_by_id.get(pid, {})
            picks.append({
                "id": pid,
                "name": p.get("web_name"),
                "club": club_by_id.get(p.get("team")),
                "position": p.get("element_type"),
                "squad_position": pick.get("position"),
                "multiplier": pick.get("multiplier"),
                "captain": pick.get("is_captain"),
                "vice_captain": pick.get("is_vice_captain")
            })
        profile = manager["profile"]
        history = manager["history"]
        summary["managers"][name] = {
            "team_id": manager["team_id"],
            "overall_points": profile.get("summary_overall_points"),
            "overall_rank": profile.get("summary_overall_rank"),
            "last_finished_week_picks": picks,
            "last_finished_week_entry_history": picks_data.get("entry_history"),
            "chips_used": history.get("chips", []),
            "recent_transfers": manager["transfers"][:10],
            "recent_history": history.get("current", [])[-3:]
        }
        for transfer in manager["transfers"][:10]:
            relevant_ids.update(
                [transfer.get("element_in"), transfer.get("element_out")]
            )

    next_id = upcoming.get("id") if upcoming else None
    if next_id:
        for fixture in fixtures:
            if fixture.get("event") in (next_id, next_id + 1):
                summary["upcoming_fixtures"].append({
                    "gameweek": fixture.get("event"),
                    "home": club_by_id.get(fixture.get("team_h")),
                    "away": club_by_id.get(fixture.get("team_a")),
                    "kickoff_time": fixture.get("kickoff_time"),
                    "finished": fixture.get("finished")
                })

    for pid in sorted(relevant_ids - {None}):
        p = player_by_id.get(pid)
        if not p:
            continue
        summary["players"][str(pid)] = {
            "name": p.get("web_name"),
            "club": club_by_id.get(p.get("team")),
            "position": p.get("element_type"),
            "now_cost": p.get("now_cost"),
            "form": p.get("form"),
            "total_points": p.get("total_points"),
            "minutes": p.get("minutes"),
            "status": p.get("status"),
            "chance_of_playing_next_round": p.get("chance_of_playing_next_round"),
            "news": p.get("news"),
            "selected_by_percent": p.get("selected_by_percent")
        }

    with open(
        "data/fpl_summary.json", "w", encoding="utf-8"
    ) as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    print("SUCCESS: Compact FPL summary collected!", flush=True)

    print("SUCCESS: FPL data collected!")


if __name__ == "__main__":
    main()
