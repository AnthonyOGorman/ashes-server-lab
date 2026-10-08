"""Use --mode mcp for a stdio MCP server, or --tool for a single JSON call."""
import argparse
import json
import sys

from ashes_testing.bridge import Bridge

TOOLS = ('get_status', 'get_player_state', 'get_world_state', 'capture_screen',
         'press_key', 'run_scenario', 'cancel_test')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--enable-input', action='store_true')
    parser.add_argument('--mode', choices=('cli', 'mcp'), default='cli')
    parser.add_argument('--tool', choices=TOOLS, default='get_status')
    parser.add_argument('--arguments', default='{}', help='JSON object of tool arguments')
    args = parser.parse_args()
    bridge = Bridge(args.pid, args.enable_input)
    if args.mode == 'mcp':
        from ashes_testing.server import run
        run(bridge)
        return
    try:
        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError('Arguments must be a JSON object')
        result = getattr(bridge, args.tool)(**arguments)
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        sys.exit(1)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
