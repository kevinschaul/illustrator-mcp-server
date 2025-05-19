# Illustrator MCP Server

_Forked from [@spencerhhuberg/illustrator-mcp-server](https://github.com/spencerhhubert/illustrator-mcp-server)_

Adobe Illustrator is compatible with JavaScript. In fact, some super big stuff you need to programmatically generate with these scripts. Bots are good at JavaScript.

This MCP server let's bots send scripts straight to Illustrator and look at the result.

Since it depends on AppleScript, it's only compatible with MacOS. and I've only tested it with Claude Desktop.
`~/Library/Application\ Support/Claude/claude_desktop_config.json`

```
{
    "mcpServers": {
        "illustrator": {
            "command": "uv",
            "args": [
                "--directory",
                "/Users/you/code/mcp/illustrator-mcp-server",
                "run",
                "illustrator"
            ]
        }
    }
}
```

## Testing

To view logs (when connected to Claude Desktop):

```bash
tail -n 20 -F ~/Library/Logs/Claude/mcp*.log
```

Test this MCP server interactively with [inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector -- uv run illustrator
```

Run some code in Illustrator with:

```bash
npx @modelcontextprotocol/inspector --cli uv run illustrator --method tools/call --tool-name run --tool-arg code='log("hi")'
```
