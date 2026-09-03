"""RepoReady — a modern desktop app for cloning and bootstrapping GitHub repositories."""

import os
import subprocess
import shutil
import threading
import webbrowser
import json
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Third-party dependencies (install with: pip install -r requirements.txt)
try:
    import requests
    from tkcalendar import DateEntry
except ImportError as e:  # pragma: no cover - only hits when deps are missing
    raise SystemExit(
        f"Missing dependency: {e.name}. Please install the required packages "
        "with: pip install -r requirements.txt"
    )

APP_NAME = "RepoReady"
APP_VERSION = "3.0"
CONFIG_FILE = Path.home() / ".repoready_config.json"

# --------------------------------------------------------------------------- #
#  Design system — a sleek, GitHub-dark inspired theme
# --------------------------------------------------------------------------- #
C_BG        = "#0d1117"
C_SURFACE   = "#161b22"
C_SURFACE_2 = "#1c2128"
C_BORDER    = "#2c323b"
C_TEXT      = "#e6edf3"
C_MUTED     = "#8b959e"
C_ACCENT    = "#58a6ff"
C_BTN       = "#1f6feb"
C_BTN_HI    = "#388bfd"
C_DANGER    = "#f85149"
C_SUCCESS   = "#3fb950"
C_WARNING   = "#d29922"

FONT = "Segoe UI"
FONT_MONO = "Consolas"
# --------------------------------------------------------------------------- #
#  Config & shell helpers
# --------------------------------------------------------------------------- #
def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Failed to save config: {e}")


def load_config():
    config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError):
            # Ignore unreadable/corrupt config and start fresh
            pass
    return config


def run_cmd(cmd, cwd=None):
    try:
        res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        return res
    except Exception as e:
        # Return a dummy failed result object-like if subprocess completely crashes
        class FailedResult:
            returncode = -1
            stdout = ""
            stderr = str(e)
        return FailedResult()


def check_uv():
    """Checks for uv and installs it if missing. Updates PATH if necessary."""
    # 1. Check if on PATH already
    if shutil.which("uv"):
        return "uv"

    # 2. Check common install locations (Windows: .local/bin, Linux/Mac: .local/bin or .cargo/bin)
    home = Path.home()
    possible_paths = [
        home / ".local" / "bin",
        home / ".cargo" / "bin"
    ]

    found_path = None
    for p in possible_paths:
        exe = p / ("uv.exe" if os.name == 'nt' else "uv")
        if exe.exists():
            found_path = p
            break

    # 3. Install if not found
    if not found_path:
        print("uv not found. Installing...")
        if os.name == 'nt':  # Windows
            subprocess.run('powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"', shell=True)
            found_path = home / ".local" / "bin"
        else:  # Linux/Mac
            subprocess.run('curl -LsSf https://astral.sh/uv/install.sh | sh', shell=True)
            found_path = home / ".local" / "bin"

    # 4. Update PATH for this session
    if found_path and found_path.exists():
        path_str = str(found_path)
        if path_str not in os.environ["PATH"]:
            os.environ["PATH"] += os.pathsep + path_str
            print(f"Added {found_path} to PATH temporarily.")

    return "uv"


def log_safe(msg, callback=print):
    # Strip emojis or restricted chars if on windows console
    try:
        callback(msg)
    except UnicodeEncodeError:
        # Fallback to ascii
        msg_safe = msg.encode('ascii', 'ignore').decode('ascii')
        callback(msg_safe)
# --------------------------------------------------------------------------- #
#  Installer detection & repository setup
# --------------------------------------------------------------------------- #
def detect_installer_candidates(target_path, manual_installer="Auto (Smart)", log=lambda msg: None):
    """Detect which package-manager installers apply to the project at *target_path*.

    Returns a ``(candidates, project)`` tuple, where ``project`` carries the
    per-file detection flags used later by the setup routine.
    """
    candidates = []

    has_uv_files = os.path.exists(os.path.join(target_path, "uv.lock")) or \
        os.path.exists(os.path.join(target_path, "pyproject.toml"))
    has_conda_env = os.path.exists(os.path.join(target_path, "environment.yml"))
    has_reqs = os.path.exists(os.path.join(target_path, "requirements.txt"))
    has_py_toml = os.path.exists(os.path.join(target_path, "pyproject.toml"))

    if manual_installer == "Auto (Smart)":
        # Priority: uv (pyproject.toml/uv.lock) > conda (environment.yml) > uv (requirements.txt) > pip
        uv_path = shutil.which("uv")

        if has_uv_files:
            if uv_path:
                candidates.append("uv")
            else:
                log("  [Warning] pyproject.toml/uv.lock found, but 'uv' not installed/found. Skipping uv.")

        if has_conda_env:
            candidates.append("conda")

        if has_reqs:
            if uv_path and "uv" not in candidates:
                candidates.append("uv")

        # Fallback to pip
        if has_reqs or has_py_toml:
            candidates.append("pip")
    else:
        # User forced a specific installer
        candidates.append(manual_installer)

    return candidates, {
        "has_uv_files": has_uv_files,
        "has_conda_env": has_conda_env,
        "has_reqs": has_reqs,
        "has_py_toml": has_py_toml,
    }
