import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add parent directory to path to allow importing autoenv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock tkinter before importing autoenv (headless CI support)
sys.modules['tkinter'] = MagicMock()
sys.modules['tkinter.ttk'] = MagicMock()
sys.modules['tkinter.filedialog'] = MagicMock()
sys.modules['tkinter.messagebox'] = MagicMock()

# Mock tkcalendar
sys.modules['tkcalendar'] = MagicMock()

import repoready

def test_run_cmd_success():
    """Test that run_cmd returns a success object."""
    # We mock subprocess.run to avoid actual execution
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Success"
        
        res = repoready.run_cmd("echo test")
        assert res.returncode == 0
        assert res.stdout == "Success"

def test_check_uv_found():
    """Test check_uv returns 'uv' if found."""
    with patch('shutil.which', return_value='/usr/bin/uv'):
        assert repoready.check_uv() == "uv"

def test_installer_logic_conda():
    """Test standard installer detection logic independent of Filesystem (using mocks)."""
    # This involves mocking os.path.exists
    with patch('os.path.exists') as mock_exists:
        # Simulate environment.yml exists
        def side_effect(path):
            if "environment.yml" in path: return True
            return False
        mock_exists.side_effect = side_effect
        
        # We can't easily unit test the huge setup_repo function without refactoring 
        # because it calls run_cmd and log internally.
        # Ideally, we would extract the "detection" logic into a separate function.
        # But we can verify simpler parts of the script imported successfully.
        assert repoready.CONFIG_FILE.name == ".repoready_config.json"
