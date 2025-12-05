import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk
import sys
import os

# Add parent to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui import (
    FPLApp,
    DashboardFrame,
    TransferFrame,
    DataFrame,
    FDRFrame,
    CaptaincyFrame,
)


class TestGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a root window but hide it
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _configure_manager(self, mock_manager):
        mock_manager.get_bootstrap_static.return_value = {
            "events": [{"id": 15, "is_next": True}],
            "teams": [],
        }
        # starters, bench, captain, vice, next_event
        mock_manager.optimize_team.return_value = ([], [], None, None, 15)
        mock_manager.get_team_details.return_value = {"last_deadline_bank": 100}

    @patch("gui.tool.FPLManager")
    @patch("gui.threading.Thread")
    def test_app_startup(self, mock_thread, mock_manager_cls):
        # Mock Manager
        mock_manager = mock_manager_cls.return_value
        self._configure_manager(mock_manager)

        app = FPLApp(self.root)
        self.assertIsInstance(app.current_frame, DashboardFrame)

        # Verify Shared State Init
        self.assertIn("team_id", app.shared_state)

    @patch("gui.tool.FPLManager")
    @patch("gui.threading.Thread")  # Mock thread to prevent async execution issues
    def test_navigation_transfer(self, mock_thread, mock_manager_cls):
        mock_manager = mock_manager_cls.return_value
        self._configure_manager(mock_manager)

        app = FPLApp(self.root)
        app.show_transfer_hub()
        self.assertIsInstance(app.current_frame, TransferFrame)

    @patch("gui.tool.FPLManager")
    @patch("gui.threading.Thread")
    def test_navigation_data_hub(self, mock_thread, mock_manager_cls):
        mock_manager = mock_manager_cls.return_value
        self._configure_manager(mock_manager)

        app = FPLApp(self.root)
        app.show_data_hub()
        self.assertIsInstance(app.current_frame, DataFrame)

    @patch("gui.tool.FPLManager")
    @patch("gui.threading.Thread")
    @patch("gui.FDRFrame.load_data")  # Mock data loading
    def test_navigation_fdr(self, mock_load, mock_thread, mock_manager_cls):
        mock_manager = mock_manager_cls.return_value
        self._configure_manager(mock_manager)

        app = FPLApp(self.root)
        app.show_fdr()
        self.assertIsInstance(app.current_frame, FDRFrame)

    @patch("gui.tool.FPLManager")
    @patch("gui.threading.Thread")
    @patch("gui.CaptaincyFrame.load_data")
    def test_navigation_captaincy(self, mock_load, mock_thread, mock_manager_cls):
        mock_manager = mock_manager_cls.return_value
        self._configure_manager(mock_manager)

        app = FPLApp(self.root)
        app.show_captaincy()
        self.assertIsInstance(app.current_frame, CaptaincyFrame)


if __name__ == "__main__":
    unittest.main()
