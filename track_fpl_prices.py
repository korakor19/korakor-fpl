"""Daily public FPL price snapshots. No private account information required."""
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

API = "https://fantasy.premierleague.com/api/bootstrap-static/"
HISTORY = Path("data/fpl_price_history.json")
LATEST = Path("data/fpl_price_watch.json")
MAX_DAYS = 120

def fetch():
    for attempt in range(3):
        try:
            response = subprocess.run(
                ["curl", "--silent", "--show-error", "--fail", "--max-time", "60", API],
                check=True, capture_output=True, text=True
            )
            result = json.loads(response.stdout)
            if not result.get("elements") or not result.get("teams"):
                raise ValueError("FPL response missing players or clubs")
            return result
        except (subprocess.CalledProcessError, ValueError) as error:
            if attempt == 2:
                raise
            print(f"Download failed: {error}; retrying", flush=True)
            time.sleep(5)

def main():
    data = fetch()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    clubs = {str(t["id"]): t["short_name"] for t in data["teams"]}
    players = {
        str(p["id"]): {
            "name": p.get("web_name"),
            "team_id": p.get("team"),
            "position_id": p.get("element_type"),
            "price": p.get("now_cost"),
            "transfers_in_event": p.get("transfers_in_event"),
            "transfers_out_event": p.get("transfers_out_event"),
            "selected_by_percent": p.get("selected_by_percent"),
            "status": p.get("status")
        }
        for p in data["elements"]
    }
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history = {"snapshots": []}
    if HISTORY.exists():
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
    snapshots = history.get("snapshots", [])
    # One daily snapshot; reruns replace today's entry.
    snapshots = [s for s in snapshots if s.get("date") != today]
    snapshots.append({
        "date": today,
        "captured_at": now.isoformat(),
        "prices": {pid: p["price"] for pid, p in players.items()}
    })
    snapshots.sort(key=lambda s: s["date"])
    snapshots = snapshots[-MAX_DAYS:]
    HISTORY.write_text(
        json.dumps({"source": API, "price_unit": "0.1m GBP",
                    "snapshots": snapshots}, separators=(",", ":")),
        encoding="utf-8"
    )

    def previous_price(pid, days):
        earlier = [s for s in snapshots if s["date"] < today]
        if not earlier:
            return None
        # Use the latest available observation at or before the target date.
        from datetime import timedelta
        target = (now.date() - timedelta(days=days)).isoformat()
        eligible = [s for s in earlier if s["date"] <= target]
        if not eligible:
            return None
        return eligible[-1]["prices"].get(pid)

    watch = []
    for pid, p in players.items():
        current = p["price"]
        prev_day = previous_price(pid, 1)
        prev_week = previous_price(pid, 7)
        watch.append({
            "id": int(pid), "name": p["name"],
            "club": clubs.get(str(p["team_id"])),
            "position_id": p["position_id"],
            "now_cost": current,
            "change_1d": current - prev_day if prev_day is not None else None,
            "change_7d": current - prev_week if prev_week is not None else None,
            "transfers_in_event": p["transfers_in_event"],
            "transfers_out_event": p["transfers_out_event"],
            "selected_by_percent": p["selected_by_percent"],
            "status": p["status"]
        })
    latest = {
        "updated_at": now.isoformat(),
        "price_unit": "0.1m GBP",
        "history_days": len(snapshots),
        "methodology": (
            "Observed daily prices and current-gameweek transfer totals from official FPL. "
            "Transfer totals are cumulative for the gameweek, not daily net flows. "
            "Price changes are historical observations, NOT predictions of tomorrow's price. "
            "No personal purchase price, sale price, or bank balance is available."
        ),
        "players": watch
    }
    LATEST.write_text(json.dumps(latest, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(players)} player prices; {len(snapshots)} daily snapshots", flush=True)

if __name__ == "__main__":
    main()