def setup_repo(repo_url, parent_dir, options={}, log_callback=print):
    """Clone *repo_url* into *parent_dir* and set up its environment.

    Returns ``True`` if the environment was configured successfully (or the
    clone-only path was taken), ``False`` otherwise.
    """
    def log(m): log_safe(m, log_callback)

    repo_name = repo_url.split("/")[-1].replace(".git", "")
    target_path = os.path.join(parent_dir, repo_name)
    manual_installer = options.get("installer", "Auto (Smart)")
    only_clone = options.get("only_clone", False)

    log(f"Processing {repo_name}...")

    # 1. Clone
    if not os.path.exists(target_path):
        log(f"  Cloning {repo_url}...")
        run_cmd(f"git clone {repo_url} {target_path}")
    else:
        if options.get("skip_update"):
            log(f"  {repo_name} already exists. Skipping pull (Offline Mode).")
        else:
            log(f"  {repo_name} already exists. Pulling latest...")
            run_cmd(f"git -C {target_path} pull")

    if only_clone:
        log(f"Finished {repo_name} (Clone Only).\n")
        return True

    # 2. Detect Installer Strategy
    candidates, project = detect_installer_candidates(target_path, manual_installer, log=log)
    has_conda_env = project["has_conda_env"]
    has_reqs = project["has_reqs"]
    has_py_toml = project["has_py_toml"]

    # 3. Setup Loop
    success = False

    for installer in candidates:
        if success:
            break

        log(f"  [Python] Attempting setup via {installer}...")

        if installer == "uv":
            log("    Creating venv with uv...")
            res = run_cmd("uv venv", cwd=target_path)
            if res.returncode != 0:
                log(f"    [Error] uv venv failed: {res.stderr.strip()}")
                continue  # Try next candidate

            install_res = None
            if has_reqs:
                log("    Installing requirements.txt with uv...")
                install_res = run_cmd("uv pip install -r requirements.txt", cwd=target_path)
            elif has_py_toml:
                log("    Syncing pyproject.toml with uv...")
                install_res = run_cmd("uv sync", cwd=target_path)

            if install_res and install_res.returncode != 0:
                log(f"    [Error] uv install failed: {install_res.stderr.strip()}")
                continue

            success = True

        elif installer == "pip":
            # Create venv standard way
            venv_path = os.path.join(target_path, ".venv")
            if not os.path.exists(venv_path):
                log("    Creating .venv with python...")
                res = run_cmd("python -m venv .venv", cwd=target_path)
                if res.returncode != 0:
                    log(f"    [Error] python venv failed: {res.stderr.strip()}")
                    continue

            # Install
            pip_cmd = os.path.join(".venv", "Scripts", "pip") if os.name == 'nt' else "./.venv/bin/pip"

            install_res = None
            if has_reqs:
                log("    Installing requirements.txt with pip...")
                install_res = run_cmd(f"{pip_cmd} install -r requirements.txt", cwd=target_path)
            elif has_py_toml:
                log("    Installing pyproject.toml with pip...")
                install_res = run_cmd(f"{pip_cmd} install .", cwd=target_path)
            else:
                if manual_installer != "Auto (Smart)":
                    log("    No requirements found. Venv created only.")
                    success = True
                    break

            if install_res and install_res.returncode != 0:
                log(f"    [Error] pip install failed: {install_res.stderr.strip()}")
                continue

            success = True

        elif installer == "conda":
            if has_conda_env:
                log("    Updating conda env from environment.yml...")
                res = run_cmd("conda env update --file environment.yml --prune", cwd=target_path)
                if res.returncode == 0:
                    success = True
                else:
                    log(f"    [Error] conda update failed: {res.stderr.strip()}")
            else:
                if manual_installer != "Auto (Smart)":
                    if not os.path.exists(os.path.join(target_path, ".conda")):
                        run_cmd("conda create -p ./.conda python -y", cwd=target_path)
                    success = True

    # Check non-python if python failed or wasn't attempted
    if not success:
        # If processed by candidates loop and failed, log it
        if candidates:
            log("  [Warning] All attempts to setup Python environment failed.")

        # Java Check (Maven/Gradle)
        if os.path.exists(os.path.join(target_path, "pom.xml")):
            log("  [Java] Setting up Maven repo...")
            run_cmd("mvn clean install -DskipTests", cwd=target_path)
            success = True

        # Node.js Check
        elif os.path.exists(os.path.join(target_path, "package.json")):
            log("  [Node] Setting up Node.js repo...")
            if shutil.which("npm"):
                run_cmd("npm install", cwd=target_path)
            elif shutil.which("yarn"):
                run_cmd("yarn install", cwd=target_path)
            success = True

    if not success and not candidates:
        log("  [Skipping] No known environment configuration found.")

    # 4. Post-Setup Actions
    if options.get("open_vscode"):
        log("  Opening in VS Code...")
        run_cmd(f"code \"{target_path}\"", cwd=target_path)

    log(f"Finished {repo_name}.\n")
    return success
