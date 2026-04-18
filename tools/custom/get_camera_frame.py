"""
Auto-generated tool: get_camera_frame
Description: Get a live camera frame via Python subprocess calling swift CLI tool
"""

TOOL_DEFINITION = {
    "name": "get_camera_frame",
    "description": 'Get a live camera frame via Python subprocess calling swift CLI tool',
    "input_schema": {'type': 'object', 'properties': {'output_path': {'type': 'string', 'description': 'Where to save JPEG'}}, 'required': []},
}


def run(params: dict) -> str:

    import subprocess
    import os
    import tempfile

    output_path = params.get("output_path", "/tmp/camera_frame.jpg")

    # Create a Swift script to capture camera
    swift_script = """
    import AVFoundation
    import Foundation
    import CoreImage

    let outputPath = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "/tmp/swift_camera.jpg"

    let session = AVCaptureSession()
    session.sessionPreset = .photo

    guard let device = AVCaptureDevice.default(for: .video) else {
        print("ERROR: No camera found")
        exit(1)
    }

    do {
        try device.lockForConfiguration()
        device.unlockForConfiguration()

        let input = try AVCaptureDeviceInput(device: device)
        session.addInput(input)

        let output = AVCapturePhotoOutput()
        session.addOutput(output)

        session.startRunning()

        // Wait a moment for camera to warm up
        usleep(1_000_000) // 1 second

        let settings = AVCapturePhotoSettings()

        var capturedImage: AVCapturePhoto?
        let semaphore = DispatchSemaphore(value: 0)

        class PhotoDelegate: NSObject, AVCapturePhotoCaptureDelegate {
            var photo: AVCapturePhoto?
            let semaphore: DispatchSemaphore

            init(semaphore: DispatchSemaphore) {
                self.semaphore = semaphore
            }

            func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
                if error == nil {
                    self.photo = photo
                }
                semaphore.signal()
            }
        }

        let delegate = PhotoDelegate(semaphore: semaphore)
        output.capturePhoto(with: settings, delegate: delegate)

        _ = semaphore.wait(timeout: .now() + 5.0)

        session.stopRunning()

        if let photo = delegate.photo, let data = photo.fileDataRepresentation() {
            try data.write(toFile: outputPath, options: .atomic)
            print("SUCCESS")
        } else {
            print("ERROR: Failed to get photo data")
            exit(1)
        }

    } catch {
        print("ERROR: \\(error)")
        exit(1)
    }
    """

    # Write swift script to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False) as f:
        f.write(swift_script)
        swift_file = f.name

    try:
        result = subprocess.run(
            ['swift', swift_file, output_path],
            capture_output=True,
            text=True,
            timeout=15
        )

        if "SUCCESS" in result.stdout and os.path.exists(output_path):
            size = os.path.getsize(output_path) / 1024
            return f"✅ Camera frame saved to {output_path} ({size:.1f}KB)"
        else:
            return f"Error: {result.stdout}{result.stderr}"

    finally:
        if os.path.exists(swift_file):
            os.unlink(swift_file)



TOOLS = [(TOOL_DEFINITION, run)]
