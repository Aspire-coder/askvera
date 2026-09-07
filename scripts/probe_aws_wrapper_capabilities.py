"""Nonsecret MCP discovery only. Never resolves references or invokes AWS tools."""
import argparse
import json
import runpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrapper")
    args = parser.parse_args()
    post = runpy.run_path(args.wrapper, run_name="wrapper_discovery")["_mcp_post"]
    try:
        reply, session = post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05",
                                          "clientInfo": {"name": "asm-exec", "version": "1.0.0"},
                                          "capabilities": {}}})
        if "error" in reply:
            raise RuntimeError("Initialization failed")
        post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
        cursor = None
        for request_id in range(2, 12):
            reply, _ = post({"jsonrpc": "2.0", "id": request_id, "method": "tools/list",
                             "params": {"cursor": cursor} if cursor else {}}, session)
            if "error" in reply:
                raise RuntimeError("Tool discovery failed")
            result = reply.get("result", {})
            for tool in result.get("tools", []):
                print(json.dumps({key: tool.get(key) for key in ("name", "description", "inputSchema")}))
            cursor = result.get("nextCursor")
            if not cursor:
                break
    except Exception as exc:
        # Do not print transport errors, signed headers or credentials.
        print(json.dumps({"status": "discovery_failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