# --------------------------------------------------------------------------- #
#  ttk theme
# --------------------------------------------------------------------------- #
def build_styles():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # Base
    style.configure(".", background=C_BG, foreground=C_TEXT, borderwidth=0)

    style.configure("TFrame", background=C_BG)
    style.configure("Card.TFrame", background=C_SURFACE, borderwidth=1, relief="solid",
                    bordercolor=C_BORDER)

    style.configure("TLabel", background=C_BG, foreground=C_TEXT, font=(FONT, 10))
    style.configure("Muted.TLabel", background=C_BG, foreground=C_MUTED)
    style.configure("Card.TLabel", background=C_SURFACE, foreground=C_TEXT)
    style.configure("Card.Muted.TLabel", background=C_SURFACE, foreground=C_MUTED, font=(FONT, 9))

    # Entry
    style.configure("TEntry", fieldbackground=C_SURFACE_2, foreground=C_TEXT,
                    insertcolor=C_TEXT, bordercolor=C_BORDER, padding=6)
    style.map("TEntry", bordercolor=[("focus", C_ACCENT)])
    style.configure("Search.TEntry", fieldbackground=C_SURFACE_2, foreground=C_MUTED,
                    insertcolor=C_TEXT, bordercolor=C_BORDER, padding=6)

    # Buttons
    style.configure("TButton", background=C_SURFACE_2, foreground=C_TEXT,
                    bordercolor=C_BORDER, padding=(14, 7), font=(FONT, 9))
    style.map("TButton",
              background=[("active", "#2a313c"), ("pressed", C_BORDER),
                          ("disabled", C_SURFACE)],
              foreground=[("disabled", C_MUTED)])

    style.configure("Accent.TButton", background=C_BTN, foreground="#ffffff",
                    bordercolor=C_BTN, padding=(16, 8), font=(FONT, 9, "bold"))
    style.map("Accent.TButton",
              background=[("active", C_BTN_HI), ("pressed", "#1a5dc8"),
                          ("disabled", C_BORDER)],
              foreground=[("disabled", "#c9d1d9")])

    style.configure("Ghost.TButton", background=C_BG, foreground=C_ACCENT,
                    bordercolor=C_BG, padding=(10, 6), font=(FONT, 9))
    style.map("Ghost.TButton",
              background=[("active", C_SURFACE_2), ("pressed", C_SURFACE_2)],
              foreground=[("active", C_ACCENT)])

    # Combobox
    style.configure("TCombobox", fieldbackground=C_SURFACE_2, foreground=C_TEXT,
                    bordercolor=C_BORDER, arrowcolor=C_TEXT, padding=5)
    style.map("TCombobox",
              fieldbackground=[("readonly", C_SURFACE_2)],
              foreground=[("readonly", C_TEXT)],
              selectbackground=[("readonly", C_SURFACE_2)],
              selectforeground=[("readonly", C_TEXT)],
              bordercolor=[("focus", C_ACCENT)])

    # Checkbutton
    style.configure("TCheckbutton", background=C_SURFACE, foreground=C_TEXT,
                    font=(FONT, 9))
    style.map("TCheckbutton",
              background=[("active", C_SURFACE)],
              foreground=[("active", C_TEXT)])

    # LabelFrame (dialogs)
    style.configure("TLabelframe", background=C_SURFACE, bordercolor=C_BORDER,
                    relief="solid")
    style.configure("TLabelframe.Label", background=C_SURFACE,
                    foreground=C_ACCENT, font=(FONT, 9, "bold"))

    # Treeview
    style.configure("Treeview", background=C_SURFACE, foreground=C_TEXT,
                    fieldbackground=C_SURFACE, rowheight=30, borderwidth=0)
    style.map("Treeview",
              background=[("selected", "#1d4ed8")],
              foreground=[("selected", "#ffffff")])

    style.configure("Treeview.Heading", background=C_SURFACE_2, foreground=C_MUTED,
                    font=(FONT, 9, "bold"), relief="flat", padding=(8, 8))
    style.map("Treeview.Heading",
              background=[("active", "#232a35")],
              foreground=[("active", C_TEXT)])

    # Scrollbar
    style.configure("Vertical.TScrollbar", background=C_SURFACE_2,
                    troughcolor=C_BG, bordercolor=C_BG, arrowcolor=C_MUTED,
                    arrowsize=12, relief="flat")
    style.map("Vertical.TScrollbar",
              background=[("pressed", C_ACCENT), ("active", "#2a313c")])

    # Progressbar
    style.configure("TProgressbar", background=C_ACCENT, troughcolor=C_SURFACE_2,
                    bordercolor=C_SURFACE_2, lightcolor=C_ACCENT, darkcolor=C_ACCENT)
class RepoReadyApp:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.loaded_repos = []
        self.filter_state = None
        self.busy = False
        self._sort_asc = {}

        build_styles()
        self.root.title("RepoReady")
        self.root.configure(bg=C_BG)
        self.apply_geometry()

        # Load saved filter state
        if "filter_state" in self.config:
            fs = self.config["filter_state"]
            try:
                self.filter_state = {
                    "owners": set(fs.get("owners", [])),
                    "langs": set(fs.get("langs", [])),
                    "updated_after": (datetime.strptime(fs["updated_after"], "%Y-%m-%d").date()
                                      if fs.get("updated_after") else None),
                    "created_after": (datetime.strptime(fs["created_after"], "%Y-%m-%d").date()
                                      if fs.get("created_after") else None),
                }
            except Exception:
                self.filter_state = None

        # Memory of selections (IDs as strings)
        self.remembered_selections = set(self.config.get("selected_ids", []))
        self.ignore_selection_changes = False

        self.setup_ui()
        self.bind_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if not shutil.which("git"):
            self.log("git was not found on PATH — cloning will fail.", level="error")
        self.update_token_status()
        self.log(f"{APP_NAME} v{APP_VERSION} ready.")

    # --------------------------------------------------------------- misc - #
    def apply_geometry(self):
        saved = self.config.get("window_geometry")
        if saved:
            try:
                self.root.geometry(saved)
            except tk.TclError:
                self.root.geometry("1100x820")
        else:
            self.root.geometry("1100x820")
        self.root.minsize(900, 640)

    def on_close(self):
        self.config["selected_ids"] = list(self.remembered_selections)
        if self.filter_state and self.loaded_repos:
            self.config["filter_state"] = {
                "owners": list(self.filter_state["owners"]),
                "langs": list(self.filter_state["langs"]),
                "updated_after": (str(self.filter_state["updated_after"])
                                  if self.filter_state["updated_after"] else None),
                "created_after": (str(self.filter_state["created_after"])
                                  if self.filter_state["created_after"] else None),
            }
        try:
            self.config["window_geometry"] = self.root.geometry()
            self.config["column_widths"] = {c: self.tree.column(c, "width")
                                            for c in self.tree["columns"]}
        except Exception:
            pass
        save_config(self.config)
        self.root.destroy()

    def setup_ui(self):
        self._build_header()
        self._build_toolbar()
        self._build_tree()
        self._build_footer()
        self._build_log()
        self._build_statusbar()

    def bind_shortcuts(self):
        self.root.bind("<Control-l>", lambda e: self.start_load_repos())
        self.root.bind("<Control-s>", lambda e: self.entry_search.focus_set())
        self.root.bind("<Control-d>", lambda e: self.open_filter_dialog())
        self.root.bind("<Control-o>", lambda e: self.browse_dir())
        self.root.bind("<F5>", lambda e: self.start_load_repos())
        self.root.bind("<Control-a>", self._handle_select_all)
        self.root.bind("<Return>", lambda e: self.open_selected_repos())

    def _handle_select_all(self, event=None):
        w = self.root.focus_get()
        if isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)):
            return None
        self.select_all_visible()
        return "break"
