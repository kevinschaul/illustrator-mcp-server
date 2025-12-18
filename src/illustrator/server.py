import logging
import subprocess
import tempfile
import os
import asyncio
import mcp.types as types
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
import base64
from PIL import Image
import io

logger = logging.getLogger("illustrator_mcp")
current_dir = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    filename=os.path.join(current_dir, "..", "..", "illustrator_mcp_server.log"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,
)

server = Server("illustrator")


RUN_DESCRIPTION = """
Run ExtendScript code in Illustrator.

DO NOT call `alert()` or `$.writeln()` for debugging.

Instead, call `log(message)` each time you want to log a message. I have already defined `log()` for you and will pass in to Illustrator along with the code you provide. All calls to `log()` will be returned in the output.
"""


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="view",
            description="View a screenshot of the Adobe Illustrator window",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="run",
            description=RUN_DESCRIPTION,
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "ExtendScript/JavaScript code to execute",
                    }
                },
                "required": ["code"],
            },
        ),
    ]


def _runInIllustrator(code: str) -> str:
    """Run some ExtendScript in Illustrator"""
    with tempfile.NamedTemporaryFile(suffix=".jsx", delete=False) as tmp_file:
        tmp_file_path = tmp_file.name
        tmp_file.write(code.encode("utf-8"))

    applescript = f"""
        tell application "Adobe Illustrator"
            set user interaction level to never interact
            try
                set result to do javascript file "{tmp_file_path}"
                return result
            on error errMsg
                return "ERROR: " & errMsg
            end try
        end tell
    """

    result = subprocess.run(
        ["osascript", "-e", applescript], capture_output=True, text=True
    )
    output = result.stdout.strip()

    # Clean up the temporary file
    os.unlink(tmp_file_path)

    return output


def captureIllustrator() -> types.CallToolResult:
    screenshot_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            screenshot_path = f.name

        code = """
        if (app.documents.length === 0) {
            throw new Error("No active document found");
        }
        
        var doc = app.activeDocument;
        
        // Set up PNG export options for extended bounds
        var exportOptions = new ExportOptionsPNG24();
        exportOptions.resolution = 150; // Good quality for screenshot purposes
        exportOptions.antiAliasing = true;
        exportOptions.transparency = true;
        exportOptions.artBoardClipping = false; // This captures extended bounds (all objects)
        exportOptions.horizontalScale = 100;
        exportOptions.verticalScale = 100;
        
        // Export the document with extended bounds
        var file = {screenshot_path}
        doc.exportFile(file, ExportType.PNG24, exportOptions);
        """

        output = _runInIllustrator(code)
        # TODO check output for error

        with Image.open(screenshot_path) as img:
            if img.mode in ("RGBA", "LA"):
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85, optimize=True)
            screenshot_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return types.CallToolResult(
            content=[
                types.ImageContent(
                    type="image",
                    mimeType="image/jpeg",
                    data=screenshot_data,
                )
            ],
            isError=False,
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
            isError=True,
        )
    finally:
        if screenshot_path and os.path.exists(screenshot_path):
            os.unlink(screenshot_path)


def runIllustratorScript(code: str) -> types.CallToolResult:
    try:
        wrapped_code = f"""
        var __alert_output = [];
        var log = function(message) {{
            __alert_output.push(message);
        }};

        // TODO why doesn't this work?
        app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS

        {code}

        // The last line becomes the return value to AppleScript
        __alert_output.join("\\\n");
        """

        output = _runInIllustrator(wrapped_code)

        if output.startswith("ERROR:"):
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Error: {output.replace('ERROR:', '').strip()}",
                    )
                ],
                isError=True,
            )

        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text", text=f"Script executed successfully\nOutput: {output}"
                )
            ],
            isError=False,
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
            isError=True,
        )


@server.call_tool()
async def handleCallTool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "view":
        result = captureIllustrator()
        return result.content
    elif name == "run":
        if not arguments or "code" not in arguments:
            return [
                types.TextContent(
                    type="text", text="Error: The 'code' parameter is required"
                )
            ]
        result = runIllustratorScript(arguments["code"])
        return result.content
    else:
        return [types.TextContent(type="text", text=f"Error: Unknown tool '{name}'")]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="illustrator",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
