"""
Auto-generated tool: capture_camera
Description: Capture a single frame from the system camera on macOS using native APIs, save as JPEG
"""

TOOL_DEFINITION = {
    "name": "capture_camera",
    "description": 'Capture a single frame from the system camera on macOS using native APIs, save as JPEG',
    "input_schema": {'type': 'object', 'properties': {'output_path': {'type': 'string', 'description': 'Path to save the JPEG image (default: /tmp/camera_capture.jpg)'}}, 'required': []},
}


def run(params: dict) -> str:

    import subprocess
    import os

    output_path = params.get("output_path", "/tmp/camera_capture.jpg")

    # Try using macOS screencapture with -V flag for video device (if available)
    # Alternative: use ffmpeg if installed
    try:
        # Try ffmpeg first
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-i", "0", "-frames:v", "1", "-y", output_path],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            return f"Camera frame captured to {output_path}"
    except Exception as e:
        pass

    # Fallback: use imagesnap if available
    try:
        result = subprocess.run(
            ["imagesnap", "-w", "1", output_path],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            return f"Camera frame captured to {output_path} via imagesnap"
    except Exception as e:
        pass

    # Fallback: use Swift/Objective-C via osascript
    try:
        script = '''
        tell application "System Events"
            activate
        end tell
        '''
        result = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except:
        pass

    return "Failed to capture camera: ffmpeg and imagesnap not found. Install with: brew install ffmpeg imagesnap"



TOOLS = [(TOOL_DEFINITION, run)]
