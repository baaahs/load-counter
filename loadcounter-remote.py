#!/usr/bin/env python3
import argparse
import curses
import os
import queue
import shlex
import subprocess
import sys
import textwrap
import threading
import time
from collections import deque


DEFAULT_HOST = os.environ.get("LOADCOUNTER_PI", "jul@raspberry.local")
DEFAULT_STATE_DIR = "/var/tmp/loadcounter"


REMOTE_WRITER = r"""
import json
import os
import sys
import time

state_dir = sys.argv[1]
command_path = os.path.join(state_dir, "keyboard-command.json")


def write_command(command):
    payload = {
        "id": str(time.time_ns()),
        "command": command,
        "created_at": time.time(),
    }
    temp_path = f"{command_path}.tmp"
    os.makedirs(state_dir, exist_ok=True)
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, command_path)


print("ready", flush=True)
for line in sys.stdin:
    command = line.strip()
    if not command:
        continue
    if command == "__quit__":
        break
    try:
        write_command(command)
    except Exception as exc:
        print(f"error {command}: {exc}", file=sys.stderr, flush=True)
    else:
        print(f"ok {command}", flush=True)
"""


KEY_HELP = (
    ("Return", "open/select"),
    ("Esc", "back/exit menu"),
    ("Arrows", "move/adjust"),
    ("Space or d", "toggle debug"),
    ("0-9 . Backspace", "edit values"),
    ("r", "reset count"),
    ("--send learn", "start learning"),
    ("--send learn_calibrate/count/end/cancel", "control learning"),
    ("y / n", "answer save prompt"),
)


COMMAND_ALIASES = {
    "return": "enter",
    "enter": "enter",
    "esc": "esc",
    "escape": "esc",
    "space": "space",
    "debug": "space",
    "d": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "backspace": "backspace",
    "delete": "backspace",
    "del": "backspace",
    ".": "dot",
    "dot": "dot",
    "r": "count_reset",
    "reset": "count_reset",
    "count_reset": "count_reset",
    "learn": "learn_start",
    "learn_start": "learn_start",
    "start_learning": "learn_start",
    "learning_start": "learn_start",
    "learn_calibrate": "learn_calibrate",
    "learning_calibrate": "learn_calibrate",
    "learn_count": "learn_count",
    "learning_count": "learn_count",
    "learn_end": "learn_end",
    "learn_stop": "learn_end",
    "stop_learning": "learn_end",
    "learning_stop": "learn_end",
    "learn_cancel": "learn_cancel",
    "cancel_learning": "learn_cancel",
    "brightness_up": "brightness_up",
    "brightness_down": "brightness_down",
    "sensor_order_toggle": "sensor_order_toggle",
    "menu_cancel": "menu_cancel",
    "cancel_menu": "menu_cancel",
    "close_menu": "menu_cancel",
    "cancel": "menu_cancel",
    "yes": "yes",
    "y": "yes",
    "no": "no",
    "n": "no",
}


def normalize_command(token):
    token = token.strip().lower()
    if not token:
        raise ValueError("empty command")
    if token.startswith("digit:") and token[6:].isdigit() and len(token[6:]) == 1:
        return token
    if token.startswith("brightness:"):
        value = token.split(":", 1)[1]
        try:
            percent = int(float(value))
        except ValueError as exc:
            raise ValueError(f"invalid brightness value: {value}") from exc
        if percent < 1 or percent > 100:
            raise ValueError("brightness must be between 1 and 100")
        return f"brightness:{percent}"
    if token.isdigit() and len(token) == 1:
        return f"digit:{token}"
    if token in COMMAND_ALIASES:
        return COMMAND_ALIASES[token]
    raise ValueError(f"unknown command: {token}")


