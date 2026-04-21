"""
HUBERT LinkedIn Login Helper
Opens a persistent Chrome window for manual login + CAPTCHA completion
"""
import subprocess
import os
import sys
import time

print("=" * 50)
print("HUBERT LinkedIn Login Helper")
print("=" * 50)
print()
print("Opening Chrome with LinkedIn login page...")
print()

# Try to find Chrome
chrome_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]

chrome = None
for path in chrome_paths:
    if os.path.exists(path):
        chrome = path
        break

if chrome:
    profile_dir = r"C:\Users\Jake\Jarvis\chrome_profile"
    os.makedirs(profile_dir, exist_ok=True)
    subprocess.Popen([
        chrome,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.linkedin.com/login?emailAddress=jakegoncalves2002@gmail.com"
    ])
    print("Chrome opened! LinkedIn login page should appear.")
    print()
    print("Instructions:")
    print("1. Log in with: jakegoncalves2002@gmail.com")
    print("2. Complete any CAPTCHA or verification")
    print("3. Once on LinkedIn feed, come back here")
    print()
    print("Press Enter when you're logged in and ready to apply...")
    input()
    print()
    print("Great! Session saved. Tell HUBERT you're logged in to start applying.")
else:
    print("Chrome not found. Trying to open LinkedIn in default browser...")
    import webbrowser
    webbrowser.open("https://www.linkedin.com/login?emailAddress=jakegoncalves2002@gmail.com")
    print()
    print("Log in to LinkedIn in the browser that just opened.")
    print("Press Enter when done...")
    input()
    print("Ready!")

print()
print("This window will stay open. You can minimize it.")
input("Press Enter to close...")
