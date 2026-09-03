# RepoReady

**The zero-config GUI for managing and bootstrapping GitHub repositories.**

RepoReady is a Python desktop application that simplifies the workflow of developers who work with many repositories. It fetches, clones, and configures project environments — automatically detecting the right package manager for **Python**, **Node.js**, and **Java** codebases.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macOS-lightgrey)

## Features

- **One-click GitHub sync** — Fetch all of your personal and organization repositories. Pagination is handled automatically.
- **Automatic environment detection** — Recognizes `conda`, `uv`, `pip`, `npm`, `yarn`, and Maven projects from their files (`environment.yml`, `uv.lock`, `pyproject.toml`, `requirements.txt`, `package.json`, `pom.xml`).
- **Bulk setup** — Select as many repositories as you need and click **INSTALL ENV**. RepoReady clones, updates, and installs dependencies in a single pass.
- **Advanced filtering** — Filter by owner, language, creation/update date, name, or description.
- **Persistent state** — Your selections, filters, and settings are remembered between sessions.
- **Safe logging** — Emoji-safe log output that copes with Windows console limitations.

## Installation

**Prerequisites:** Python 3.8+ and Git.

```bash
# 1. Clone this repository
git clone https://github.com/pushkarsathe89/RepoReady.git
cd RepoReady

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run RepoReady
python repoready.py
```

## Usage

1. **Connect** — Click **Configure Token** and enter a GitHub Personal Access Token (PAT), or use **Create PAT** to generate one with the required `repo` scope.
2. **Target directory** — Click **Browse** to choose where repositories will be cloned.
3. **Load** — Click **LOAD REPOSITORIES** to fetch your repositories.
4. **Filter** — Use the **Filter** dialog to narrow the list by owner, language, or date.
5. **Select and act** — Choose the repositories you want and run an action:

| Action | Behavior |
| --- | --- |
| ⬇ **CLONE ONLY** | Clones missing repositories (or runs `git pull` on existing ones). |
| ⚙ **INSTALL ENV** | Clones, creates a virtual environment, and installs dependencies. |

Optional per-run options: *Skip 'git pull'* for faster offline runs, and *Open in VS Code* after setup.

## How environment detection works

| Project files | Installer used |
| --- | --- |
| `pyproject.toml` / `uv.lock` | `uv` |
| `requirements.txt` | `pip` or `uv` |
| `environment.yml` | `conda` |
| `pom.xml` | Maven |
| `package.json` | `npm` or `yarn` |

## Why RepoReady?

| Feature | **RepoReady** | `meta` / `myrepos` (CLI) | VS Code Dev Containers |
| :--- | :--- | :--- | :--- |
| **Interface** | GUI — visual selection and sorting | CLI — text-based config | UI + JSON config |
| **Environment setup** | Auto-detected, zero config | Manual hooks required | Manual `.devcontainer` required |
| **Cloning** | Bulk API fetch and auto-discovery | Manual config entry | Single-repo focus |
| **Target user** | Developers managing many repositories | Git automation enthusiasts | Deep work on a single repo |
| **Learning curve** | Low — click and run | High — config syntax | Medium — Docker knowledge |

- **`meta` / `myrepos`** manage a list of repositories but rely on custom shell hooks to install dependencies. RepoReady detects the project type and runs the appropriate installer out of the box.
- **Dev Containers** provide strong isolation, but authoring a `.devcontainer` for every repository is a significant up-front effort. RepoReady runs locally, giving you immediate IDE support without container build times.

## Building a standalone desktop app

RepoReady is a Python desktop application (Tkinter). You can also build it into a
single, self-contained executable that runs on machines **without** a Python
installation.

**Windows**

```bat
build.bat
```

**macOS / Linux**

```bash
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean RepoReady.spec
```

The packaged app is written to `dist/`:

| Platform | Output |
| --- | --- |
| Windows | `dist\RepoReady.exe` |
| macOS | `dist/RepoReady.app` |
| Linux | `dist/RepoReady` |

> **Note:** `git`, and the optional `uv` / `npm` / `yarn` / Maven toolchains that
> RepoReady orchestrates, are still required separately on the target machine.

## Testing

The test suite covers the core command runner and environment-detection logic.

```bash
pytest tests/
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

1. Fork the repository.
2. Create a branch: `git checkout -b feature/amazing-feature`.
3. Commit your changes.
4. Push and open a pull request.

## How to Cite

If RepoReady helps your research or workflow, please cite it so others can find
it. A machine-readable citation is included in
[`CITATION.cff`](CITATION.cff) — GitHub also exposes it through the
**Cite this repository** button in the "About" sidebar of the repo page.

**APA style:**

> Sathe, P. S. (2026). *RepoReady: A zero-config GUI for cloning and
> bootstrapping GitHub repositories* (Version 3.0) [Computer software].
> <https://github.com/pushkarsathe89/RepoReady>

**BibTeX:**

```bibtex
@software{repoready,
  author  = {Pushkar Sathe},
  title   = {RepoReady: A zero-config GUI for cloning and bootstrapping GitHub repositories},
  year    = {2026},
  version = {3.0},
  url     = {https://github.com/pushkarsathe89/RepoReady},
  license = {MIT}
}
```

## License

Distributed under the [MIT License](LICENSE).
