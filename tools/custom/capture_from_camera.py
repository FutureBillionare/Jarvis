"""
Auto-generated tool: capture_from_camera
Description: Capture live camera frame using macOS AVFoundation and save as JPEG image
"""

TOOL_DEFINITION = {
    "name": "capture_from_camera",
    "description": 'Capture live camera frame using macOS AVFoundation and save as JPEG image',
    "input_schema": {'type': 'object', 'properties': {'output_path': {'type': 'string', 'description': 'Where to save the JPEG (default: /tmp/camera_frame.jpg)'}, 'timeout_seconds': {'type': 'integer', 'description': 'Max seconds to wait for frame (default: 5)'}}, 'required': []},
}


def run(params: dict) -> str:

    import threading
    import time
    import os
    from pathlib import Path

    output_path = params.get("output_path", "/tmp/camera_frame.jpg")
    timeout = params.get("timeout_seconds", 5)

    try:
        from AVFoundation import (
            AVCaptureSession,
            AVCaptureDevice,
            AVCaptureDeviceInput,
            AVCapturePhotoOutput,
            AVCapturePhoto,
            AVMediaTypeVideo,
            AVCaptureSessionPresetPhoto
        )
        from Foundation import NSAutoreleasePool, NSData
        import AppKit

        captured_image = None
        capture_event = threading.Event()

        class PhotoDelegate:
            def captureOutput_didFinishProcessingPhoto_error_(self, output, photo, error):
                global captured_image
                if error:
                    return
                if photo and hasattr(photo, 'fileDataRepresentation'):
                    captured_image = photo.fileDataRepresentation()
                capture_event.set()

        # Create autorelease pool
        pool = NSAutoreleasePool.alloc().init()

        # Set up capture session
        session = AVCaptureSession.alloc().init()
        session.setSessionPreset_(AVCaptureSessionPresetPhoto)

        # Get default camera
        device = AVCaptureDevice.defaultDeviceWithMediaType_(AVMediaTypeVideo)
        if not device:
            return "Error: No camera device found on this system"

        # Add input
        input_ = AVCaptureDeviceInput.deviceInputWithDevice_error_(device, None)
        if not input_:
            return "Error: Could not create camera input"
        session.addInput_(input_)

        # Add output
        photo_output = AVCapturePhotoOutput.alloc().init()
        session.addOutput_(photo_output)

        # Start session
        session.startRunning()

        # Capture photo
        settings = AVCapturePhotoSettings.alloc().init()
        delegate = PhotoDelegate.alloc().init()
        photo_output.capturePhotoWithSettings_delegate_(settings, delegate)

        # Wait for capture
        if capture_event.wait(timeout=timeout):
            session.stopRunning()

            if captured_image:
                # Write to file
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(captured_image)
                file_size = os.path.getsize(output_path) / 1024
                return f"✅ Camera frame captured: {output_path} ({file_size:.1f}KB)"

        session.stopRunning()
        return "Error: No frame captured within timeout"

    except ImportError as e:
        return f"Error: pyobjc not properly installed: {e}"
    except Exception as e:
        return f"Error during capture: {e}"



TOOLS = [(TOOL_DEFINITION, run)]
