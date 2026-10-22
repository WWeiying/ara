#!/usr/bin/env python3
"""Compare store handshake timing in frozen CVXIF UVM A/B logs."""

import argparse
import hashlib
import json
import re
from pathlib import Path


EVENT = re.compile(
    r"\[CVXIF/EVENT\] cycle=(\d+) req_fire=([01]) req_id=(\d+) "
    r"insn=([0-9a-fA-F]+) resp_fire=([01]) resp_id=(\d+) exc=([01])"
)


def events(path: Path) -> list[dict]:
    found = []
    for line in path.read_text(errors="replace").splitlines():
        match = EVENT.search(line)
        if match:
            cycle, request, request_id, insn, response, response_id, exception = match.groups()
            found.append({"cycle": int(cycle), "request": request == "1",
                          "request_id": int(request_id), "insn": insn.lower(),
                          "response": response == "1", "response_id": int(response_id),
                          "exception": exception == "1"})
    if not found:
        raise ValueError(f"no CVXIF events in {path}")
    return found


def summarize(trace: list[dict], store_insn: str) -> dict:
    pending = {}
    stores = []
    requests = []
    for event in trace:
        if event["request"]:
            request = {"cycle": event["cycle"], "insn": event["insn"],
                       "id": event["request_id"]}
            if request["id"] in pending:
                raise ValueError(f"reused outstanding CVXIF ID {request['id']}")
            pending[request["id"]] = request
            requests.append(request)
        if event["response"]:
            response_id = event["response_id"]
            if response_id not in pending:
                raise ValueError(f"response without request for CVXIF ID {response_id}")
            request = pending.pop(response_id)
            if request["insn"] == store_insn:
                stores.append({"request_cycle": request["cycle"],
                               "response_cycle": event["cycle"],
                               "response_latency": event["cycle"] - request["cycle"],
                               "exception": event["exception"]})
    for store in stores:
        following = next((request for request in requests
                          if request["cycle"] > store["response_cycle"]), None)
        store["next_request_cycle"] = following["cycle"] if following else None
        store["response_to_next_request"] = (
            following["cycle"] - store["response_cycle"] if following else None)
    latencies = [store["response_latency"] for store in stores]
    gaps = [store["response_to_next_request"] for store in stores
            if store["response_to_next_request"] is not None]
    return {"store_count": len(stores), "response_latency_sum": sum(latencies),
            "response_latency_min": min(latencies, default=None),
            "response_latency_max": max(latencies, default=None),
            "response_to_next_request_sum": sum(gaps),
            "response_to_next_request_count": len(gaps), "stores": stores,
            "unanswered_requests": len(pending)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-log", type=Path, required=True)
    parser.add_argument("--precise-log", type=Path, required=True)
    parser.add_argument("--store-insn", default="020661a7")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"store_insn": args.store_insn.lower(), "scope":
              "CVXIF monitor handshake timing; no internal WAIT or AXI-B attribution"}
    for name, path in (("baseline", args.baseline_log), ("precise", args.precise_log)):
        report[name] = {"log": str(path.resolve()),
                        "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        **summarize(events(path), args.store_insn.lower())}
    if report["baseline"]["store_count"] != report["precise"]["store_count"]:
        raise ValueError("store counts differ between A/B logs")
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"matched {report['baseline']['store_count']} stores: "
          f"response-latency sums {report['baseline']['response_latency_sum']} -> "
          f"{report['precise']['response_latency_sum']} cycles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