# ------------------------------------------------------------ header - #
    def _build_header(self):
        header = tk.Frame(self.root, bg=C_BG)
        header.pack(fill="x", padx=18, pady=(14, 0))

        brand = tk.Frame(header, bg=C_BG)
        brand.pack(side="left")

        tk.Label(brand, text="RepoReady", bg=C_BG, fg=C_TEXT,
                 font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(brand, text="Clone & bootstrap GitHub repositories", bg=C_BG,
                 fg=C_MUTED, font=(FONT, 9)).pack(anchor="w")

        token_box = tk.Frame(header, bg=C_BG)
        token_box.pack(side="right", pady=(8, 0))

        self.lbl_token = tk.Label(token_box, text="Checking…", bg=C_BG,
                                  fg=C_MUTED, font=(FONT, 9, "bold"))
        self.lbl_token.pack(side="left", padx=(0, 12))

        ttk.Button(token_box, text="Configure Token",
                   command=self.open_token_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(token_box, text="Create PAT", style="Ghost.TButton",
                   command=self.open_token_page).pack(side="left")

    # ----------------------------------------------------------- toolbar - #
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, style="Card.TFrame", padding=(14, 10))
        bar.pack(fill="x", padx=18, pady=(10, 0))

        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *a: self.apply_filters())
        self.entry_search = ttk.Entry(bar, textvariable=self.search_var, width=30,
                                      style="Search.TEntry")
        self.entry_search.pack(side="left", padx=(0, 10), fill="x", expand=True)
        self.entry_search.insert(0, self._SEARCH_PLACEHOLDER)
        self.entry_search.bind("<FocusIn>", self._search_focus_in)
        self.entry_search.bind("<FocusOut>", self._search_focus_out)

        ttk.Label(bar, text="Sort", style="Muted.TLabel").pack(side="left", padx=(4, 6))
        self.sort_var = tk.StringVar(value="Updated")
        sort_combo = ttk.Combobox(bar, textvariable=self.sort_var, state="readonly",
                                  width=11,
                                  values=["Updated", "Stars", "Name", "Created", "Owner"])
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        sort_combo.pack(side="left", padx=(0, 10))

        ttk.Button(bar, text="Filter", command=self.open_filter_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Select All", command=self.select_all_visible).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Clear Selection", command=self.clear_selection_memory).pack(side="left")

        self.btn_load = ttk.Button(bar, text="Load Repositories", style="Accent.TButton",
                                   command=self.start_load_repos)
        self.btn_load.pack(side="right", padx=(8, 0))
# ------------------------------------------------------------- tree - #
    def _build_tree(self):
        frame = tk.Frame(self.root, bg=C_SURFACE)
        frame.pack(fill="both", expand=True, padx=18, pady=(10, 0))

        head = tk.Frame(frame, bg=C_SURFACE)
        head.pack(fill="x", padx=14, pady=(10, 8))
        tk.Label(head, text="REPOSITORIES", bg=C_SURFACE, fg=C_MUTED,
                 font=(FONT, 9, "bold")).pack(side="left")
        self.lbl_count = tk.Label(head, text="", bg=C_SURFACE, fg=C_MUTED, font=(FONT, 9))
        self.lbl_count.pack(side="left", padx=(8, 0))
        self.lbl_selected = tk.Label(head, text="", bg=C_SURFACE, fg=C_ACCENT, font=(FONT, 9))
        self.lbl_selected.pack(side="right")

        body = tk.Frame(frame, bg=C_SURFACE, highlightthickness=1,
                        highlightbackground=C_BORDER)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        cols = ("name", "desc", "lang", "stars", "updated", "owner")
        saved_widths = self.config.get("column_widths", {})
        defaults = {"name": 250, "desc": 330, "lang": 90, "stars": 55,
                    "updated": 105, "owner": 110}

        self.tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="extended")
        for col in cols:
            self.tree.heading(col, text=self._col_title(col),
                              command=lambda c=col: self.sort_by_column(c))
            self.tree.column(col, width=saved_widths.get(col, defaults[col]),
                             anchor="center" if col in ("stars", "updated") else "w",
                             minwidth=44)

        self.tree.tag_configure("odd", background="#1a202a")

        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self._on_row_double_click)

        self.lbl_empty = tk.Label(frame, bg=C_SURFACE, fg=C_MUTED, font=(FONT, 10),
                                  justify="center",
                                  text="No repositories loaded yet.\n"
                                       "Click “Load Repositories” to fetch yours.")
        self.lbl_empty.place(relx=0.5, rely=0.5, anchor="center")

    def _on_row_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self._open_repo_by_id(iid)

    @staticmethod
    def _col_title(col):
        return {"name": "Repository", "desc": "Description", "lang": "Language",
                "stars": "⭐", "updated": "Updated", "owner": "Owner"}[col]

    # ------------------------------------------------------------ footer - #
    def _build_footer(self):
        footer = ttk.Frame(self.root, style="Card.TFrame", padding=(14, 12))
        footer.pack(fill="x", padx=18, pady=(10, 0))

        row1 = ttk.Frame(footer, style="Card.TFrame")
        row1.pack(fill="x", pady=(0, 8))
        ttk.Label(row1, text="Target folder", style="Card.Muted.TLabel").pack(side="left", padx=(0, 8))
        self.path_var = tk.StringVar(value=self.config.get("target_dir", os.getcwd()))
        self.entry_path = ttk.Entry(row1, textvariable=self.path_var)
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row1, text="Browse", command=self.browse_dir).pack(side="left")

        row2 = ttk.Frame(footer, style="Card.TFrame")
        row2.pack(fill="x")
        ttk.Label(row2, text="Installer", style="Card.Muted.TLabel").pack(side="left", padx=(0, 8))
        self.installer_var = tk.StringVar(value="Auto (Smart)")
        combo = ttk.Combobox(row2, textvariable=self.installer_var, state="readonly",
                             width=13, values=["Auto (Smart)", "uv", "pip", "conda"])
        combo.pack(side="left", padx=(0, 18))

        self.opt_skip_update = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Skip git pull", variable=self.opt_skip_update).pack(side="left", padx=(0, 14))
        self.opt_vscode = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Open in VS Code", variable=self.opt_vscode).pack(side="left")

        self.btn_clone = ttk.Button(row2, text="Clone Only",
                                    command=lambda: self.start_processing(install=False, clone=True))
        self.btn_clone.pack(side="right", padx=(8, 0))
        self.btn_run = ttk.Button(row2, text="Install Env", style="Accent.TButton",
                                  command=lambda: self.start_processing(install=True, clone=False))
        self.btn_run.pack(side="right")

        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(12, 0))
