"""Meridian's Windows desktop entry point. Start and stop the loopback service with its Edge window."""
import ctypes
from ctypes import wintypes as wt
import json
import logging
import msvcrt
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
VERIFY = "--verify" in sys.argv or os.environ.get("MERIDIAN_LAUNCH_VERIFY") == "1"
USER = ctypes.windll.user32
CALLBACK = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
USER.EnumWindows.argtypes = [CALLBACK, wt.LPARAM]
USER.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
USER.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
USER.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
USER.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]


def owner(hwnd):
    pid = wt.DWORD()
    USER.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window(pids):
    matching = []
    @CALLBACK
    def inspect(hwnd, ignored):
        if owner(hwnd) in pids and USER.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            kind = ctypes.create_unicode_buffer(80)
            USER.GetWindowTextW(hwnd, title, len(title))
            USER.GetClassNameW(hwnd, kind, len(kind))
            if "Meridian Desk" in title.value and kind.value.startswith("Chrome_WidgetWin"):
                matching.append(hwnd)
        return True
    USER.EnumWindows(inspect, 0)
    return matching[0] if matching else 0


def profile_owners(profile):
    script = """$arg='--user-data-dir='+$env:MERIDIAN_EDGE_PROFILE
Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object {
$_.CommandLine -and $_.CommandLine.IndexOf($arg,[StringComparison]::OrdinalIgnoreCase) -ge 0 -and
$_.CommandLine -notmatch '(?:^|\\s)--type=' } | ForEach-Object { $_.ProcessId }"""
    ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(ps), "-NoProfile", "-NonInteractive", "-Command", script],
                            env={**os.environ, "MERIDIAN_EDGE_PROFILE":str(profile)}, capture_output=True,
                            text=True, timeout=7, creationflags=subprocess.CREATE_NO_WINDOW)
    return {int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdecimal()}


def focus(file):
    for _ in range(100):
        try:
            file.seek(1)
            hwnd, pid = json.loads(file.read())
            if hwnd and owner(hwnd) == pid:
                if USER.IsIconic(hwnd):
                    USER.ShowWindow(hwnd, 9)
                USER.SetForegroundWindow(hwnd)
                return
        except (ValueError, OSError):
            pass
        time.sleep(.15)
    raise RuntimeError("The previous Meridian window is starting or closing. Open the shortcut again in a moment.")


def publish(file, hwnd, pid):
    file.seek(1)
    file.truncate()
    file.write(json.dumps([hwnd,pid]).encode())
    file.flush()


def launch(profile, lockfile):
    from desk import Desk, serve
    edge = next((p for k in ("ProgramFiles(x86)", "ProgramFiles") if os.environ.get(k)
                 for p in [Path(os.environ[k]) / "Microsoft/Edge/Application/msedge.exe"] if p.is_file()), None)
    if edge is None:
        raise RuntimeError("Microsoft Edge is required. Windows could not locate the installed browser.")
    if VERIFY:
        os.environ["MERIDIAN_BROKER"] = "off"
    db = ROOT / ("tests/launcher-verification.sqlite3" if VERIFY else "data/desk.sqlite3")
    desk = Desk(db, verification=VERIFY)
    token = secrets.token_urlsafe(32)
    server = serve(desk, token)
    ready = threading.Event()
    class Handler(server.RequestHandlerClass):
        def reply(self, code, content, ctype="application/json; charset=utf-8"):
            super().reply(code, content, ctype)
            if (code == 200 and self.path.startswith("/api/state?") and isinstance(content, dict)
                    and content.get("market") and "Edg/" in self.headers.get("User-Agent", "")):
                ready.set()
    server.RequestHandlerClass = Handler
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":.15}, daemon=True)
    hwnd = pid = 0
    success = False
    thread.start()
    try:
        desk.start()
        port = server.server_port
        url = f"http://127.0.0.1:{port}/#{token}" + ("~verify" if VERIFY else "")
        args = [str(edge), "--user-data-dir="+str(profile), "--disk-cache-dir="+str(profile/"disk-cache"),
                "--disable-background-mode", "--no-first-run", "--no-default-browser-check",
                "--disable-sync", "--disable-extensions", "--window-size=1400,900", "--app="+url]
        env = {k:v for k,v in os.environ.items() if not any(
            tag in k.upper() for tag in ("SECRET","API_KEY","TOKEN","PASSWORD","CREDENTIAL"))}
        proc = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pids = {proc.pid}
        handoff = False
        for _ in range(320):
            hwnd = window(pids)
            if hwnd:
                break
            if proc.poll() is not None and not handoff:
                pids.update(profile_owners(profile))
                handoff = True
            time.sleep(.15)
        if not hwnd:
            raise RuntimeError("Edge did not open the Meridian app window.")
        pid = owner(hwnd)
        publish(lockfile, hwnd, pid)
        logging.info("Window opened. PID %d, loopback port %d.", pid, port)
        if VERIFY:
            if not ready.wait(25):
                raise RuntimeError("The browser did not load authenticated demo data.")
            USER.PostMessageW(hwnd, 0x0010, 0, 0)
        timeout = time.monotonic() + 20
        while owner(hwnd) == pid:
            if VERIFY and time.monotonic() > timeout:
                raise RuntimeError("The verification window did not close.")
            time.sleep(.2)
        success = True
    finally:
        if not success and hwnd and pid and owner(hwnd) == pid:
            USER.PostMessageW(hwnd, 0x0010, 0, 0)
        server.shutdown()
        server.server_close()
        thread.join(3)
        desk.stop()
        logging.info("Local HTTP service stopped.")
    if VERIFY:
        with socket.socket() as check:
            check.settimeout(.5)
            if check.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("Loopback socket remained open after window closure.")
        (ROOT/"logs/launcher-verification.json").write_text(json.dumps({
            "utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"runtime":sys.executable,
            "edge":str(edge),"profile":str(profile),"database":str(db),"pid":pid,
            "authenticated_demo_loaded":ready.is_set(),"window_closed":True,"service_closed":True
        },indent=2),encoding="utf8")


def main():
    if ROOT.drive.upper() != "E:":
        raise RuntimeError("Meridian Desk requires its project directory on E:.")
    os.chdir(ROOT)
    sys.dont_write_bytecode=True
    profile = ROOT/"cache"/("edge-launch-verify" if VERIFY else "edge")
    temp = ROOT/"cache/temp"
    for folder in (profile,temp,ROOT/"logs"):
        folder.mkdir(parents=True,exist_ok=True)
    os.environ.update(TEMP=str(temp),TMP=str(temp),PYTHONDONTWRITEBYTECODE="1")
    logging.basicConfig(filename=ROOT/"logs/launcher.log",encoding="utf8",level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    with (profile/"meridian.session").open("a+b",buffering=0) as lockfile:
        lockfile.seek(0)
        try:
            msvcrt.locking(lockfile.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            focus(lockfile)
            return
        publish(lockfile, 0, 0)
        launch(profile,lockfile)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("Launcher failed")
        if not VERIFY:
            USER.MessageBoxW(None,f"{exc}\n\nSee {ROOT/'logs/launcher.log'}.","Meridian Desk",0x10)
        raise SystemExit(1)
