"""Report the first recorded prediction divergence for one C++ connection.

Read-only SQLite access. No game input, service startup or state modification.
The report is recorded server comparison evidence, not native-client acceptance.
"""
import argparse
import collections
import json
import pathlib
import sqlite3


def analyze(database, connection_id):
    counts = collections.Counter()
    flags = collections.Counter()
    speeds = collections.Counter()
    first = None
    largest = None
    rows = []
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for event_id, observed, detail in db.execute(
            "SELECT id,ts,detail FROM events WHERE kind='movement' ORDER BY id"
        ):
            event = json.loads(detail)
            if event.get("connection_id") != connection_id:
                continue
            result = event["result"]
            counts[result.get("response", "intermediate")] += 1
            flags[str(result.get("compressed_flags", "unrecorded"))] += 1
            speeds[result.get("comparison", {}).get("speed_selection", "unrecorded")] += 1
            row = {"event_id": event_id, "observed_unix": observed, **result}
            rows.append(row)
            if "prediction_error_cm" not in result:
                continue
            if largest is None or result["prediction_error_cm"] > largest["prediction_error_cm"]:
                largest = row
            if first is None and (
                result["prediction_error_cm"] > 10
                or result.get("reported_movement_mode") != result.get("movement_mode")
                or "discarded_time" in result
                or result.get("speed_synchronized") is False
            ):
                first = row
    return {
        "connection_id": connection_id,
        "moves": len(rows),
        "response_counts": dict(counts),
        "compressed_flag_counts": dict(flags),
        "speed_selection_counts": dict(speeds),
        "first_response_divergence": first,
        "largest_position_error": largest,
        "evidence": "recorded C++ comparisons; independent live readback still required",
        "trace": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("connection_id", help="Exact fresh /api/connections id")
    parser.add_argument("--database", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parents[1] / "data/lab.sqlite")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    report = analyze(args.database, args.connection_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "trace"}, indent=2))


if __name__ == "__main__":
    main()
