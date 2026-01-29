import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import asyncio

# Mock Home Assistant modules
mock_hass = MagicMock()
sys.modules['homeassistant'] = mock_hass
sys.modules['homeassistant.config_entries'] = MagicMock()
sys.modules['homeassistant.core'] = MagicMock()

# Mock the constants
sys.modules['custom_components.todo_txt.const'] = MagicMock()
sys.modules['custom_components.todo_txt.const'].DOMAIN = "todo_txt"

# Add path
sys.path.append(os.getcwd())

from custom_components.todo_txt import async_setup_entry, async_unload_entry, async_reload_entry

class TestInit(unittest.TestCase):
    def setUp(self):
        self.hass = MagicMock()
        self.entry = MagicMock()
        self.entry.entry_id = "test_entry_id"
        self.entry.data = {"some": "data"}
        self.hass.data = {}

    def test_setup_entry(self):
        """Test successful setup of entry."""
        self.hass.config_entries.async_forward_entry_setups = AsyncMock()
        
        # Run setup
        result = asyncio.run(async_setup_entry(self.hass, self.entry))
        
        self.assertTrue(result)
        # Check that data was stored
        self.assertIn("todo_txt", self.hass.data)
        self.assertEqual(self.hass.data["todo_txt"]["test_entry_id"], self.entry.data)
        
        # Check that update listener was added
        self.entry.add_update_listener.assert_called_once()
        self.entry.async_on_unload.assert_called_once()
        
        # Check that platforms were forwarded
        self.hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    def test_unload_entry(self):
        """Test successful unload of entry."""
        # Setup initial state
        self.hass.data = {"todo_txt": {"test_entry_id": {}}}
        self.hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        
        # Run unload
        result = asyncio.run(async_unload_entry(self.hass, self.entry))
        
        self.assertTrue(result)
        # Check that data was popped
        self.assertNotIn("test_entry_id", self.hass.data["todo_txt"])
        self.hass.config_entries.async_unload_platforms.assert_awaited_once()

    def test_reload_entry(self):
        """Test reload entry."""
        self.hass.config_entries.async_reload = AsyncMock()
        
        asyncio.run(async_reload_entry(self.hass, self.entry))
        
        self.hass.config_entries.async_reload.assert_awaited_with(self.entry.entry_id)

if __name__ == '__main__':
    unittest.main()
