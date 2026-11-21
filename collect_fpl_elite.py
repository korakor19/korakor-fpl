"""Collect public overall top-50 FPL managers and their published picks."""
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://fantasy.premierleague.com/api/"
OUT = Path("data/fpl_elite_managers.json")
HISTORY = Path("data/fpl_elite_history.json")

def fetch(path):
    for attempt in range(3):
        try:
            r = subprocess.run(
                ["curl", "--silent", "--show-error", "--fail", "--max-time", "35", BASE + path],
                capture_output=True, text=True, check=True)
            return json.loads(r.stdout)
        except (subprocess.CalledProcessError, ValueError):
            if attempt == 2:
                raise
            time.sleep(3)

def main():
    now = datetime.now(timezone.utc)
    bootstrap = fetch("bootstrap-static/")
    finished = max((e["id"] for e in bootstrap["events"] if e.get("finished")), default=0)
    league = fetch("leagues-classic/314/standings/?page_standings=1")
    standings = league.get("standings", {}).get("results", [])[:50]
    if not standings:
        raise ValueError("Overall standings returned no entries; refusing empty report")
    player_map = {p["id"]: p for p in bootstrap["elements"]}
    elite = []
    for rank, item in enumerate(standings, 1):
        entry_id = item["entry"]
        record = {
            "rank": item.get("rank", rank),
            "entry_id": entry_id,
            "team_name": item.get("entry_name"),
            "manager_name": item.get("player_name"),
            "total": item.get("total"),
            "event_total": item.get("event_total")
        }
        # A failed manager fetch should not discard the other 49 managers.
        for key, endpoint in (
            ("history", f"entry/{entry_id}/history/"),
            ("transfers", f"entry/{entry_id}/transfers/"),
            ("picks", f"entry/{entry_id}/event/{finished}/picks/" if finished else None)
        ):
            if not endpoint:
                continue
            try:
                payload = fetch(endpoint)
                if key == "history":
                    record["chips_used"] = payload.get("chips", [])
                    record["recent_gameweeks"] = payload.get("current", [])[-5:]
                elif key == "transfers":
                    record["recent_transfers"] = payload[:8]
                else:
                    record["last_finished_week_picks"] = [
                        {
                            "id": p["element"],
                            "name": player_map.get(p["element"], {}).get("web_name"),
                            "squad_position": p.get("position"),
                            "multiplier": p.get("multiplier"),
                            "captain": p.get("is_captain"),
                            "vice_captain": p.get("is_vice_captain")
                        } for p in payload.get("picks", [])
                    ]
            except Exception as exc:
                record.setdefault("unavailable", []).append(key)
                print(f"Manager {entry_id} {key}: {exc}", flush=True)
            time.sleep(0.15)
        elite.append(record)
    report = {
        "updated_at": now.isoformat(),
        "source": "Official public FPL overall league 314 and entry endpoints",
        "completed_gameweek": finished,
        "data_note": "Overall top 50 is a changing snapshot, not a fixed cohort. Picks reflect the last finished gameweek, never undisclosed current transfers. High rank may reflect variance as well as skill.",
        "managers": elite
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    past = {"snapshots": []}
    if HISTORY.exists():
        past = json.loads(HISTORY.read_text(encoding="utf-8"))
    date = now.date().isoformat()
    snapshots = [s for s in past.get("snapshots", []) if s.get("date") != date]
    snapshots.append({"date": date, "completed_gameweek": finished,
                      "top_50": [{"entry_id": x["entry_id"], "rank": x["rank"], "total": x["total"]} for x in elite]})
    snapshots.sort(key=lambda s: s["date"])
    HISTORY.write_text(json.dumps({"snapshots": snapshots[-80:]}, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(elite)} elite managers; finished GW {finished}", flush=True)

if __name__ == "__main__":
    main()
