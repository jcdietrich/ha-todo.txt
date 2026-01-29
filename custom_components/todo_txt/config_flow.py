import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import os

from .const import DOMAIN

class TodoTxtConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TodoTxtOptionsFlowHandler(config_entry)

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

class TodoTxtOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            # Update the entry's data directly since we want these to be the new "truth"
            self.hass.config_entries.async_update_entry(
                self.entry, 
                data=user_input,
                title=f"{user_input['name']} ({user_input.get('filter', 'All')})"
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("name", default=self.entry.data.get("name", "My Tasks")): str,
                vol.Required("file_path", default=self.entry.data.get("file_path")): str,
                vol.Optional("filter", default=self.entry.data.get("filter", "")): str,
            }),
        )
