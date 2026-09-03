import os
import sys
from unittest.mock import MagicMock, patch

# Add the project root to the path so ``repoready`` is importable.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock GUI dependencies so the tests run without a display server.
sys.modules['tkinter'] = MagicMock()
sys.modules['tkinter.ttk'] = MagicMock()
sys.modules['tkinter.filedialog'] = MagicMock()
sys.modules['tkinter.messagebox'] = MagicMock()
sys.modules['tkcalendar'] = MagicMock()

import repoready


def test_run_cmd_success():
    """run_cmd returns an object exposing the underlying subprocess result."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Success"

        res = repoready.run_cmd("echo test")
        assert res.returncode == 0
        assert res.stdout == "Success"


def test_run_cmd_failure_returns_failed_result():
    """run_cmd degrades gracefully if subprocess itself crashes."""
    with patch('subprocess.run', side_effect=OSError("boom")):
        res = repoready.run_cmd("echo test")
        assert res.returncode == -1
        assert "boom" in res.stderr


def test_check_uv_found():
    """check_uv returns 'uv' when it is already on the PATH."""
    with patch('shutil.which', return_value='/usr/bin/uv'):
        assert repoready.check_uv() == "uv"


def test_detect_falls_back_to_pip():
    """A plain requirements.txt project is detected as pip."""
    with patch('os.path.exists', side_effect=lambda p: "requirements.txt" in p), \
            patch('shutil.which', return_value=None):
        candidates, project = repoready.detect_installer_candidates("/fake/repo")

        assert candidates == ["pip"]
        assert project["has_reqs"] is True


def test_detect_prefers_uv_for_pyproject():
    """pyproject.toml projects prefer uv when uv is available."""
    with patch('os.path.exists', side_effect=lambda p: "pyproject.toml" in p), \
            patch('shutil.which', return_value="/usr/bin/uv"):
        candidates, _ = repoready.detect_installer_candidates("/fake/repo")

        assert candidates == ["uv", "pip"]


def test_conda_env_is_detected():
    """An environment.yml project uses conda as its installer."""
    with patch('os.path.exists', side_effect=lambda p: "environment.yml" in p), \
            patch('shutil.which', return_value=None):
        candidates, project = repoready.detect_installer_candidates("/fake/repo")

        assert candidates == ["conda"]
        assert project["has_conda_env"] is True


def test_conda_and_pip_are_both_detected():
    """Projects with both environment.yml and requirements.txt use both."""
    def exists(path):
        return "environment.yml" in path or "requirements.txt" in path

    with patch('os.path.exists', side_effect=exists), \
            patch('shutil.which', return_value=None):
        candidates, project = repoready.detect_installer_candidates("/fake/repo")

        assert candidates == ["conda", "pip"]
        assert project["has_conda_env"] is True
        assert project["has_reqs"] is True


def test_no_project_files_returns_no_candidates():
    """Unknown projects produce no installer candidates."""
    with patch('os.path.exists', return_value=False), \
            patch('shutil.which', return_value=None):
        candidates, project = repoready.detect_installer_candidates("/fake/repo")

        assert candidates == []
        assert not any(project.values())


def test_manual_installer_is_forced():
    """A manually selected installer bypasses auto-detection."""
    candidates, project = repoready.detect_installer_candidates(
        "/fake/repo", manual_installer="conda")

    assert candidates == ["conda"]
    assert project["has_conda_env"] is False


def test_config_file_name():
    """Persistent configuration lives under the user home directory."""
    assert repoready.CONFIG_FILE.name == ".repoready_config.json"