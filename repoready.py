import os
import subprocess
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import threading
import webbrowser
import json
from datetime import datetime
from pathlib import Path
# Third-party dependencies (install with: pip install -r requirements.txt)
try:
    import requests
    from tkcalendar import DateEntry
except ImportError as e:  # pragma: no cover - only hits when deps are missing
    raise SystemExit(
        f"Missing dependency: {e.name}. Please install the required packages "
        "with: pip install -r requirements.txt"
    )

CONFIG_FILE = Path.home() / ".repoready_config.json"


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
            # Default windows install location
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
        return

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
            log(f"  [Java] Setting up Maven repo...")
            run_cmd("mvn clean install -DskipTests", cwd=target_path)
            success = True

        # Node.js Check
        elif os.path.exists(os.path.join(target_path, "package.json")):
            log(f"  [Node] Setting up Node.js repo...")
            if shutil.which("npm"):
                run_cmd("npm install", cwd=target_path)
            elif shutil.which("yarn"):
                run_cmd("yarn install", cwd=target_path)
            success = True

    if not success and not candidates:
        log("  [Skipping] No known environment configuration found.")

    # 4. Post-Setup Actions
    if options.get("open_vscode"):
        log(f"  Opening in VS Code...")
        run_cmd(f"code \"{target_path}\"", cwd=target_path)

    log(f"Finished {repo_name}.\n")


class RepoReadyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RepoReady")
        self.root.geometry("950x750")
        self.root.configure(bg="#2d2d2d")

        # Apply Dark Mode Theme
        self.apply_dark_theme()

        self.loaded_repos = []
        self.config = load_config()
        self.filter_state = None

        # Load saved filter state
        if 'filter_state' in self.config:
            fs = self.config['filter_state']
            try:
                self.filter_state = {
                    'owners': set(fs.get('owners', [])),
                    'langs': set(fs.get('langs', [])),
                    'updated_after': datetime.strptime(fs['updated_after'], "%Y-%m-%d").date() if fs.get('updated_after') else None,
                    'created_after': datetime.strptime(fs['created_after'], "%Y-%m-%d").date() if fs.get('created_after') else None
                }
            except Exception as e:
                print(f"Error loading filter state: {e}")
                self.filter_state = None

        # Memory of selections (IDs as strings)
        self.remembered_selections = set(self.config.get("selected_ids", []))
        self.ignore_selection_changes = False

        self.setup_ui()

        # Save on exit
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Initial status check
        self.update_token_status()

    def on_close(self):
        # Save selections
        self.config["selected_ids"] = list(self.remembered_selections)

        # Save filters
        if self.filter_state:
            # Sets to lists and Dates to strings for JSON
            fs_save = {
                'owners': list(self.filter_state['owners']),
                'langs': list(self.filter_state['langs']),
                'updated_after': str(self.filter_state['updated_after']) if self.filter_state['updated_after'] else None,
                'created_after': str(self.filter_state['created_after']) if self.filter_state['created_after'] else None
            }
            self.config["filter_state"] = fs_save

        save_config(self.config)
        self.root.destroy()

    def apply_dark_theme(self):
        style = ttk.Style()
        style.theme_use('clam')

        bg_color = "#2d2d2d"
        fg_color = "#e0e0e0"
        entry_bg = "#3d3d3d"
        select_bg = "#007acc"

        style.configure(".", background=bg_color, foreground=fg_color, bordercolor="#444444")
        style.configure("TLabel", background=bg_color, foreground=fg_color)
        style.configure("TLabelframe", background=bg_color, foreground=fg_color, bordercolor="#444444")
        style.configure("TLabelframe.Label", background=bg_color, foreground="#007acc", font=("Segoe UI", 10, "bold"))

        style.configure("TEntry", fieldbackground=entry_bg, foreground=fg_color, insertcolor=fg_color, bordercolor=entry_bg)

        style.configure("TButton", background="#3d3d3d", foreground=fg_color, bordercolor="#555555", padding=6)
        style.map("TButton", background=[("active", "#505050"), ("disabled", "#2d2d2d")])

        style.configure("Treeview",
                        background="#3d3d3d",
                        foreground=fg_color,
                        fieldbackground="#3d3d3d",
                        rowheight=30,
                        borderwidth=0)
        style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", "white")])

        style.configure("Treeview.Heading", background="#444444", foreground="white", relief="flat", padding=5)
        style.map("Treeview.Heading", background=[("active", "#505050")])

        style.configure("TCombobox", fieldbackground=entry_bg, foreground=fg_color, arrowcolor=fg_color)
        style.map("TCombobox", fieldbackground=[("readonly", entry_bg)], selectbackground=[
                  ("readonly", entry_bg)], selectforeground=[("readonly", fg_color)])

        style.configure("TCheckbutton", background=bg_color, foreground=fg_color)

    def open_token_dialog(self):
        current_token = self.config.get("github_token", "")
        token = simpledialog.askstring("GitHub Token", "Enter your GitHub Personal Access Token (PAT):", initialvalue=current_token, show='*')
        if token is not None: # check for None in case user cancels
            self.config["github_token"] = token.strip()
            self.save_settings()
            self.update_token_status()

    def update_token_status(self):
        token = self.config.get("github_token", "")
        if not token:
            self.lbl_token_status.config(text="❌ Not Configured", foreground="#FF5252")
            return

        self.lbl_token_status.config(text="🔄 Verifying...", foreground="#FFC107") # Amber
        
        def check_api():
            try:
                headers = {"Authorization": f"token {token}"}
                r = requests.get("https://api.github.com/user", headers=headers, timeout=5)
                if r.status_code == 200:
                    user_data = r.json()
                    user = user_data.get("login", "Unknown")
                    self.root.after(0, lambda: self.lbl_token_status.config(
                        text=f"✅ Connected as {user}", foreground="#4CAF50"))
                elif r.status_code == 401:
                    self.root.after(0, lambda: self.lbl_token_status.config(
                        text="❌ Invalid Token", foreground="#FF5252"))
                else:
                    self.root.after(0, lambda: self.lbl_token_status.config(
                        text=f"⚠️ API Error ({r.status_code})", foreground="#FFC107"))
            except requests.exceptions.ConnectionError:
                 self.root.after(0, lambda: self.lbl_token_status.config(
                        text="🔌 Offline / Check Internet", foreground="#FFC107"))
            except Exception as e:
                self.root.after(0, lambda: self.lbl_token_status.config(
                        text=f"❌ Error: {str(e)}", foreground="#FF5252"))

        threading.Thread(target=check_api, daemon=True).start()

    def setup_ui(self):
        # --- Top Frame: Configuration ---
        config_frame = ttk.LabelFrame(self.root, text="Configuration", padding=15)
        config_frame.pack(fill="x", padx=15, pady=10)

        # Token
        ttk.Label(config_frame, text="GitHub Access:").grid(row=0, column=0, sticky="e", padx=5)
        
        self.lbl_token_status = ttk.Label(config_frame, text="Checking...", font=("Segoe UI", 9, "bold"))
        self.lbl_token_status.grid(row=0, column=1, padx=5, sticky="w")
        
        ttk.Button(config_frame, text="Configure Token", command=self.open_token_dialog).grid(row=0, column=2, padx=5)
        ttk.Button(config_frame, text="Create PAT", command=self.open_token_page).grid(row=0, column=3, padx=5)

        # Parent Dir
        ttk.Label(config_frame, text="Target Dir:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.path_var = tk.StringVar(value=self.config.get("target_dir", os.getcwd()))
        ttk.Entry(config_frame, textvariable=self.path_var, width=50).grid(row=1, column=1, padx=5, sticky="ew")
        ttk.Button(config_frame, text="Browse", command=self.browse_dir).grid(row=1, column=2, padx=5)

        config_frame.columnconfigure(1, weight=1)

        # --- Filter & Settings Bar ---
        bar_frame = ttk.Frame(self.root, padding="15 5 15 5")
        bar_frame.pack(fill="x")

        # Left: Search and Sort
        ttk.Label(bar_frame, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.apply_filters())
        ttk.Entry(bar_frame, textvariable=self.search_var, width=25).pack(side="left", padx=5)

        ttk.Label(bar_frame, text="Sort:").pack(side="left", padx=(15, 5))
        self.sort_var = tk.StringVar(value="Updated")
        sort_combo = ttk.Combobox(bar_frame, textvariable=self.sort_var, values=[
                                  "Updated", "Stars", "Name", "Created", "Owner"], state="readonly", width=12)
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        sort_combo.pack(side="left")

        # Filter Button
        ttk.Button(bar_frame, text="🌪 Filter", command=self.open_filter_dialog).pack(side="left", padx=5)

        # Clear Memory Button
        ttk.Button(bar_frame, text="🧹 Clear Selection", command=self.clear_selection_memory).pack(side="left", padx=5)

        # Right: Python Installer Selection
        # Moved to footer for cleaner top bar
        self.btn_load = ttk.Button(bar_frame, text="📥 LOAD REPOSITORIES", command=self.start_load_repos)
        self.btn_load.pack(side="right", padx=15, ipadx=10)

        # --- List Frame: Treeview ---
        list_frame = ttk.Frame(self.root, padding=15)
        list_frame.pack(fill="both", expand=True)

        columns = ("name", "desc", "lang", "stars", "updated", "owner")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("name", text="Repository", command=lambda: self.sort_by_column("name"))
        self.tree.heading("desc", text="Description")
        self.tree.heading("lang", text="Language", command=lambda: self.sort_by_column("lang"))
        self.tree.heading("stars", text="⭐", command=lambda: self.sort_by_column("stars"))
        self.tree.heading("updated", text="Last Updated", command=lambda: self.sort_by_column("updated"))
        self.tree.heading("owner", text="Owner", command=lambda: self.sort_by_column("owner"))

        self.tree.column("name", width=220, anchor="w")
        self.tree.column("desc", width=350, anchor="w")
        self.tree.column("lang", width=100, anchor="center")
        self.tree.column("stars", width=50, anchor="center")
        self.tree.column("updated", width=120, anchor="center")
        self.tree.column("owner", width=100, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- Footer: Options & Action ---
        footer_frame = ttk.Frame(self.root, padding=15)
        footer_frame.pack(fill="x")

        # Installer Selection (Moved here)
        ttk.Label(footer_frame, text="Installer:").pack(side="left", padx=(0, 5))
        self.installer_var = tk.StringVar(value="Auto (Smart)")
        inst_combo = ttk.Combobox(footer_frame, textvariable=self.installer_var, values=[
                                  "Auto (Smart)", "uv", "pip", "conda"], state="readonly", width=12)
        inst_combo.pack(side="left", padx=5)

        self.opt_skip_update = tk.BooleanVar(value=False)
        cb_skip = ttk.Checkbutton(footer_frame, text="Skip 'git pull'", variable=self.opt_skip_update)
        cb_skip.pack(side="left", padx=5)

        self.opt_vscode = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(footer_frame, text="Open in VS Code", variable=self.opt_vscode)
        cb.pack(side="left", padx=15)

        self.btn_run = ttk.Button(footer_frame, text="⚙ INSTALL ENV", command=lambda: self.start_processing(install=True, clone=False))
        self.btn_run.pack(side="right", fill="x", expand=False, ipadx=10, padx=5)

        self.btn_clone = ttk.Button(footer_frame, text="⬇ CLONE ONLY", command=lambda: self.start_processing(install=False, clone=True))
        self.btn_clone.pack(side="right", fill="x", expand=False, ipadx=10, padx=5)

        # --- Status Bar ---
        status_frame = ttk.Frame(self.root, padding=5)
        status_frame.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready. Enter Token and Load Repositories.")
        lbl_status = ttk.Label(status_frame, textvariable=self.status_var, foreground="#888888", font=("Consolas", 9))
        lbl_status.pack(side="left")

    def sort_by_column(self, col):
        # Simple column click sort
        self.sort_var.set(col.capitalize())
        self.apply_filters()

    def browse_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.path_var.set(directory)
            self.save_settings()

    def save_settings(self):
        self.config["target_dir"] = self.path_var.get().strip()
        save_config(self.config)

        # Flash success
        self.status_var.set("Config saved!")
        self.root.after(2000, lambda: self.status_var.set("Ready."))

    def open_token_page(self):
        webbrowser.open("https://github.com/settings/tokens/new?scopes=repo&description=RepoReady")

    def log(self, message):
        log_safe(message)
        self.status_var.set(str(message))
        self.root.update_idletasks()

    def start_load_repos(self):
        token = self.config.get("github_token", "").strip()
        if not token:
            messagebox.showerror("Error", "Please enter a GitHub Personal Access Token.")
            return

        self.btn_load.config(state="disabled")
        self.log("Fetching repositories...")
        self.tree.delete(*self.tree.get_children())  # Clear existing
        threading.Thread(target=self.fetch_repos, args=(token,), daemon=True).start()

    def fetch_repos(self, token):
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        repos = []
        page = 1

        try:
            while True:
                url = f"https://api.github.com/user/repos?per_page=100&page={page}&type=all&sort=updated"
                r = requests.get(url, headers=headers)

                if r.status_code == 401:
                    self.root.after(0, messagebox.showerror, "Error", "Invalid Token (401 Unauthorized)")
                    return
                if r.status_code != 200:
                    self.root.after(0, messagebox.showerror, "Error", f"API Error: {r.status_code}")
                    return

                data = r.json()
                if not data:
                    break

                repos.extend(data)
                self.root.after(0, self.status_var.set, f"Fetched {len(repos)} repositories...")
                page += 1

            self.root.after(0, self.update_data, repos)

        except Exception as e:
            self.root.after(0, messagebox.showerror, "Error", str(e))
        finally:
            self.root.after(0, lambda: self.btn_load.config(state="normal"))

    def update_data(self, repos):
        self.loaded_repos = repos
        self.apply_filters()  # Populates the tree
        self.log(f"Successfully loaded {len(repos)} repositories.")

    def open_filter_dialog(self):
        if not self.loaded_repos:
            messagebox.showinfo("Info", "Load repositories first.")
            return

        # Calculate uniques
        all_owners = sorted(list(set(r['owner']['login'] for r in self.loaded_repos)))
        all_langs = sorted(list(set((r.get('language') or "N/A") for r in self.loaded_repos)))

        # Setup state if empty
        if self.filter_state is None:
            self.filter_state = {
                'owners': set(all_owners),
                'langs': set(all_langs),
                'updated_after': None,
                'created_after': None
            }
        else:
            # Re-ensure all expected owners/langs are present in case repo list changed
            # But we actually want to KEEP the user's specific selection from Config
            # So if they selected "OwnerA" and we load new repos, stick to "OwnerA" logic?
            # Or default to all if config is stale?
            # Logic: If saved filter has items, keep them. If user selects nothing, it typically means nothing.
            # But "Select All" saves ALL items.
            pass

        dlg = tk.Toplevel(self.root)
        dlg.title("Filter Repositories")
        dlg.geometry("700x500")
        dlg.transient(self.root)
        dlg.grab_set()

        # UI Layout
        main_frame = ttk.Frame(dlg, padding=10)
        main_frame.pack(fill="both", expand=True)

        # --- Columns Frame ---
        cols_frame = ttk.Frame(main_frame)
        cols_frame.pack(fill="both", expand=True)

        # Owners Column
        frame_owners = ttk.LabelFrame(cols_frame, text="Owners", padding=5)
        frame_owners.pack(side="left", fill="both", expand=True, padx=5)

        list_owners = tk.Listbox(frame_owners, selectmode=tk.MULTIPLE, exportselection=False, bg="#3d3d3d", fg="white")
        list_owners.pack(fill="both", expand=True)
        for i, owner in enumerate(all_owners):
            list_owners.insert(tk.END, owner)
            if owner in self.filter_state['owners']:
                list_owners.selection_set(i)

        # Languages Column
        frame_langs = ttk.LabelFrame(cols_frame, text="Languages", padding=5)
        frame_langs.pack(side="left", fill="both", expand=True, padx=5)

        list_langs = tk.Listbox(frame_langs, selectmode=tk.MULTIPLE, exportselection=False, bg="#3d3d3d", fg="white")
        list_langs.pack(fill="both", expand=True)
        for i, lang in enumerate(all_langs):
            list_langs.insert(tk.END, lang)
            if lang in self.filter_state['langs']:
                list_langs.selection_set(i)

        # --- Date Filters Frame ---
        date_frame = ttk.LabelFrame(main_frame, text="Date Filters (Optional)", padding=10)
        date_frame.pack(fill="x", pady=10)

        # Updated After
        tk.Label(date_frame, text="Updated After:").grid(row=0, column=0, padx=5, sticky="e")
        de_updated = DateEntry(date_frame, width=12, background='darkblue', foreground='white', borderwidth=2)
        de_updated.grid(row=0, column=1, padx=5)
        # Checkbox to enable
        var_use_updated = tk.BooleanVar(value=self.filter_state['updated_after'] is not None)
        chk_updated = tk.Checkbutton(date_frame, variable=var_use_updated)
        chk_updated.grid(row=0, column=2)

        if self.filter_state['updated_after']:
            de_updated.set_date(self.filter_state['updated_after'])

        # Created After
        tk.Label(date_frame, text="Created After:").grid(row=0, column=3, padx=15, sticky="e")
        de_created = DateEntry(date_frame, width=12, background='darkblue', foreground='white', borderwidth=2)
        de_created.grid(row=0, column=4, padx=5)
        var_use_created = tk.BooleanVar(value=self.filter_state['created_after'] is not None)
        chk_created = tk.Checkbutton(date_frame, variable=var_use_created)
        chk_created.grid(row=0, column=5)

        if self.filter_state['created_after']:
            de_created.set_date(self.filter_state['created_after'])

        # Buttons
        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill="x")

        def apply():
            # Gather selections
            sel_owners = [all_owners[i] for i in list_owners.curselection()]
            sel_langs = [all_langs[i] for i in list_langs.curselection()]

            self.filter_state['owners'] = set(sel_owners)
            self.filter_state['langs'] = set(sel_langs)

            # Dates
            self.filter_state['updated_after'] = de_updated.get_date() if var_use_updated.get() else None
            self.filter_state['created_after'] = de_created.get_date() if var_use_created.get() else None

            self.apply_filters()
            dlg.destroy()

        def select_all():
            list_owners.select_set(0, tk.END)
            list_langs.select_set(0, tk.END)

        ttk.Button(btn_frame, text="Apply Filter", command=apply).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Select All", command=select_all).pack(side="right", padx=5)

    def apply_filters(self):
        self.ignore_selection_changes = True

        search_term = self.search_var.get().lower()
        sort_mode = self.sort_var.get()

        # 1. Filter
        filtered = []
        for repo in self.loaded_repos:
            r_name = repo.get('full_name', '').lower()
            r_desc = (repo.get('description') or '').lower()
            r_lang = (repo.get('language') or '').lower()
            r_owner = repo['owner']['login']
            r_lang_exact = repo.get('language') or "N/A"

            # Dates (ISO 8601 YYYY-MM-DD...)
            r_updated_str = repo.get('updated_at')  # 2026-01-29T...
            r_created_str = repo.get('created_at')

            # Search Text Check
            text_match = search_term in r_name or search_term in r_desc or search_term in r_lang
            if not text_match:
                continue

            # Category Filter Check
            if self.filter_state:
                if r_owner not in self.filter_state['owners']:
                    continue
                if r_lang_exact not in self.filter_state['langs']:
                    continue

                # Date Check
                if self.filter_state.get('updated_after') and r_updated_str:
                    dt_up = datetime.strptime(r_updated_str.split('T')[0], "%Y-%m-%d").date()
                    if dt_up < self.filter_state['updated_after']:
                        continue

                if self.filter_state.get('created_after') and r_created_str:
                    dt_cr = datetime.strptime(r_created_str.split('T')[0], "%Y-%m-%d").date()
                    if dt_cr < self.filter_state['created_after']:
                        continue

            filtered.append(repo)

        # 2. Sort
        if sort_mode == "Stars":
            filtered.sort(key=lambda x: x.get('stargazers_count', 0), reverse=True)
        elif sort_mode == "Name":
            filtered.sort(key=lambda x: x.get('full_name', '').lower())
        elif sort_mode == "Created":
            filtered.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        elif sort_mode == "Owner":
            filtered.sort(key=lambda x: x['owner']['login'].lower())
        else:  # Updated (Default)
            filtered.sort(key=lambda x: x.get('updated_at', ''), reverse=True)

        # 3. Update UI
        self.tree.delete(*self.tree.get_children())
        for repo in filtered:
            # Format date
            updated_raw = repo.get('updated_at', '')
            updated_str = updated_raw.split('T')[0] if updated_raw else ""

            iid = str(repo['id'])
            self.tree.insert("", "end", iid=iid, values=(
                repo['full_name'],
                repo.get('description', '') or "",
                repo.get('language', 'N/A'),
                repo.get('stargazers_count', 0),
                updated_str,
                repo['owner']['login']
            ))

            if iid in self.remembered_selections:
                self.tree.selection_add(iid)

        self.ignore_selection_changes = False

    def on_tree_select(self, event):
        if self.ignore_selection_changes:
            return

        visible_ids = self.tree.get_children()
        current_selection = self.tree.selection()

        for iid in visible_ids:
            if iid in current_selection:
                self.remembered_selections.add(iid)
            else:
                self.remembered_selections.discard(iid)

    def clear_selection_memory(self):
        self.ignore_selection_changes = True
        self.remembered_selections.clear()
        self.tree.selection_remove(self.tree.selection())
        self.config["selected_ids"] = []
        save_config(self.config)
        self.ignore_selection_changes = False
        messagebox.showinfo("Memory", "Selection memory cleared.")

    def start_processing(self, install=True, clone=True):
        selected_ids = self.tree.selection()
        if not selected_ids:
            messagebox.showinfo("Info", "No repositories selected.")
            return

        # Find repo objects by ID
        selected_repos = []
        id_map = {str(r['id']): r for r in self.loaded_repos}
        for iid in selected_ids:
            if iid in id_map:
                selected_repos.append(id_map[iid])

        parent_dir = self.path_var.get()
        if not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir)
            except Exception as e:
                messagebox.showerror("Error", f"Could not create directory: {e}")
                return

        # Check uv if selected
        installer = self.installer_var.get()
        if installer in ["uv", "Auto (Smart)"]:
            check_uv()

        options = {
            "open_vscode": self.opt_vscode.get() if install else False,  # Only open if installing (usually) or change logic if needed
            "installer": installer,
            "only_clone": (clone and not install),
            "skip_update": self.opt_skip_update.get()
        }

        threading.Thread(target=self.process_batch, args=(selected_repos, parent_dir, options), daemon=True).start()

    def process_batch(self, repos, parent_dir, options):
        self.root.after(0, lambda: self.btn_run.config(state="disabled"))
        self.root.after(0, lambda: self.btn_clone.config(state="disabled"))

        total = len(repos)

        for i, repo in enumerate(repos):
            repo_name = repo['name']
            msg = f"Processing ({i+1}/{total}): {repo_name}"
            self.root.after(0, self.log, msg)

            try:
                setup_repo(repo['clone_url'], parent_dir, options=options,
                           log_callback=lambda m: self.root.after(0, self.log, m))
            except Exception as e:
                self.root.after(0, self.log, f"Error processing {repo_name}: {e}")

        self.root.after(0, self.log, "Batch processing complete!")
        self.root.after(0, messagebox.showinfo, "Success", "All selected repositories have been processed.")
        self.root.after(0, lambda: self.btn_run.config(state="normal"))
        self.root.after(0, lambda: self.btn_clone.config(state="normal"))


if __name__ == "__main__":
    root = tk.Tk()
    app = RepoReadyApp(root)
    root.mainloop()
