#!/usr/bin/env python3
"""Bounded socket transport to a private, persistent Vivado Tcl process."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import time

from host_image import from_axi_hex, to_axi_hex


@dataclass(frozen=True)
class Operation:
    bus: str
    kind: str
    address: int
    beats: int = 1
    data: bytes = b""
    separate_words: bool = False

    @property
    def width(self):
        return 8 if self.bus == "M" else 4

    def wire(self):
        if self.bus not in ("M", "D") or self.kind not in ("READ", "WRITE"):
            raise ValueError("Invalid AXI operation")
        limit = 256 if self.bus == "M" else 1
        size = self.width * self.beats
        if (not 1 <= self.beats <= limit or self.address < 0 or
                self.address + size > 1 << (64 if self.bus == "M" else 32) or
                self.address % self.width or (self.address & 4095) + size > 4096):
            raise ValueError("Invalid AXI alignment, length or boundary")
        if (self.kind == "WRITE" and len(self.data) != size) or (self.kind == "READ" and self.data):
            raise ValueError("Invalid AXI data length")
        if self.separate_words and (self.kind != "WRITE" or self.beats < 2):
            raise ValueError("Word separators require a multi-beat WRITE")
        data = to_axi_hex(self.data, self.width) if self.kind == "WRITE" else "-"
        if self.separate_words:
            digits = self.width * 2
            data = "_".join(data[i:i + digits] for i in range(0, len(data), digits))
        return f"{self.bus} {self.kind} {self.address:016x} {self.beats} {data}"


class TransportError(RuntimeError):
    pass


def process_start_options(platform=None):
    """Own a POSIX session; on Windows taskkill follows only our recorded PID."""
    return {"start_new_session": True} if (platform or os.name) != "nt" else {}


def windows_tree_command(pid):
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("An owned positive process PID is required")
    return ["taskkill", "/PID", str(pid), "/T", "/F"]


def stop_owned_tree(process, platform=None):
    """Called only after the owned process failed its graceful exit deadline.

    Never kill by executable name: a shared hw_server or user GUI is not ours.
    Popen(vivado.bat) can own cmd.exe, so terminating only that PID is insufficient.
    """
    if (platform or os.name) == "nt":
        cleanup = subprocess.run(windows_tree_command(process.pid), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 timeout=15, check=False)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise TransportError(f"Owned Vivado tree cleanup failed: {cleanup.stdout!r}") from exc
        if cleanup.returncode:
            raise TransportError(f"Owned Vivado tree cleanup failed: {cleanup.stdout!r}")
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        # A child can ignore TERM even when the session leader already exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


class VivadoTransport:
    def __init__(self, output, vivado="vivado", server="localhost:3121", target="-",
                 device="-", mem_cell="i_jtag_mem", debug_cell="i_jtag_debug",
                 timeout=30.0, startup_timeout=120.0, command=None, probes=None):
        self.output = Path(output)
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.sequence = 0
        self.process = self.sock = self.reader = self.log = self.audit = None
        self.broken = False
        self.arguments = (server, target, device, mem_cell, debug_cell,
                          Path(probes).as_posix() if probes is not None else "-")
        script = Path(__file__).with_name("host_vivado.tcl")
        # Windows CreateProcess does not search PATHEXT; which resolves vivado.bat.
        self.command = command or [shutil.which(vivado) or vivado,
                                   "-mode", "batch", "-nojournal", "-nolog", "-notrace",
                                   "-source", str(script), "-tclargs"]

    def __enter__(self):
        self.output.mkdir(parents=True, exist_ok=True)
        self.log = (self.output / "vivado.log").open("wb")
        self.audit = (self.output / "transport.jsonl").open("w", encoding="ascii")
        token = secrets.token_hex(16)
        try:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(0.2)
                args = self.command + [str(listener.getsockname()[1]), token, *self.arguments]
                self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=self.log,
                                                stderr=subprocess.STDOUT, cwd=self.output,
                                                **process_start_options())
                deadline = time.monotonic() + self.startup_timeout
                while self.sock is None:
                    if self.process.poll() is not None or time.monotonic() >= deadline:
                        raise TransportError("Vivado startup failed/timed out; inspect vivado.log")
                    try:
                        self.sock, _ = listener.accept()
                    except socket.timeout:
                        continue
                self.sock.settimeout(self.timeout)
                self.reader = self.sock.makefile("rb")
                if self._line() != f"READY {token}":
                    raise TransportError("Bad Vivado transport handshake")
            return self
        except BaseException:
            self.close()
            raise

    def _line(self):
        line = self.reader.readline(65537)
        if not line or len(line) > 65536 or not line.endswith(b"\n"):
            raise TransportError("Truncated/oversized Vivado reply")
        return line.decode("ascii").strip()

    def exchange(self, operations):
        if self.broken:
            raise TransportError("Session is unusable; open a new debug-only session")
        if not 1 <= len(operations) <= 256:
            raise ValueError("Batch must contain 1..256 operations")
        lines = [op.wire() for op in operations]
        self.sequence += 1
        seq = self.sequence
        self.audit.write(json.dumps({"batch": seq, "operations": [
            {"bus": op.bus, "kind": op.kind, "address": op.address, "beats": op.beats}
            for op in operations]}) + "\n")
        self.audit.flush()
        try:
            self.sock.sendall((f"BATCH {seq} {len(lines)}\n" + "\n".join(lines) + "\n").encode("ascii"))
            replies = []
            failure = None
            for index, op in enumerate(operations):
                fields = self._line().split()
                if len(fields) != 4 or fields[1:3] != [str(seq), str(index)]:
                    raise TransportError("Mismatched Vivado transaction response")
                status, _, _, payload = fields
                if status == "ERR":
                    failure = bytes.fromhex(payload).decode("utf-8", errors="replace")
                    break
                if status != "OK":
                    raise TransportError("Unknown Vivado transaction status")
                if op.kind == "READ":
                    replies.append(from_axi_hex(payload, op.beats * op.width))
                elif payload == "-":
                    replies.append(b"")
                else:
                    raise TransportError("Unexpected write response")
            if self._line() != f"END {seq}":
                raise TransportError("Missing batch completion")
            if failure:
                raise TransportError(failure)
            self.audit.write(json.dumps({"batch": seq, "checked": True}) + "\n")
            self.audit.flush()
            return replies
        except (OSError, ValueError, TransportError) as exc:
            self.broken = True
            self.audit.write(json.dumps({"batch": seq, "error": str(exc)}) + "\n")
            self.audit.flush()
            raise TransportError(f"AXI batch {seq} failed: {exc}") from exc

    def close(self):
        try:
            if self.sock:
                try:
                    self.sock.sendall(b"QUIT\n")
                except OSError:
                    pass
                if self.reader:
                    self.reader.close()
                self.sock.close()
            if self.process:
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    stop_owned_tree(self.process)
        finally:
            for stream in (self.log, self.audit):
                if stream:
                    stream.close()
            self.sock = self.reader = self.process = self.log = self.audit = None

    def __exit__(self, *args):
        self.close()
