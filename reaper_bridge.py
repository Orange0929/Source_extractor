"""Locate REAPER and hand persistent media to its existing instance."""
import json
import os
from pathlib import Path
import shutil
import subprocess


def valid_executable(path):
    path = Path(path)
    return path.is_file() and path.name.lower() in ('reaper.exe', 'reaper')


def find_reaper(root):
    candidates = []
    try:
        preferences = json.loads((Path(root)/'.desktop'/'preferences.json').read_text(encoding='utf-8'))
        if preferences.get('reaper_executable'):
            candidates.append(Path(preferences['reaper_executable']))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\App Paths\reaper.exe', 0, winreg.KEY_READ|view) as key:
                        candidates.append(Path(winreg.QueryValueEx(key, '')[0].strip('"')))
                except OSError:
                    pass
        for variable in ('ProgramW6432','ProgramFiles','ProgramFiles(x86)'):
            folder = os.environ.get(variable)
            if folder:
                candidates.extend((Path(folder)/'REAPER (x64)'/'reaper.exe', Path(folder)/'REAPER'/'reaper.exe'))
    found = shutil.which('reaper.exe' if os.name == 'nt' else 'reaper')
    if found:
        candidates.append(Path(found))
    return next((p.resolve() for p in candidates if valid_executable(p)), None)


def launch_reaper(executable, media):
    # REAPER >=6.80 accepts media on the command line and -nonewinst routes it
    # to an already running instance. No shell, extensions, or Python plugin.
    return subprocess.Popen([str(executable), '-nonewinst', str(Path(media).resolve())],
                            cwd=str(Path(executable).parent))
