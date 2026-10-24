"""python -m matchvoice.mcp_server  (stdio transport, no key needed)"""
from .server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
