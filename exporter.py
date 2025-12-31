import os
import shutil
import threading
import queue
import time
import subprocess
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

DEFAULT_SUBFOLDERS = [
    "WhatsApp Images",
    "WhatsApp Video",
    "WhatsApp Documents",
    "WhatsApp Audio",
    "WhatsApp Voice Notes",
    "Animated Gifs",
]

DATE_FMT = "%Y-%m-%d"


def parse_yyyy_mm_dd(s: str) -> datetime:
    """Parse strict YYYY-MM-DD date."""
    return datetime.strptime(s.strip(), DATE_FMT)


def detect_media_root(source_root: str) -> str:
    candidate = os.path.join(source_root, "Media")
    if os.path.isdir(candidate):
        return candidate
    return source_root


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def unique_destination_path(dst_path: str) -> str:
    if not os.path.exists(dst_path):
        return dst_path

    base, ext = os.path.splitext(dst_path)
    i = 1
    while True:
        candidate = f"{base}__dup{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


# -------------------------
# ADB helpers (Android USB)
# -------------------------

def adb_path_guess() -> str:
    return "adb"


def adb_run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def adb_list_devices(adb: str) -> list[str]:
    p = adb_run([adb, "devices"])
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "adb devices failed")

    devices = []
    lines = p.stdout.strip().splitlines()
    for line in lines[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def adb_shell(adb: str, device: str, cmd: str) -> str:
    p = adb_run([adb, "-s", device, "shell", cmd])
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or f"adb shell failed: {cmd}")
    return p.stdout


def adb_shell_sh(adb: str, device: str, sh_cmd: str) -> str:
    return adb_shell(adb, device, f"sh -c '{sh_cmd}'")


def adb_pull(adb: str, device: str, remote_path: str, local_path: str) -> None:
    ensure_dir(os.path.dirname(local_path))
    p = adb_run([adb, "-s", device, "pull", remote_path, local_path])
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or f"adb pull failed: {remote_path}")


def adb_stat_mtime_epoch(adb: str, device: str, remote_path: str) -> int:
    rp = remote_path.replace('"', '\\"')
    out = adb_shell_sh(
        adb,
        device,
        f'toybox stat -c %Y "{rp}" 2>/dev/null || stat -c %Y "{rp}"'
    ).strip()
    return int(out)


def adb_path_exists(adb: str, device: str, remote_path: str) -> bool:
    rp = remote_path.replace('"', '\\"')
    out = adb_shell_sh(adb, device, f'ls "{rp}" >/dev/null 2>&1; echo $?').strip()
    return out.endswith("0")


def adb_find_whatsapp_media_roots(adb: str, device: str) -> list[str]:
    candidates = [
        "/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media",
        "/storage/emulated/0/WhatsApp/Media",
    ]
    roots = []
    for c in candidates:
        if adb_path_exists(adb, device, c):
            roots.append(c)
    return roots


def adb_find_files(adb: str, device: str, remote_dir: str) -> list[str]:
    rd = remote_dir.replace('"', '\\"')
    out = adb_shell_sh(adb, device, f'find "{rd}" -type f 2>/dev/null')
    return [line.strip() for line in out.splitlines() if line.strip()]


