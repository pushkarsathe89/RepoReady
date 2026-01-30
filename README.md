# RepoReady (v2.1)

**The Zero-Config GUI for Managing & Bootstrapping GitHub Repositories.**

RepoReady (formerly Repo Automator) is a Python-based desktop application designed to streamline the workflow of developers managing dozens of repositories. It automates fetching, cloning, and—most importantly—**environment setup** (installing dependencies) for Python, Node.js, and Java projects.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Status](https://img.shields.io/badge/status-active-success)

## 🚀 Features

* **GitHub API Integration**: Fetch all your repositories (Personal & Org) with one click. Supports pagination and lazy loading.
* **Smart Environment Detection**: Automatically identifies if a project needs `conda`, `uv`, `pip`, `npm`, or `maven` based on its files (`environment.yml`, `uv.lock`, `pyproject.toml`, `requirements.txt`).
* **Bulk Operations**: Select 50+ repositories and click **INSTALL ENV**. The tool handles cloning, updating, and environment creation (`.venv`) in parallel logging.
* **Advanced Filtering**: Filter by **Owner**, **Language**, **Date** (Created/Updated), or Name/Description.
* **Persistent State**: Remembers your selections and filter settings between sessions.
* **Zero-Crash Logging**: Includes safe logging handlers for Windows consoles (emoji-safe).

## 📦 Installation

Prerequisites: Python 3.8+ and Git.

1. **Clone this repository**:

    ```bash
    git clone https://github.com/yourusername/repo-automator.git
    cd repo-automator
    ```

2. **Install dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

    *(Ideally, you can let RepoReady manage its own environment in the future!)*

3. **Run**:

    ```bash
    python repoready.py
    ```

## 🛠 Usage

1. **Configuration**: Enter your GitHub Personal Access Token (PAT) and select a target local directory.
2. **Load**: Click **LOAD REPOSITORIES** to fetch your list.
3. **Filter**: Use the **🌪 Filter** dialog to narrow down to specific owners (e.g., `usnistgov`) or languages.
4. **Select & Action**:
    * **⬇ CLONE ONLY**: Just clones the repos (or `git pull` if they exist).
    * **⚙ INSTALL ENV**: Clones AND creates virtual environments/installs dependencies.
    * **Checkboxes**: "Skip 'git pull'" (for offline speed) or "Open in VS Code".

## 🆚 Comparison

Why use **RepoReady** over standard CLI tools?

| Feature | **RepoReady** | `meta` / `myrepos` (CLI) | VS Code Dev Containers |
| :--- | :--- | :--- | :--- |
| **Interface** | **GUI** (Visual selection, sorting) | CLI (Text-based config) | UI + JSON Config |
| **Env Setup** | **Auto-detected** (Zero config) | Manual `scripts` required | Manual `.devcontainer` required |
| **Cloning** | **Bulk API Fetch** (Auto-discovery) | Manual config entry | Single repo focus |
| **Target User** | Managing 100+ mixed legacy repos | Git Ops / DevOps | Deep development on one repo |
| **Learning Curve**| **Low** (Click & Run) | High (Config syntax) | Medium (Docker knowledge) |

* **vs `meta`/`myrepos`**: These tools are excellent for version controlling a *list* of repos, but they don't natively know how to `pip install` or `npm install` based on file detection. You have to write shell hooks. RepoReady "just works" for standard Python/Node projects.
* **vs Dev Containers**: Dev Containers provide perfect isolation using Docker. However, setting up a `.devcontainer` for 50 legacy research codes is a huge task. RepoReady runs locally on your machine, giving you immediate Intellisense support in VS Code without waiting for containers to build.

## 🧪 Testing

We include a test suite to verify core command runners and detection logic.

```bash
pip install pytest
pytest tests/
```

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a Pull Request.

1. Fork the repo.
2. Create a branch (`git checkout -b feature/amazing-feature`).
3. Commit changes.
4. Push and open PR.

## 📄 License

Distributed under the MIT License.
