"""MCP stdio endpoint. One host-configured principal per process."""
import asyncio
import json
import os
import contextlib
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from .core import Adapter

SPECS = {
 'checkpoint': ('Snapshot an allowlisted SQLite memory namespace into SGit.', {'namespace': {'type': 'string'}}),
 'inspect': ('Verify a checkpoint and return metadata, never keys.', {'checkpoint_id': {'type': 'string'}}),
 'restore': ('Restore a verified checkpoint to a new isolated workspace.', {'checkpoint_id': {'type': 'string'}, 'workspace': {'type': 'string'}}),
 'close_run': ('Delete local checkpoint and key record; restored copies remain.', {'checkpoint_id': {'type': 'string'}}),
}

async def serve():
    adapter = Adapter(os.environ['SGIT_RUV_CONFIG'])
    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[types.Tool(name=n, description=d, inputSchema={
            'type': 'object', 'properties': p, 'required': list(p), 'additionalProperties': False}) for n,(d,p) in SPECS.items()])
    async def call_tool(ctx, params):
        try:
            if params.name not in SPECS:
                raise ValueError('Unknown tool')
            args = params.arguments or {}
            if set(args) != set(SPECS[params.name][1]) or not all(isinstance(v,str) for v in args.values()):
                raise ValueError('Invalid arguments')
            # SGit may print informational output. Keep stdout exclusively MCP.
            def invoke():
                with contextlib.redirect_stdout(sys.stderr):
                    return getattr(adapter, params.name)(**args)
            result = await asyncio.to_thread(invoke)
            return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(result))])
        except Exception as e:
            # Do not leak dependency errors containing private paths or credentials.
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text',text=type(e).__name__ + ': operation failed; check configuration, policy and integrity')])
    server = Server('sgit-ruv-memory', version='0.1.0', on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

def main():
    os.umask(0o077)
    asyncio.run(serve())

if __name__ == '__main__':
    main()
