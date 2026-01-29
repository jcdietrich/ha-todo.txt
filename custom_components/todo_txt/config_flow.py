import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import os

from .const import DOMAIN

class TodoTxtConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input.get("file_path"):
                errors["base"] = "invalid_path"
            else:
                return self.async_create_entry(
                    title=f"{user_input['name']} ({user_input.get('filter', 'All')})", 
                    data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("name", default="My Tasks"): str,
                vol.Required("file_path"): str,
                vol.Optional("filter"): str,
            }),
            errors=errors,
        )