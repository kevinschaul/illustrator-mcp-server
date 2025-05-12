import subprocess
import tempfile
import sys
import os
import asyncio
import mcp.types as types
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
import base64
from PIL import Image
import io


server = Server("illustrator")


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
            description="Run ExtendScript code in Illustrator",
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


def captureIllustrator() -> list[types.TextContent | types.ImageContent]:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        screenshot_path = f.name
    try:
        capture_script = (
            """
            -- Save the current active application
            tell application "System Events"
                set frontApp to name of first process where frontmost is true
            end tell

            -- Activate Illustrator and wait for it to come to front
            tell application "Adobe Illustrator"
                activate
                delay 1.5
            end tell

            -- Get window position and dimensions
            tell application "System Events"
                tell process "Adobe Illustrator"
                    try
                        set frontWindow to first window
                        set {x, y} to position of frontWindow
                        set {width, height} to size of frontWindow

                        -- Format coordinates for screencapture
                        set windowInfo to "" & x & "," & y & "," & width & "," & height

                        -- Take the screenshot directly from AppleScript while Illustrator is frontmost
                        do shell script "screencapture -R " & quoted form of windowInfo & " -x '" & "%s" & "'"

                        -- Return coordinates for verification
                        set captureResult to "SUCCESS:" & windowInfo
                    on error errMsg
                        set captureResult to "ERROR: " & errMsg
                    end try
                end tell
            end tell

            -- Return to the previous application if it wasn't Illustrator
            if frontApp is not "Adobe Illustrator" then
                tell application frontApp
                    activate
                end tell
            end if

            return captureResult
        """
            % screenshot_path
        )

        capture_result = subprocess.run(
            ["osascript", "-e", capture_script], capture_output=True, text=True
        )

        if capture_result.returncode != 0:
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to capture Illustrator window: {capture_result.stderr}",
                )
            ]

        result_info = capture_result.stdout.strip()

        # Check if there was an error message in the AppleScript output
        if result_info.startswith("ERROR:"):
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to capture Illustrator: {result_info}",
                )
            ]

        # Extract the window coordinates from the SUCCESS message
        if result_info.startswith("SUCCESS:"):
            window_info = result_info.replace("SUCCESS:", "")
            print(f"Captured Illustrator window: {window_info}", file=sys.stderr)
        else:
            print(f"Unexpected result from AppleScript: {result_info}", file=sys.stderr)

        # Make sure the screenshot file exists and has content
        if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) == 0:
            return [
                types.TextContent(
                    type="text",
                    text="Screenshot file was not created or is empty",
                )
            ]

        with Image.open(screenshot_path) as img:
            if img.mode in ("RGBA", "LA"):
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85, optimize=True)
            compressed_data = buffer.getvalue()
            screenshot_data = base64.b64encode(compressed_data).decode("utf-8")

        return [
            types.ImageContent(
                type="image",
                mimeType="image/jpeg",
                data=screenshot_data,
            )
        ]
    except Exception as e:
        # Catch any other exceptions
        return [
            types.TextContent(
                type="text",
                text=f"Exception while capturing Illustrator window: {str(e)}",
            )
        ]
    finally:
        if os.path.exists(screenshot_path):
            os.unlink(screenshot_path)


def runIllustratorScript(code: str) -> list[types.TextContent]:
    script = code.replace('"', '\\"').replace("\n", "\\n")

    applescript = f"""
        tell application "Adobe Illustrator"
            do javascript "{script}"
        end tell
    """

    result = subprocess.run(
        ["osascript", "-e", applescript], capture_output=True, text=True
    )

    if result.returncode != 0:
        return [
            types.TextContent(
                type="text", text=f"Error executing script: {result.stderr}"
            )
        ]

    success_message = "Script executed successfully"
    if result.stdout:
        success_message += f"\nOutput: {result.stdout}"

    return [types.TextContent(type="text", text=success_message)]


@server.call_tool()
async def handleCallTool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "view":
        return captureIllustrator()
    elif name == "run":
        if not arguments or "code" not in arguments:
            return [types.TextContent(type="text", text="No code provided")]
        return runIllustratorScript(arguments["code"])
    else:
        raise ValueError(f"Unknown tool: {name}")


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
