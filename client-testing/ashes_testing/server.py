"""Official MCP SDK stdio transport; no network listener or model API key."""
import asyncio
import threading
import base64
import json
from pathlib import Path


def create_server(bridge):
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations, CallToolResult, TextContent, ImageContent
    from mcp.server.mcpserver.exceptions import ToolError
    server = MCPServer('Ashes Client Testing', version='0.1.0',
                       instructions='Observe the exact local Ashes client. Input requires a coordinated exclusive window. All artifacts are under client-testing/runs. Displacement is not proof of correct walking.')

    async def invoke(method, *args, controlled=False):
        cancel = threading.Event()
        try:
            return await asyncio.to_thread(method, *args, **({'cancel': cancel} if controlled else {}))
        except asyncio.CancelledError:
            cancel.set()
            raise
        except Exception as exc:
            raise ToolError(str(exc)) from exc

    observe = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    control = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=observe)
    async def get_status() -> dict:
        """Read bridge ownership, dependency status and selected server telemetry."""
        return await invoke(bridge.get_status)

    @server.tool(annotations=observe)
    async def get_player_state() -> dict:
        """Read fresh possessed-pawn position, velocity, movement mode and identity. Resource mapping gaps are explicit."""
        return await invoke(bridge.get_player_state)

    @server.tool(annotations=observe)
    async def get_world_state() -> dict:
        """Read live world lifecycle fields and existing server players/connections."""
        return await invoke(bridge.get_world_state)

    @server.tool(annotations=observe)
    async def capture_screen() -> CallToolResult:
        """Capture the verified game's client window to a local PNG without injecting a DLL or changing focus."""
        result = await invoke(bridge.capture_screen)
        pixels = Path(result['path']).read_bytes()
        content = [TextContent(type='text', text=json.dumps(result))]
        if len(pixels) <= 10 * 1024 * 1024:
            content.append(ImageContent(type='image', data=base64.b64encode(pixels).decode('ascii'), mime_type='image/png'))
        return CallToolResult(content=content, structured_content=result)

    @server.tool(annotations=control)
    async def press_key(key: str, duration: float = .5) -> dict:
        """Hold WASD or space for 0.05..2 seconds through the existing resident input adapter; preserve native before/after evidence."""
        return await invoke(bridge.press_key, key, duration, controlled=True)

    @server.tool(annotations=control)
    async def run_scenario(steps: list[dict], min_horizontal_cm: float = 5, max_vertical_cm: float = 50) -> dict:
        """Run at most 10 allowlisted key steps, total <=10 seconds, recording screenshots and explicit displacement assertions."""
        return await invoke(bridge.run_scenario, steps, min_horizontal_cm, max_vertical_cm, controlled=True)

    @server.tool(annotations=control)
    async def cancel_test() -> dict:
        """Cancel the active bounded action; key cleanup runs even if the MCP request disconnects."""
        return bridge.cancel_test()

    return server


def run(bridge):
    try:
        create_server(bridge).run(transport='stdio')
    finally:
        bridge.cancel_test()