def adb_count_files(adb: str, device: str, remote_dir: str) -> int:
    rd = remote_dir.replace('"', '\\"')
    out = adb_shell_sh(adb, device, f'find "{rd}" -type f 2>/dev/null | wc -l').strip()
    try:
        return int(out)
    except Exception:
        return 0


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WhatsApp Media Exporter (Date Range)")
        self.geometry("960x720")
        self.minsize(880, 620)

        self._try_set_icon()

        # Threading / communication
        self._worker_thread = None
        self._ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self._cancel_event = threading.Event()

        # State counters
        self._scanned = 0
        self._matched = 0
        self._errors = 0

        # ADB state
        self.adb = adb_path_guess()

        # Variables
        self.var_source_mode = tk.StringVar(value="adb")  # adb | local
        self.var_device = tk.StringVar()
        self.var_source_folder = tk.StringVar()
        self.var_dest = tk.StringVar()
        self.var_start = tk.StringVar(value="2025-09-17")
        self.var_end = tk.StringVar(value="2025-12-17")
        self.var_mode = tk.StringVar(value="copy")

        self.subfolder_vars = {name: tk.BooleanVar(value=True) for name in DEFAULT_SUBFOLDERS}

        self._build_ui()

        self.after(100, self._process_ui_queue)

        self._refresh_devices()

        # Force correct initial visibility AFTER everything exists
        self.after(0, self._apply_source_mode_visibility)

    def _try_set_icon(self):
        try:
            if os.path.exists("assets/app.ico"):
                self.iconbitmap("assets/app.ico")
                return
        except Exception:
            pass

        try:
            if os.path.exists("assets/app.png"):
                self._icon_img = tk.PhotoImage(file="assets/app.png")
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _build_ui(self):
        pad = {"padx": 10, "pady": 8}

        # Optional top logo
        try:
            if os.path.exists("assets/logo.png"):
                self._logo = tk.PhotoImage(file="assets/logo.png")
                ttk.Label(self, image=self._logo).pack(pady=(10, 0))
        except Exception:
            pass

        # Source mode selector
        frm_mode_select = ttk.LabelFrame(self, text="Source Type")
        frm_mode_select.pack(fill="x", **pad)

        ttk.Radiobutton(
            frm_mode_select,
            text="Option 1: USB Device (ADB) - read directly from phone",
            variable=self.var_source_mode,
            value="adb",
            command=self._apply_source_mode_visibility,
        ).pack(anchor="w", padx=10, pady=6)

        ttk.Radiobutton(
            frm_mode_select,
            text="Option 2: Local Folder - use a folder already copied from phone",
            variable=self.var_source_mode,
            value="local",
            command=self._apply_source_mode_visibility,
        ).pack(anchor="w", padx=10, pady=6)

        # Container for dynamic frames
        self.frm_source_container = ttk.Frame(self)
        self.frm_source_container.pack(fill="x", padx=10, pady=8)

        # --- ADB frame (NOT packed here) ---
        self.frm_adb = ttk.LabelFrame(self.frm_source_container, text="USB Device (ADB)")
        ttk.Label(self.frm_adb, text="Device:").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        self.cmb_device = ttk.Combobox(self.frm_adb, textvariable=self.var_device, state="readonly", width=45)
        self.cmb_device.grid(row=0, column=1, sticky="w", padx=10, pady=8)
        ttk.Button(self.frm_adb, text="Refresh Devices", command=self._refresh_devices).grid(
            row=0, column=2, sticky="e", padx=10, pady=8
        )
        self.lbl_device_status = ttk.Label(self.frm_adb, text="Status: Not checked yet")
        self.lbl_device_status.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 8))
        self.frm_adb.columnconfigure(1, weight=1)

        # --- Local frame (NOT packed here) ---
        self.frm_local = ttk.LabelFrame(self.frm_source_container, text="Local Folder (Copied from phone)")
        ttk.Label(self.frm_local, text="Source folder (copied from phone):").grid(
            row=0, column=0, sticky="w", padx=10, pady=6
        )
        ttk.Entry(self.frm_local, textvariable=self.var_source_folder).grid(
            row=1, column=0, sticky="we", padx=10, pady=6
        )
        ttk.Button(self.frm_local, text="Browse…", command=self._browse_source_folder).grid(
            row=1, column=1, sticky="e", padx=10, pady=6
        )
        self.frm_local.columnconfigure(0, weight=1)

        # Destination frame
        frm_dest = ttk.LabelFrame(self, text="Destination Export Folder (on this PC)")
        frm_dest.pack(fill="x", **pad)

        ttk.Label(frm_dest, text="Destination folder:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(frm_dest, textvariable=self.var_dest).grid(row=1, column=0, sticky="we", padx=10, pady=6)
        ttk.Button(frm_dest, text="Browse…", command=self._browse_dest).grid(row=1, column=1, sticky="e", padx=10, pady=6)
        frm_dest.columnconfigure(0, weight=1)

        # Settings
        frm_settings = ttk.Frame(self)
        frm_settings.pack(fill="x", **pad)

        frm_dates = ttk.LabelFrame(frm_settings, text="Date Range (inclusive, YYYY-MM-DD)")
        frm_dates.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ttk.Label(frm_dates, text="Start date:").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(frm_dates, textvariable=self.var_start, width=16).grid(row=0, column=1, sticky="w", padx=10, pady=8)

        ttk.Label(frm_dates, text="End date:").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(frm_dates, textvariable=self.var_end, width=16).grid(row=1, column=1, sticky="w", padx=10, pady=8)

        self.frm_copy_mode = ttk.LabelFrame(frm_settings, text="Mode")
        self.frm_copy_mode.pack(side="left", fill="both")

        ttk.Radiobutton(self.frm_copy_mode, text="Copy (recommended)", variable=self.var_mode, value="copy").pack(anchor="w", padx=10, pady=8)
        ttk.Radiobutton(self.frm_copy_mode, text="Move (only in Local Folder mode)", variable=self.var_mode, value="move").pack(anchor="w", padx=10, pady=8)

        # Subfolders
        frm_sub = ttk.LabelFrame(self, text="WhatsApp subfolders to scan")
        frm_sub.pack(fill="x", **pad)

        sub_inner = ttk.Frame(frm_sub)
        sub_inner.pack(fill="x", padx=10, pady=8)

        cols = 3
        names = list(self.subfolder_vars.keys())
        for i, name in enumerate(names):
            r = i // cols
            c = i % cols
            ttk.Checkbutton(sub_inner, text=name, variable=self.subfolder_vars[name]).grid(
                row=r, column=c, sticky="w", padx=10, pady=6
            )
        for c in range(cols):
            sub_inner.columnconfigure(c, weight=1)

        # Controls
        frm_controls = ttk.Frame(self)
        frm_controls.pack(fill="x", **pad)

        self.btn_start = ttk.Button(frm_controls, text="Start Export", command=self._on_start)
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_cancel = ttk.Button(frm_controls, text="Cancel", command=self._on_cancel, state="disabled")
        self.btn_cancel.pack(side="left")

        # Progress
        frm_progress = ttk.LabelFrame(self, text="Progress")
        frm_progress.pack(fill="x", **pad)

        self.progress = ttk.Progressbar(frm_progress, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(10, 6))

        counters = ttk.Frame(frm_progress)
        counters.pack(fill="x", padx=10, pady=(0, 10))

        self.lbl_scanned = ttk.Label(counters, text="Scanned: 0")
        self.lbl_scanned.pack(side="left", padx=(0, 20))

        self.lbl_matched = ttk.Label(counters, text="Exported: 0")
        self.lbl_matched.pack(side="left", padx=(0, 20))

        self.lbl_errors = ttk.Label(counters, text="Errors: 0")
        self.lbl_errors.pack(side="left")

        # Log
        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(fill="both", expand=True, **pad)

        self.txt_log = tk.Text(frm_log, height=14, wrap="word")
        self.txt_log.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)

        scroll = ttk.Scrollbar(frm_log, orient="vertical", command=self.txt_log.yview)
        scroll.pack(side="right", fill="y", padx=(0, 10), pady=10)
        self.txt_log.configure(yscrollcommand=scroll.set)

        # Footer (always visible)
        footer = ttk.Label(self, text="Built by: Muhammad Jalal Fatih")
        footer.pack(side="bottom", fill="x", pady=(0, 8))

        self._log("Ready. Choose Source Type, pick destination, set dates, then Start Export.")

    # ---------------- UI helpers ----------------

    def _apply_source_mode_visibility(self):
        # Robust: hide ALL frames in the container first
        for child in self.frm_source_container.winfo_children():
            child.pack_forget()

        mode = self.var_source_mode.get()
        if mode == "adb":
            self.frm_adb.pack(fill="x")
            if self.var_mode.get() == "move":
                self.var_mode.set("copy")
        else:
            self.frm_local.pack(fill="x")

        # Force layout refresh (helps on some systems)
        self.frm_source_container.update_idletasks()

    def _browse_source_folder(self):
        path = filedialog.askdirectory(title="Select Source Folder (Copied from phone)")
        if path:
            self.var_source_folder.set(path)

    def _browse_dest(self):
        path = filedialog.askdirectory(title="Select Destination Folder")
        if path:
            self.var_dest.set(path)

    def _set_running_ui(self, running: bool):
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_cancel.configure(state="normal" if running else "disabled")

    def _on_cancel(self):
        if self._worker_thread and self._worker_thread.is_alive():
            self._cancel_event.set()
            self._log("Cancel requested. The exporter will stop after the current file.")

    def _refresh_devices(self):
        try:
            devices = adb_list_devices(self.adb)
            self.cmb_device["values"] = devices

            if devices:
                if self.var_device.get() not in devices:
                    self.var_device.set(devices[0])
                self.lbl_device_status.configure(text=f"Status: {len(devices)} device(s) detected.")
                self._log(f"Detected devices: {', '.join(devices)}")
            else:
                self.var_device.set("")
                self.lbl_device_status.configure(text="Status: No devices detected. Check USB debugging and authorization.")
                self._log("No devices detected. Open CMD and test: adb devices")
        except Exception as e:
            self.var_device.set("")
            self.cmb_device["values"] = []
            self.lbl_device_status.configure(text=f"Status: ADB error: {e}")
            self._log(f"ADB error: {e}")

    # ---------------- Validation ----------------

    def _validate_inputs(self):
        src_mode = self.var_source_mode.get().strip()
        if src_mode not in ("adb", "local"):
            raise ValueError("Invalid Source Type selected.")

        dst = self.var_dest.get().strip()
        if not dst:
            raise ValueError("Please select a Destination folder.")
        ensure_dir(dst)

        start_dt = parse_yyyy_mm_dd(self.var_start.get())
        end_dt = parse_yyyy_mm_dd(self.var_end.get()).replace(hour=23, minute=59, second=59)
        if end_dt < start_dt:
            raise ValueError("End date must be the same as or later than start date.")

        chosen_subs = [name for name, v in self.subfolder_vars.items() if v.get()]
        if not chosen_subs:
            raise ValueError("Please select at least one subfolder to scan.")

        mode = self.var_mode.get()
        if mode not in ("copy", "move"):
            raise ValueError("Invalid export mode selected.")

        if src_mode == "adb":
            device = self.var_device.get().strip()
            if not device:
                raise ValueError("Please select a connected device (Refresh Devices if needed).")
            if mode == "move":
                raise ValueError("Move mode is not supported in USB Device (ADB) mode. Use Copy.")
            return ("adb", device, dst, start_dt, end_dt, chosen_subs, "copy")

        src_folder = self.var_source_folder.get().strip()
        if not src_folder or not os.path.isdir(src_folder):
            raise ValueError("Please select a valid Source folder (copied from phone).")

        return ("local", src_folder, dst, start_dt, end_dt, chosen_subs, mode)

    # ---------------- Start / Workers ----------------

    def _on_start(self):
        try:
            src_mode, src_value, dst, start_dt, end_dt, subfolders, mode = self._validate_inputs()
        except Exception as e:
            messagebox.showerror("Input error", str(e))
            return

        self._cancel_event.clear()
        self._scanned = 0
        self._matched = 0
        self._errors = 0

        self._set_running_ui(True)
        self.progress.configure(value=0, maximum=100, mode="determinate")

        self.txt_log.delete("1.0", "end")
        self._log("Starting export...")

        self._worker_thread = threading.Thread(
            target=self._worker_dispatch,
            args=(src_mode, src_value, dst, start_dt, end_dt, subfolders, mode),
            daemon=True,
        )
        self._worker_thread.start()

    def _worker_dispatch(self, src_mode: str, src_value: str, dest_root: str,
                         start_dt: datetime, end_dt: datetime, subfolders: list[str], mode: str):
        try:
            if src_mode == "adb":
                self._worker_adb(device=src_value, dest_root=dest_root, start_dt=start_dt, end_dt=end_dt, subfolders=subfolders)
            else:
                self._worker_local(source_root=src_value, dest_root=dest_root, start_dt=start_dt, end_dt=end_dt, subfolders=subfolders, mode=mode)
        finally:
            self._ui_queue.put(("done", None))

    def _worker_adb(self, device: str, dest_root: str, start_dt: datetime, end_dt: datetime, subfolders: list[str]):
        try:
            roots = adb_find_whatsapp_media_roots(self.adb, device)
            if not roots:
                self._ui_queue.put(("log", "ERROR: Could not find WhatsApp Media folder on the device."))
                self._ui_queue.put(("log", "Tried: /storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media and /storage/emulated/0/WhatsApp/Media"))
                return

            self._ui_queue.put(("log", f"Using WhatsApp Media root(s): {', '.join(roots)}"))

            total = 0
            for root in roots:
                for sub in subfolders:
                    remote_dir = f"{root}/{sub}"
                    if adb_path_exists(self.adb, device, remote_dir):
                        total += adb_count_files(self.adb, device, remote_dir)

            if total > 0:
                self._ui_queue.put(("progress_setup", total))
                self._ui_queue.put(("log", f"Estimated total files to scan: {total}"))
            else:
                self._ui_queue.put(("progress_indeterminate", None))
                self._ui_queue.put(("log", "Scanning... (progress is indeterminate)"))

            for root in roots:
                if self._cancel_event.is_set():
                    break

                for sub in subfolders:
                    if self._cancel_event.is_set():
                        break

                    remote_dir = f"{root}/{sub}"
                    if not adb_path_exists(self.adb, device, remote_dir):
                        self._ui_queue.put(("log", f"Skipping missing folder: {remote_dir}"))
                        continue

                    try:
                        remote_files = adb_find_files(self.adb, device, remote_dir)
                    except Exception as e:
                        self._errors += 1
                        self._ui_queue.put(("errors", self._errors))
                        self._ui_queue.put(("log", f"ERROR listing files in: {remote_dir} ({e})"))
                        continue

                    for remote_file in remote_files:
                        if self._cancel_event.is_set():
                            break

                        self._scanned += 1
                        self._ui_queue.put(("scanned", self._scanned))
                        self._ui_queue.put(("progress_tick", 1))

                        try:
                            mtime_epoch = adb_stat_mtime_epoch(self.adb, device, remote_file)
                            mtime = datetime.fromtimestamp(mtime_epoch)
                        except Exception as e:
                            self._errors += 1
                            self._ui_queue.put(("errors", self._errors))
                            self._ui_queue.put(("log", f"ERROR reading time: {remote_file} ({e})"))
                            continue

                        if not (start_dt <= mtime <= end_dt):
                            continue

                        prefix = root.rstrip("/") + "/"
                        rel_path = remote_file[len(prefix):] if remote_file.startswith(prefix) else os.path.basename(remote_file)
                        dst_file = unique_destination_path(os.path.join(dest_root, rel_path))

                        try:
                            adb_pull(self.adb, device, remote_file, dst_file)
                            self._matched += 1
                            self._ui_queue.put(("matched", self._matched))
                            self._ui_queue.put(("log", f"Exported: {rel_path}  (modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')})"))
                        except Exception as e:
                            self._errors += 1
                            self._ui_queue.put(("errors", self._errors))
                            self._ui_queue.put(("log", f"ERROR exporting: {rel_path} ({e})"))

            self._ui_queue.put(("log", "Cancelled by user." if self._cancel_event.is_set() else "Export complete (ADB mode)."))

        except Exception as e:
            self._errors += 1
            self._ui_queue.put(("errors", self._errors))
            self._ui_queue.put(("log", f"FATAL (ADB mode): {e}"))

    def _estimate_total_files_local(self, media_root: str, subfolders: list[str]) -> int:
        total = 0
        for sub in subfolders:
            p = os.path.join(media_root, sub)
            if not os.path.isdir(p):
                continue
            for _, _, files in os.walk(p):
                total += len(files)
                if total > 500000:
                    return total
        return total

    def _worker_local(self, source_root: str, dest_root: str, start_dt: datetime, end_dt: datetime,
                      subfolders: list[str], mode: str):
        try:
            media_root = detect_media_root(source_root)
            self._ui_queue.put(("log", f"Media root detected: {media_root}"))

            total = self._estimate_total_files_local(media_root, subfolders)
            if total > 0:
                self._ui_queue.put(("progress_setup", total))
                self._ui_queue.put(("log", f"Estimated total files to scan: {total}"))
            else:
                self._ui_queue.put(("progress_indeterminate", None))
                self._ui_queue.put(("log", "Scanning... (progress is indeterminate)"))

            for sub in subfolders:
                if self._cancel_event.is_set():
                    break

                src_dir = os.path.join(media_root, sub)
                if not os.path.isdir(src_dir):
                    self._ui_queue.put(("log", f"Skipping missing folder: {src_dir}"))
                    continue

                for root, _, files in os.walk(src_dir):
                    if self._cancel_event.is_set():
                        break

                    for name in files:
                        if self._cancel_event.is_set():
                            break

                        src_file = os.path.join(root, name)

                        self._scanned += 1
                        self._ui_queue.put(("scanned", self._scanned))
                        self._ui_queue.put(("progress_tick", 1))

                        try:
                            mtime = datetime.fromtimestamp(os.path.getmtime(src_file))
                        except Exception as e:
                            self._errors += 1
                            self._ui_queue.put(("errors", self._errors))
                            self._ui_queue.put(("log", f"ERROR reading time: {src_file} ({e})"))
                            continue

                        if not (start_dt <= mtime <= end_dt):
                            continue

                        rel_path = os.path.relpath(src_file, media_root)
                        dst_file = unique_destination_path(os.path.join(dest_root, rel_path))

                        try:
                            ensure_dir(os.path.dirname(dst_file))
                            if mode == "copy":
                                shutil.copy2(src_file, dst_file)
                            else:
                                shutil.move(src_file, dst_file)

                            self._matched += 1
                            self._ui_queue.put(("matched", self._matched))
                            self._ui_queue.put(("log", f"Exported: {rel_path}  (modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')})"))
                        except Exception as e:
                            self._errors += 1
                            self._ui_queue.put(("errors", self._errors))
                            self._ui_queue.put(("log", f"ERROR exporting: {rel_path} ({e})"))

            self._ui_queue.put(("log", "Cancelled by user." if self._cancel_event.is_set() else "Export complete (Local Folder mode)."))

        except Exception as e:
            self._errors += 1
            self._ui_queue.put(("errors", self._errors))
            self._ui_queue.put(("log", f"FATAL (Local mode): {e}"))

    # ---------------- UI queue handling ----------------

    def _process_ui_queue(self):
        try:
            while True:
                item = self._ui_queue.get_nowait()
                self._handle_ui_event(item)
        except queue.Empty:
            pass
        self.after(100, self._process_ui_queue)

    def _handle_ui_event(self, item: tuple):
        kind, payload = item

        if kind == "log":
            self._log(str(payload))
        elif kind == "scanned":
            self.lbl_scanned.configure(text=f"Scanned: {payload}")
        elif kind == "matched":
            self.lbl_matched.configure(text=f"Exported: {payload}")
        elif kind == "errors":
            self.lbl_errors.configure(text=f"Errors: {payload}")
        elif kind == "progress_setup":
            total = int(payload)
            self.progress.configure(mode="determinate", maximum=max(total, 1), value=0)
        elif kind == "progress_tick":
            if str(self.progress["mode"]) == "determinate":
                self.progress["value"] = min(self.progress["value"] + int(payload), self.progress["maximum"])
        elif kind == "progress_indeterminate":
            self.progress.configure(mode="indeterminate")
            self.progress.start(10)
        elif kind == "done":
            if str(self.progress["mode"]) == "indeterminate":
                self.progress.stop()
                self.progress.configure(mode="determinate", value=0, maximum=100)

            self._set_running_ui(False)
            summary = f"Finished. Scanned={self._scanned}, Exported={self._matched}, Errors={self._errors}."
            self._log(summary)
        else:
            self._log(f"(Unknown UI event: {kind})")

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.txt_log.insert("end", f"[{ts}] {msg}\n")
        self.txt_log.see("end")


if __name__ == "__main__":
    app = App()
    app.mainloop()
