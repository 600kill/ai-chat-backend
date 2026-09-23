"""CLI command to initialize tools from LangGraph to database."""

import asyncio
import click


@click.command()
def init_tools():
    """Initialize tools from LangGraph to database."""
    from app.services.tool_initializer import init_tools_command
    
    asyncio.run(init_tools_command())


if __name__ == "__main__":
    init_tools()