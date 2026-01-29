import datetime
import os
import logging
import re
from typing import Any

from pytodotxt import TodoTxt, Task
from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    file_path = entry.data["file_path"]
    name = entry.data["name"]
    filter_tag = entry.data.get("filter")
    async_add_entities([TodoTxtListEntity(name, file_path, entry.entry_id, filter_tag)], update_before_add=True)

class TodoTxtListEntity(TodoListEntity):
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
    )

    def __init__(self, name: str, file_path: str, entry_id: str, filter_tag: str = None) -> None:
        self._attr_name = name
        self._file_path = file_path
        self._attr_unique_id = f"{entry_id}_{filter_tag}" if filter_tag else entry_id
        self._filter_tag = filter_tag.strip() if filter_tag else None
        self._todotxt = TodoTxt(self._file_path)
        # We store pairs of (original_index, task) to handle filtering properly
        self._filtered_tasks: list[tuple[int, Task]] = []

    @property
    def todo_items(self) -> list[TodoItem] | None:
        return [
            TodoItem(
                uid=str(idx),
                summary=self._get_summary(task),
                status=TodoItemStatus.COMPLETED if task.is_completed else TodoItemStatus.NEEDS_ACTION,
                due=self._get_due_date(task),
            )
            for idx, task in self._filtered_tasks
        ]

    def _get_due_date(self, task: Task):
        # Manual extraction to be safe from library attribute naming issues
        match = re.search(r'due:(\d{4}-\d{2}-\d{2})', str(task))
        if match:
            try:
                return datetime.date.fromisoformat(match.group(1))
            except ValueError:
                pass
        return None

    def _get_summary(self, task: Task):
        # We use the full line representation but might want to strip completion marker
        # if the library doesn't do it in .description
        # Generally task.description is safe in standard implementations
        summary = task.description
        
        # If the library strips priority/creation date from description, re-add them
        # (This logic was already present and seems okay, keeping it)
        if task.priority:
            summary = f"({task.priority}) {summary}"
        if task.creation_date:
            summary = f"{task.creation_date.isoformat()} {summary}"
        return summary

    def _read_file(self):
        if not os.path.exists(self._file_path):
            with open(self._file_path, 'w') as f:
                pass
        self._todotxt.parse()
        
        # Apply filtering and sorting
        all_tasks = list(enumerate(self._todotxt.tasks))
        
        # 1. Filter
        if self._filter_tag:
            all_tasks = [
                (i, t) for i, t in all_tasks 
                if str(t) and self._filter_tag in str(t)
            ]
        else:
            all_tasks = [(i, t) for i, t in all_tasks if str(t) and str(t).strip()]

        # 2. Sort
        # Priority: Incomplete -> Priority (A-Z) -> Due Date -> Creation Date
        def sort_key(item):
            idx, task = item
            is_done = 1 if task.is_completed else 0
            priority = task.priority if task.priority else "Z"
            
            # Manual extraction for sorting key
            due_str = "9999-12-31"
            match = re.search(r'due:(\d{4}-\d{2}-\d{2})', str(task))
            if match:
                due_str = match.group(1)
            
            created = task.creation_date.isoformat() if task.creation_date else "0000-01-01"
            return (is_done, priority, due_str, created)

        all_tasks.sort(key=sort_key)
        self._filtered_tasks = all_tasks

    def _write_file(self):
        self._todotxt.save()

    async def async_update(self) -> None:
        await self.hass.async_add_executor_job(self._read_file)

    async def async_create_todo_item(self, item: TodoItem) -> None:
        creation_date = datetime.date.today().isoformat()
        line = f"{creation_date} {item.summary}"
        
        # If filtering is active, ensure the tag is in the new item
        if self._filter_tag and self._filter_tag not in line:
            line += f" {self._filter_tag}"
            
        if item.due:
            if f"due:{item.due.isoformat()}" not in line:
                line += f" due:{item.due.isoformat()}"
        
        task = Task()
        task.parse(line)
        self._todotxt.tasks.append(task)
        await self.hass.async_add_executor_job(self._write_file)
        await self.async_update()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        # UID is the original index in self._todotxt.tasks
        idx = int(item.uid)
        if 0 <= idx < len(self._todotxt.tasks):
            original_task = self._todotxt.tasks[idx]
            
            new_line = item.summary
            new_line = re.sub(r'\bdue:\d{4}-\d{2}-\d{2}\b', '', new_line).strip()
            if item.due:
                new_line += f" due:{item.due.isoformat()}"
            
            # Ensure filter tag is preserved if it was forced
            if self._filter_tag and self._filter_tag not in new_line:
                new_line += f" {self._filter_tag}"

            new_task = Task()
            new_task.parse(new_line)
            new_task.creation_date = original_task.creation_date
            new_task.priority = new_task.priority or original_task.priority
            new_task.is_completed = (item.status == TodoItemStatus.COMPLETED)
            if new_task.is_completed:
                new_task.completion_date = original_task.completion_date or datetime.date.today()
            else:
                new_task.completion_date = None

            self._todotxt.tasks[idx] = new_task
            await self.hass.async_add_executor_job(self._write_file)
            await self.async_update()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        indices = sorted([int(uid) for uid in uids], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self._todotxt.tasks):
                self._todotxt.tasks.pop(idx)
        await self.hass.async_add_executor_job(self._write_file)
        await self.async_update()