# ------------------------------------------------------- log console - #
    def _build_log(self):
        card = ttk.Frame(self.root, style="Card.TFrame", padding=0)
        card.pack(fill="x", padx=18, pady=(10, 0))

        head = tk.Frame(card, bg=C_SURFACE)
        head.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(head, text="LOG", bg=C_SURFACE, fg=C_MUTED,
                 font=(FONT, 9, "bold")).pack(side="left")
        self.log_count = tk.Label(head, text="", bg=C_SURFACE, fg=C_MUTED, font=(FONT, 8))
        self.log_count.pack(side="left", padx=(8, 0))
        ttk.Button(head, text="Copy", style="Ghost.TButton",
                   command=self.copy_log).pack(side="right")
        ttk.Button(head, text="Clear", style="Ghost.TButton",
                   command=self.clear_log).pack(side="right", padx=(0, 6))
        self.btn_toggle_log = ttk.Button(head, text="Hide", style="Ghost.TButton",
                                         command=self.toggle_log)
        self.btn_toggle_log.pack(side="right", padx=(0, 6))

        self.log_container = tk.Frame(card, bg=C_SURFACE)
        self.log_container.pack(fill="both")

        self.txt_log = tk.Text(self.log_container, bg="#0b0e13", fg=C_TEXT,
                               font=(FONT_MONO, 9), relief="flat", height=7,
                               wrap="none", padx=8, pady=6, highlightthickness=1,
                               highlightbackground=C_BORDER, highlightcolor=C_BORDER)
        vsb = ttk.Scrollbar(self.log_container, orient="vertical",
                            command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=vsb.set, state="disabled")
        self.txt_log.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.txt_log.tag_configure("info", foreground=C_TEXT)
        self.txt_log.tag_configure("head", foreground=C_ACCENT)
        self.txt_log.tag_configure("ok", foreground=C_SUCCESS)
        self.txt_log.tag_configure("warn", foreground=C_WARNING)
        self.txt_log.tag_configure("error", foreground=C_DANGER)
        self._log_visible = True

    def toggle_log(self):
        if self._log_visible:
            self.log_container.pack_forget()
            self.btn_toggle_log.configure(text="Show")
        else:
            self.log_container.pack(fill="both")
            self.btn_toggle_log.configure(text="Hide")
        self._log_visible = not self._log_visible

    def clear_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")
        self.log_count.configure(text="")

    def copy_log(self):
        content = self.txt_log.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.set_status("Log copied to clipboard.")

    def log(self, message, level="info"):
        tag = level if level in ("info", "head", "ok", "warn", "error") else "info"
        stamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"[{stamp}] {message}\n", tag)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
        lines = self.txt_log.get("1.0", "end").count("\n")
        self.log_count.configure(text=f"{lines} lines")
        self.set_status(message)
        self.root.update_idletasks()

    # ------------------------------------------------------------- status - #
    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=C_BG)
        bar.pack(fill="x", side="bottom", padx=18, pady=(6, 8))

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(bar, textvariable=self.status_var, bg=C_BG, fg=C_MUTED,
                 font=(FONT_MONO, 9)).pack(side="left")
        tk.Label(bar, text=f"v{APP_VERSION}  ·  Ctrl+L load  ·  Ctrl+D filter",
                 bg=C_BG, fg=C_MUTED, font=(FONT, 8)).pack(side="right")

    def set_status(self, msg):
        self.status_var.set(str(msg))

    # ------------------------------------------------------------ search - #
    _SEARCH_PLACEHOLDER = "Search repositories…"

    def _search_focus_in(self, event=None):
        if self.search_var.get() == self._SEARCH_PLACEHOLDER:
            self.search_var.set("")
        self.entry_search.configure(style="TEntry")

    def _search_focus_out(self, event=None):
        if not self.search_var.get().strip():
            self.entry_search.configure(style="Search.TEntry")
            self.search_var.set(self._SEARCH_PLACEHOLDER)
