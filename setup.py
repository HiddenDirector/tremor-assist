"""py2app build: .venv/bin/python setup.py py2app"""

from setuptools import setup

APP = ["app_launch.py"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/AppIcon.icns",
    "packages": ["tremor_assist"],
    "includes": ["objc", "Foundation", "AppKit", "Quartz"],
    "plist": {
        "CFBundleName": "TremorAssist",
        "CFBundleDisplayName": "TremorAssist",
        "CFBundleIdentifier": "com.HiddenDirector.tremorassist",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": "TremorAssist smooths your mouse and keyboard input.",
    },
}

setup(
    name="TremorAssist",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
