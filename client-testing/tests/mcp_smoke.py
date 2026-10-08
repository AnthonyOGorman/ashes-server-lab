"""Real stdio MCP initialization/list/call with no live client input."""
import asyncio
import json
import sys
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HOME = Path(__file__).resolve().parents[1]


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(HOME / 'cli.py'), '--mode', 'mcp'])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=20) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            assert names == sorted(['get_status', 'get_player_state', 'get_world_state', 'capture_screen', 'press_key', 'run_scenario', 'cancel_test'])
            status = await session.call_tool('get_status', {})
            assert not status.is_error
            blocked = await session.call_tool('press_key', {'key': 'w', 'duration': .1})
            assert blocked.is_error, 'Observation-mode server must refuse input'
            result = {'server': init.server_info.model_dump(), 'tools': names,
                      'initialize_list_call_passed': True, 'readonly_input_refusal': True}
            if '--live' in sys.argv or '--capture-only' in sys.argv:
                live = {}
                requested = ['capture_screen'] if '--capture-only' in sys.argv else ['get_player_state', 'get_world_state', 'capture_screen']
                for name in requested:
                    called = await session.call_tool(name, {})
                    assert not called.is_error, str(called.content)
                    if name == 'capture_screen':
                        assert any(c.type == 'image' for c in called.content), 'Screenshot should include pixels for the LLM'
                    data = called.structured_content
                    if data is None:
                        data = json.loads(next(c.text for c in called.content if c.type == 'text'))
                    live[name] = data
                result['live_read_only_tools'] = live
            (HOME / 'runs').mkdir(exist_ok=True)
            report = json.dumps(result, indent=2)
            (HOME / 'runs/mcp-smoke.json').write_text(report)
            (HOME / 'runs' / ('mcp-smoke-' + uuid.uuid4().hex + '.json')).write_text(report)
            print(json.dumps({k: v for k, v in result.items() if k != 'live_read_only_tools'}))


asyncio.run(main())