# ------------------------------------------------------------- token - #
    def open_token_page(self):
        webbrowser.open("https://github.com/settings/tokens/new?scopes=repo&description=RepoReady")

    def open_token_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("GitHub Access Token")
        dlg.configure(bg=C_SURFACE)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()

        body = tk.Frame(dlg, bg=C_SURFACE, padx=18, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="GitHub Personal Access Token", bg=C_SURFACE, fg=C_TEXT,
                 font=(FONT, 11, "bold")).pack(anchor="w")
        tk.Label(body, bg=C_SURFACE, fg=C_MUTED, font=(FONT, 9), justify="left",
                 wraplength=400,
                 text=("Used to fetch your repositories from the GitHub API.\n"
                       "Needs the 'repo' scope. Stored locally in "
                       "~/.repoready_config.json.")).pack(anchor="w", pady=(6, 14))

        token_entry = ttk.Entry(body, font=(FONT_MONO, 10), width=46, show="•")
        token_entry.insert(0, self.config.get("github_token", ""))
        token_entry.pack(anchor="w")
        token_entry.focus_set()
        self._token_entry = token_entry

        act_row = tk.Frame(body, bg=C_SURFACE)
        act_row.pack(anchor="w", pady=(10, 0))
        btn_show = tk.Button(act_row, text="Show", bg=C_SURFACE_2, fg=C_ACCENT,
                             relief="flat", activebackground=C_SURFACE_2,
                             activeforeground=C_ACCENT, cursor="hand2", padx=12, pady=3)
        btn_show.pack(side="left")
        btn_show.configure(command=lambda: self._toggle_token_visibility(btn_show))
        tk.Button(act_row, text="Create a PAT…", bg=C_SURFACE_2, fg=C_ACCENT,
                  relief="flat", activebackground=C_SURFACE_2, activeforeground=C_ACCENT,
                  cursor="hand2", padx=12, pady=3,
                  command=self.open_token_page).pack(side="left", padx=(8, 0))

        btns = tk.Frame(body, bg=C_SURFACE)
        btns.pack(anchor="e", pady=(16, 0))
        tk.Button(btns, text="Cancel", bg=C_SURFACE_2, fg=C_TEXT, relief="flat",
                  activebackground=C_SURFACE_2, activeforeground=C_TEXT,
                  cursor="hand2", padx=18, pady=5,
                  command=dlg.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Save Token", bg=C_BTN, fg="#ffffff", relief="flat",
                  activebackground=C_BTN_HI, activeforeground="#ffffff",
                  cursor="hand2", padx=18, pady=5, font=(FONT, 9, "bold"),
                  command=lambda: self._save_token_from_dialog(dlg)).pack(side="right")

    def _toggle_token_visibility(self, btn):
        if self._token_entry["show"] == "•":
            self._token_entry.configure(show="")
            btn.configure(text="Hide")
        else:
            self._token_entry.configure(show="•")
            btn.configure(text="Show")

    def _save_token_from_dialog(self, dlg):
        token = self._token_entry.get().strip()
        self.config["github_token"] = token
        save_config(self.config)
        dlg.destroy()
        self.log("GitHub token saved." if token else "GitHub token cleared.",
                 level="ok" if token else "warn")
        self.update_token_status()

    def update_token_status(self):
        token = self.config.get("github_token", "").strip()
        if not token:
            self.lbl_token.config(text="No token · set up access", fg=C_WARNING)
            return
        self.lbl_token.config(text="Verifying…", fg=C_MUTED)

        def check_api():
            try:
                headers = {"Authorization": f"token {token}"}
                r = requests.get("https://api.github.com/user", headers=headers, timeout=5)
                if r.status_code == 200:
                    user = r.json().get("login", "unknown")
                    self.root.after(0, lambda: self.lbl_token.config(
                        text=f"Connected as {user}", fg=C_SUCCESS))
                elif r.status_code == 401:
                    self.root.after(0, lambda: self.lbl_token.config(
                        text="Invalid token", fg=C_DANGER))
                else:
                    self.root.after(0, lambda: self.lbl_token.config(
                        text=f"API error {r.status_code}", fg=C_WARNING))
            except requests.exceptions.ConnectionError:
                self.root.after(0, lambda: self.lbl_token.config(
                    text="Offline — using saved settings", fg=C_WARNING))
            except Exception:
                self.root.after(0, lambda: self.lbl_token.config(
                    text="Check failed", fg=C_WARNING))

        threading.Thread(target=check_api, daemon=True).start()
