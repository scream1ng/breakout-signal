"""
asgi.py — ASGI entrypoint dispatching MCP paths to the MCP server and
everything else to the existing FastAPI app, in one uvicorn process.

Plain conditional dispatch on an explicit path set, not Mount('/mcp', ...):
the streamable endpoint is already the full path '/mcp', so mounting it under
the same prefix double-strips the segment and the bare path never matches —
it falls through to the SPA catch-all in main_app.py and answers 405.

Lifespan goes only to the FastAPI app, which owns the DB and scheduler startup.
The MCP app is stateless_http and has no lifespan work of its own.

Deploy:  uvicorn asgi:app --host 0.0.0.0 --port $PORT
"""

from main_app import app as fastapi_app
from mcp_server import http_app as mcp_app

_MCP_PATHS = {'/mcp'}


async def app(scope, receive, send):
    if scope['type'] == 'http' and scope['path'] in _MCP_PATHS:
        await mcp_app(scope, receive, send)
    else:
        await fastapi_app(scope, receive, send)