class RemoteKeyboard:
    def __init__(self, host, state_dir, ssh_options, dry_run=False, connect_timeout=8.0):
        self.host = host
        self.state_dir = state_dir
        self.ssh_options = ssh_options
        self.dry_run = dry_run
        self.connect_timeout = connect_timeout
        self.process = None
        self.events = queue.Queue()
        self.history = deque(maxlen=6)
        self._threads = []

    def start(self):
        if self.dry_run:
            self.history.append(("local", "dry-run ready"))
            return

        remote_command = "python3 -u -c {} {}".format(
            shlex.quote(REMOTE_WRITER),
            shlex.quote(self.state_dir),
        )
        ssh_command = [
            "ssh",
            "-T",
            "-o",
            f"ConnectTimeout={int(self.connect_timeout)}",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=2",
        ]
        for option in self.ssh_options:
            ssh_command.extend(["-o", option])
        ssh_command.extend([self.host, remote_command])

        self.process = subprocess.Popen(
            ssh_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._start_reader(self.process.stdout, "remote")
        self._start_reader(self.process.stderr, "error")
        self._wait_until_ready()

    def _start_reader(self, stream, source):
        thread = threading.Thread(target=self._read_pipe, args=(stream, source), daemon=True)
        thread.start()
        self._threads.append(thread)

    def _read_pipe(self, stream, source):
        try:
            for line in stream:
                self.events.put((source, line.rstrip()))
        finally:
            self.events.put((source, "closed"))

    def _wait_until_ready(self):
        deadline = time.monotonic() + self.connect_timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self._drain_events()
                details = "; ".join(message for _, message in self.history)
                raise RuntimeError(f"ssh writer exited before ready: {details}")
            try:
                source, message = self.events.get(timeout=0.1)
            except queue.Empty:
                continue
            self.history.append((source, message))
            if source == "remote" and message == "ready":
                return
        raise RuntimeError(f"timed out connecting to {self.host}")

    def _drain_events(self):
        while True:
            try:
                source, message = self.events.get_nowait()
            except queue.Empty:
                return
            self.history.append((source, message))

    def poll_messages(self):
        self._drain_events()
        return list(self.history)

    def send(self, command):
        if self.dry_run:
            self.history.append(("local", f"would send {command}"))
            return
        if self.process.poll() is not None:
            raise RuntimeError("ssh writer is not running")
        self.process.stdin.write(f"{command}\n")
        self.process.stdin.flush()

    def close(self):
        if self.dry_run or self.process is None:
            return
        if self.process.poll() is None:
            try:
                self.process.stdin.write("__quit__\n")
                self.process.stdin.flush()
                self.process.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()


def key_to_command(key):
    if key in (3, ord("q"), ord("Q")):
        return None, True
    if key in (curses.KEY_ENTER, 10, 13):
        return "enter", False
    if key == 27:
        return "esc", False
    if key == curses.KEY_UP:
        return "up", False
    if key == curses.KEY_DOWN:
        return "down", False
    if key == curses.KEY_LEFT:
        return "left", False
    if key == curses.KEY_RIGHT:
        return "right", False
    if key in (curses.KEY_BACKSPACE, 8, 127):
        return "backspace", False
    if key == ord(" "):
        return "space", False
    if key == ord("."):
        return "dot", False
    if ord("0") <= key <= ord("9"):
        return f"digit:{chr(key)}", False

    try:
        char = chr(key).lower()
    except (TypeError, ValueError):
        return None, False

    if char == "d":
        return "space", False
    if char == "r":
        return "count_reset", False
    if char == "y":
        return "yes", False
    if char == "n":
        return "no", False
    return None, False


def add_line(window, row, col, text, attr=0):
    height, width = window.getmaxyx()
    if row < 0 or row >= height or col >= width:
        return
    available = max(0, width - col - 1)
    if available == 0:
        return
    window.addstr(row, col, text[:available], attr)


def render(window, remote, status):
    window.erase()
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    add_line(window, 0, 0, "Loadcounter Remote Keyboard", curses.A_BOLD)
    add_line(window, 2, 0, f"Host: {remote.host}")
    add_line(window, 3, 0, "Quit this controller: q or Ctrl-C")
    add_line(window, 5, 0, "Keys sent to the Pi:", curses.A_BOLD)
    for index, (key, description) in enumerate(KEY_HELP, start=6):
        add_line(window, index, 2, f"{key:<16} {description}")

    add_line(window, 15, 0, f"Status: {status}")
    add_line(window, 17, 0, "Connection log:", curses.A_BOLD)
    for index, (source, message) in enumerate(remote.poll_messages()[-5:], start=18):
        add_line(window, index, 2, f"{source}: {message}")
    window.refresh()


def run_interactive(stdscr, remote):
    curses.noecho()
    curses.cbreak()
    curses.set_escdelay(50)
    stdscr.keypad(True)

    status = "connected"
    render(stdscr, remote, status)
    while True:
        key = stdscr.getch()
        command, should_quit = key_to_command(key)
        if should_quit:
            status = "closing"
            render(stdscr, remote, status)
            return
        if command is None:
            status = f"ignored key code {key}"
            render(stdscr, remote, status)
            continue
        try:
            remote.send(command)
        except Exception as exc:
            status = f"send failed: {exc}"
        else:
            status = f"sent {command}"
        render(stdscr, remote, status)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Control the Raspberry Pi loadcounter from this Mac keyboard.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              ./loadcounter-remote.py
              ./loadcounter-remote.py --send esc no enter
              ./loadcounter-remote.py --send down down enter --delay 0.35
              ./loadcounter-remote.py --dry-run --send enter down up
            """
        ),
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"SSH host for the Pi (default: {DEFAULT_HOST})")
    parser.add_argument(
        "--state-dir",
        default=DEFAULT_STATE_DIR,
        help=f"remote command state directory (default: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument("--ssh-option", action="append", default=[], help="extra ssh -o option")
    parser.add_argument("--dry-run", action="store_true", help="print commands without connecting to the Pi")
    parser.add_argument("--ping", action="store_true", help="connect to the Pi without sending a command")
    parser.add_argument(
        "--send",
        nargs="+",
        metavar="COMMAND",
        help="send one or more commands, then exit",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="seconds to wait between one-shot commands (default: 0.25)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        commands = [normalize_command(token) for token in args.send or []]
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    remote = RemoteKeyboard(args.host, args.state_dir, args.ssh_option, dry_run=args.dry_run)
    try:
        remote.start()
        if args.ping:
            print(f"Connected to {args.host}; no command sent.")
            return 0
        if commands:
            for command in commands:
                remote.send(command)
                print(f"sent {command}")
                time.sleep(args.delay)
            return 0
        if not sys.stdin.isatty():
            print("Interactive mode needs a terminal. Use --send for one-shot commands.", file=sys.stderr)
            return 2
        curses.wrapper(run_interactive, remote)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"loadcounter remote failed: {exc}", file=sys.stderr)
        return 1
    finally:
        remote.close()


if __name__ == "__main__":
    raise SystemExit(main())