# ---------------------------------------------------------- load / fetch - #
    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.btn_load.config(state=state)
        self.btn_run.config(state=state)
        self.btn_clone.config(state=state)
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)

    def start_load_repos(self):
        if self.busy:
            return
        token = self.config.get("github_token", "").strip()
        if not token:
            messagebox.showerror("Error", "Please configure a GitHub Personal Access Token first.")
            self.open_token_dialog()
            return
        self.log("Fetching repositories…", level="head")
        self.tree.delete(*self.tree.get_children())
        self.set_busy(True)
        threading.Thread(target=self.fetch_repos, args=(token,), daemon=True).start()

    def fetch_repos(self, token):
        headers = {"Authorization": f"token {token}",
                   "Accept": "application/vnd.github.v3+json"}
        repos = []
        page = 1
        try:
            while True:
                url = f"https://api.github.com/user/repos?per_page=100&page={page}&type=all&sort=updated"
                r = requests.get(url, headers=headers, timeout=20)

                if r.status_code == 401:
                    self._show_error("Invalid token (401) — open the token dialog to fix it.",
                                     open_dialog=True)
                    return
                if r.status_code == 403:
                    self._show_error("GitHub API rate limit hit (403). Wait a while or use a scoped token.")
                    return
                if r.status_code != 200:
                    self._show_error(f"GitHub API error: {r.status_code}")
                    return

                data = r.json()
                if not data:
                    break
                repos.extend(data)
                if page % 5 == 0:
                    self.root.after(0, lambda n=len(repos): self.set_status(f"Fetched {n} repositories…"))
                page += 1

            self.root.after(0, self.update_data, repos)
        except Exception as e:
            self._show_error(str(e))
        finally:
            self.root.after(0, lambda: self.set_busy(False))

    def _show_error(self, msg, open_dialog=False):
        def _do():
            messagebox.showerror("Error", msg)
            if open_dialog:
                self.open_token_dialog()
        self.root.after(0, _do)

    def update_data(self, repos):
        self.loaded_repos = repos
        self.apply_filters()
        self.log(f"Loaded {len(repos)} repositories.", level="ok")

    # ------------------------------------------------------------ filter - #
    def open_filter_dialog(self):
        if not self.loaded_repos:
            messagebox.showinfo("Info", "Load repositories first.")
            return

        all_owners = sorted({r["owner"]["login"] for r in self.loaded_repos})
        all_langs = sorted({(r.get("language") or "N/A") for r in self.loaded_repos})

        if self.filter_state is None:
            self.filter_state = {
                "owners": set(all_owners),
                "langs": set(all_langs),
                "updated_after": None,
                "created_after": None,
            }

        dlg = tk.Toplevel(self.root)
        dlg.title("Filter Repositories")
        dlg.configure(bg=C_SURFACE)
        dlg.geometry("760x540")
        dlg.transient(self.root)
        dlg.grab_set()

        main = tk.Frame(dlg, bg=C_SURFACE, padx=12, pady=12)
        main.pack(fill="both", expand=True)

        cols = tk.Frame(main, bg=C_SURFACE)
        cols.pack(fill="both", expand=True)

        def make_list(label_text):
            box = tk.Frame(cols, bg=C_SURFACE)
            box.pack(side="left", fill="both", expand=True, padx=6)
            tk.Label(box, text=label_text, bg=C_SURFACE, fg=C_MUTED,
                     font=(FONT, 9, "bold")).pack(anchor="w", pady=(0, 4))
            listbox = tk.Listbox(box, selectmode=tk.MULTIPLE, exportselection=False,
                                 bg=C_SURFACE_2, fg=C_TEXT, selectbackground="#1d4ed8",
                                 selectforeground="#ffffff", relief="flat",
                                 highlightthickness=1, highlightbackground=C_BORDER,
                                 activestyle="none")
            listbox.pack(fill="both", expand=True)
            return listbox

        list_owners = make_list("Owners")
        list_langs = make_list("Languages")

        for i, owner in enumerate(all_owners):
            list_owners.insert(tk.END, owner)
            if owner in self.filter_state["owners"]:
                list_owners.selection_set(i)

        for i, lang in enumerate(all_langs):
            list_langs.insert(tk.END, lang)
            if lang in self.filter_state["langs"]:
                list_langs.selection_set(i)
        date_frame = tk.LabelFrame(main, text=" Date filters (optional) ",
                                   bg=C_SURFACE, fg=C_ACCENT, bd=0,
                                   font=(FONT, 9, "bold"), padx=10, pady=8)
        date_frame.pack(fill="x", pady=(12, 0))

        col = 0

        def add_date(name, value):
            nonlocal col
            var_use = tk.BooleanVar(value=value is not None)
            tk.Label(date_frame, text=name, bg=C_SURFACE, fg=C_MUTED,
                     font=(FONT, 9)).grid(row=0, column=col, padx=(4, 6), sticky="e")
            col += 1
            de = DateEntry(date_frame, width=12, background=C_SURFACE_2,
                           foreground=C_TEXT, borderwidth=1, date_pattern="yyyy-mm-dd")
            de.grid(row=0, column=col, padx=2)
            col += 1
            tk.Checkbutton(date_frame, variable=var_use, bg=C_SURFACE, fg=C_TEXT,
                           activebackground=C_SURFACE, bd=0,
                           selectcolor=C_SURFACE_2).grid(row=0, column=col, padx=(2, 14))
            col += 1
            return de, var_use

        de_updated, var_use_updated = add_date("Updated after:",
                                               self.filter_state["updated_after"])
        de_created, var_use_created = add_date("Created after:",
                                               self.filter_state["created_after"])

        if self.filter_state["updated_after"]:
            de_updated.set_date(self.filter_state["updated_after"])
        if self.filter_state["created_after"]:
            de_created.set_date(self.filter_state["created_after"])

        def select_all():
            list_owners.select_set(0, tk.END)
            list_langs.select_set(0, tk.END)

        def apply():
            self.filter_state["owners"] = {all_owners[i] for i in list_owners.curselection()}
            self.filter_state["langs"] = {all_langs[i] for i in list_langs.curselection()}
            self.filter_state["updated_after"] = de_updated.get_date() if var_use_updated.get() else None
            self.filter_state["created_after"] = de_created.get_date() if var_use_created.get() else None
            self.apply_filters()
            dlg.destroy()

        btns = tk.Frame(main, bg=C_SURFACE)
        btns.pack(fill="x", pady=(12, 0))
        tk.Button(btns, text="Apply Filter", bg=C_BTN, fg="#ffffff", relief="flat",
                  activebackground=C_BTN_HI, activeforeground="#ffffff", cursor="hand2",
                  padx=18, pady=5, font=(FONT, 9, "bold"),
                  command=apply).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Select All", bg=C_SURFACE_2, fg=C_TEXT, relief="flat",
                  activebackground=C_SURFACE_2, activeforeground=C_TEXT, cursor="hand2",
                  padx=18, pady=5, command=select_all).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Cancel", bg=C_SURFACE_2, fg=C_TEXT, relief="flat",
                  activebackground=C_SURFACE_2, activeforeground=C_TEXT, cursor="hand2",
                  padx=18, pady=5, command=dlg.destroy).pack(side="right", padx=(8, 0))

    def sort_by_column(self, col):
        if self.sort_var.get() == col:
            self._sort_asc[col] = not self._sort_asc.get(col, False)
        else:
            self._sort_asc[col] = False
        self.sort_var.set(col)
        self.apply_filters()

    def _update_headings(self, col):
        desc = self._sort_asc.get(col, False)
        for c in ("name", "desc", "lang", "stars", "updated", "owner"):
            text = self._col_title(c)
            if c == col:
                text += " â–¼" if desc else " â–²"
            self.tree.heading(c, text=text)
    def apply_filters(self):
        if not hasattr(self, "tree"):
            return
        self.ignore_selection_changes = True

        raw = self.search_var.get()
        if raw == self._SEARCH_PLACEHOLDER:
            raw = ""
        search_term = raw.lower()
        sort_mode = self.sort_var.get()

        filtered = []
        for repo in self.loaded_repos:
            name = repo.get("full_name", "").lower()
            desc = (repo.get("description") or "").lower()
            lang = (repo.get("language") or "N/A").lower()
            owner = repo["owner"]["login"]
            lang_exact = repo.get("language") or "N/A"

            if search_term and (search_term not in name and
                                search_term not in desc and search_term not in lang):
                continue

            if self.filter_state:
                if owner not in self.filter_state["owners"]:
                    continue
                if lang_exact not in self.filter_state["langs"]:
                    continue
                if self.filter_state.get("updated_after") and repo.get("updated_at"):
                    dt = datetime.strptime(repo["updated_at"][:10], "%Y-%m-%d").date()
                    if dt < self.filter_state["updated_after"]:
                        continue
                if self.filter_state.get("created_after") and repo.get("created_at"):
                    dt = datetime.strptime(repo["created_at"][:10], "%Y-%m-%d").date()
                    if dt < self.filter_state["created_after"]:
                        continue
            filtered.append(repo)

        asc = self._sort_asc.get(sort_mode)
        rev_default = sort_mode in ("Stars", "Created", "Updated")
        reverse = not asc if asc is not None else rev_default
        if sort_mode == "Stars":
            filtered.sort(key=lambda x: x.get("stargazers_count", 0), reverse=reverse)
        elif sort_mode == "Name":
            filtered.sort(key=lambda x: x.get("full_name", "").lower(), reverse=reverse)
        elif sort_mode == "Created":
            filtered.sort(key=lambda x: x.get("created_at", ""), reverse=reverse)
        elif sort_mode == "lang":
            filtered.sort(key=lambda x: (x.get("language") or "N/A").lower(), reverse=reverse)
        elif sort_mode == "desc":
            filtered.sort(key=lambda x: (x.get("description") or "").lower(), reverse=reverse)
        elif sort_mode == "Owner":
            filtered.sort(key=lambda x: x["owner"]["login"].lower(), reverse=reverse)
        else:  # Updated
            filtered.sort(key=lambda x: x.get("updated_at", ""), reverse=reverse)

        self._sort_asc[sort_mode] = reverse
        self._update_headings(sort_mode)

        self.tree.delete(*self.tree.get_children())
        for idx, repo in enumerate(filtered):
            updated_raw = repo.get("updated_at", "")
            updated_str = updated_raw.split("T")[0] if updated_raw else ""
            iid = str(repo["id"])
            self.tree.insert("", "end", iid=iid, tags=("odd",) if idx % 2 else (),
                             values=(repo["full_name"],
                                     repo.get("description", "") or "",
                                     repo.get("language", "N/A"),
                                     repo.get("stargazers_count", 0),
                                     updated_str,
                                     repo["owner"]["login"]))
            if iid in self.remembered_selections:
                self.tree.selection_add(iid)

        self.lbl_count.configure(text=f"Â· {len(self.loaded_repos)} loaded Â· {len(filtered)} shown")
        self._update_selected_label()
        self._update_empty_hint(filtered)
        self.ignore_selection_changes = False

    def _update_empty_hint(self, filtered):
        if not self.loaded_repos:
            self.lbl_empty.configure(text="No repositories loaded yet.\n"
                                          "Click â€œLoad Repositoriesâ€ to fetch yours.")
            self.lbl_empty.place(relx=0.5, rely=0.5, anchor="center")
        elif not filtered:
            self.lbl_empty.configure(text="No repositories match the current filters.")
            self.lbl_empty.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.lbl_empty.place_forget()
# --------------------------------------------------------- selection - #
    def on_tree_select(self, event=None):
        if self.ignore_selection_changes:
            return
        visible = set(self.tree.get_children())
        sel = set(self.tree.selection())
        self.remembered_selections = (self.remembered_selections & visible) | sel
        self._update_selected_label()

    def _update_selected_label(self):
        n = len(self.tree.selection())
        self.lbl_selected.configure(text=f"{n} selected" if n else "")

    def select_all_visible(self):
        children = self.tree.get_children()
        if not children:
            return
        self.ignore_selection_changes = True
        self.tree.selection_set(*children)
        self.remembered_selections.update(children)
        self.ignore_selection_changes = False
        self._update_selected_label()

    def clear_selection_memory(self):
        self.ignore_selection_changes = True
        self.remembered_selections.clear()
        self.tree.selection_remove(self.tree.selection())
        self.config["selected_ids"] = []
        self.ignore_selection_changes = False
        self._update_selected_label()
        self.set_status("Selections cleared.")

    def _open_repo_by_id(self, iid):
        for repo in self.loaded_repos:
            if str(repo["id"]) == iid:
                webbrowser.open(f"https://github.com/{repo['full_name']}")
                self.set_status(f"Opening {repo['full_name']}…")
                return

    def open_selected_repos(self):
        for iid in list(self.tree.selection())[:5]:
            self._open_repo_by_id(iid)

    # ------------------------------------------------------- processing - #
    def start_processing(self, install=True, clone=True):
        if self.busy:
            return
        selected_ids = self.tree.selection()
        if not selected_ids:
            messagebox.showinfo("Info", "No repositories selected.")
            return

        id_map = {str(r["id"]): r for r in self.loaded_repos}
        selected_repos = [id_map[i] for i in selected_ids if i in id_map]
        if not selected_repos:
            return

        parent_dir = self.path_var.get()
        if not parent_dir:
            parent_dir = os.getcwd()
            self.path_var.set(parent_dir)
        if not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir)
            except Exception as e:
                messagebox.showerror("Error", f"Could not create directory: {e}")
                return

        installer = self.installer_var.get()
        if installer in ("uv", "Auto (Smart)"):
            check_uv()

        options = {
            "open_vscode": self.opt_vscode.get() if install else False,
            "installer": installer,
            "only_clone": (clone and not install),
            "skip_update": self.opt_skip_update.get(),
        }

        self.set_busy(True)
        threading.Thread(target=self.process_batch,
                         args=(selected_repos, parent_dir, options),
                         daemon=True).start()

    def process_batch(self, repos, parent_dir, options):
        total = len(repos)
        done = 0

        def progress(value):
            self.progress.configure(mode="determinate", value=value)

        self.root.after(0, lambda: progress(0))
        for i, repo in enumerate(repos):
            name = repo["name"]
            self.root.after(0, lambda n=name, i=i: self.log(
                f"[{i + 1}/{total}] {n}…", level="head"))
            try:
                ok_flag = setup_repo(
                    repo["clone_url"], parent_dir, options=options,
                    log_callback=lambda m: self.root.after(0, self.log, m))
                level = "ok" if ok_flag else "warn"
                suffix = "done" if ok_flag else "failed"
            except Exception as e:
                level, suffix = "error", f"error: {e}"
            self.root.after(0, lambda n=name, s=suffix, lv=level: self.log(
                f"{n}: {s}", level=lv))
            done += 1
            self.root.after(0, lambda d=done: progress((d * 100) // total))

        self.root.after(0, lambda: self.log("Batch complete.", level="ok"))
        self.root.after(0, lambda: self.set_status("Batch complete."))
        self.root.after(0, lambda: self.set_busy(False))

    # ------------------------------------------------------- settings - #
    def browse_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.path_var.set(directory)
            self.save_settings()
            self.log(f"Target folder set to {directory}", level="ok")

    def save_settings(self):
        self.config["target_dir"] = self.path_var.get().strip()
        save_config(self.config)


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
def main():
    root = tk.Tk()
    RepoReadyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
