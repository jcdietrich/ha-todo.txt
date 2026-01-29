import unittest
from unittest.mock import MagicMock, patch, call
import datetime
import sys
import os
import asyncio

# 1. Define real dummy classes for the HA base classes
class MockTodoListEntity:
    """Dummy base class to replace TodoListEntity."""
    _attr_supported_features = 0
    def __init__(self):
        pass
    
    async def async_update(self):
        pass

class MockTodoItem:
    def __init__(self, summary, uid=None, status=None, due=None):
        self.summary = summary
        self.uid = uid
        self.status = status
        self.due = due

class MockTodoItemStatus:
    COMPLETED = "completed"
    NEEDS_ACTION = "needs_action"

class MockTodoListEntityFeature:
    CREATE_TODO_ITEM = 1
    DELETE_TODO_ITEM = 2
    UPDATE_TODO_ITEM = 4
    SET_DUE_DATE_ON_ITEM = 8

# 2. Mock Home Assistant components
mock_hass = MagicMock()
sys.modules['homeassistant'] = mock_hass
sys.modules['homeassistant.components'] = MagicMock()

# Create the todo module mock and assign our dummy classes
mock_todo_module = MagicMock()
mock_todo_module.TodoListEntity = MockTodoListEntity
mock_todo_module.TodoItem = MockTodoItem
mock_todo_module.TodoItemStatus = MockTodoItemStatus
mock_todo_module.TodoListEntityFeature = MockTodoListEntityFeature
sys.modules['homeassistant.components.todo'] = mock_todo_module

sys.modules['homeassistant.config_entries'] = MagicMock()
sys.modules['homeassistant.core'] = MagicMock()
sys.modules['homeassistant.helpers'] = MagicMock()
sys.modules['homeassistant.helpers.entity_platform'] = MagicMock()

# Mock pytodotxt if not available
try:
    import pytodotxt
except ImportError:
    mock_py = MagicMock()
    sys.modules['pytodotxt'] = mock_py

# Import the class we want to test
sys.path.append(os.getcwd())
from custom_components.todo_txt.todo import TodoTxtListEntity

class MockTask:
    """A mock Task object that behaves like pytodotxt.Task."""
    def __init__(self, line=None, description=None, priority=None, creation_date=None, is_completed=False):
        self.line = line if line else ""
        self.description = description or self.line
        self.priority = priority
        self.creation_date = creation_date
        self.is_completed = is_completed
        self.metadata = {}

    def parse(self, line):
        self.line = line
        # Simple parse for description to help tests
        self.description = line

    def __str__(self):
        return self.line

class TestTodoTxtLogic(unittest.TestCase):
    def setUp(self):
        self.file_path = "mock.txt"
        self.entry_id = "test_entry"
        self.name = "Test List"

    def get_entity(self, filter_tag=None):
        """Helper to create an entity with a specific filter."""
        entity = TodoTxtListEntity(self.name, self.file_path, self.entry_id, filter_tag)
        entity.hass = MagicMock()
        # Mock async_add_executor_job to run immediately
        async def mock_executor(func, *args):
            return func(*args)
        entity.hass.async_add_executor_job = mock_executor
        return entity

    def test_filter_parsing(self):
        """Test that the filter string is parsed correctly into includes and excludes."""
        entity = self.get_entity("+home -@weekend -+personal +urgent")
        self.assertEqual(entity._include_filters, ["+home", "+urgent"])
        self.assertEqual(entity._exclude_filters, ["@weekend", "+personal"])

    def test_filtering_logic(self):
        """Test the full filtering logic (Inclusions AND NOT Exclusions)."""
        entity = self.get_entity("+ha -+per")
        
        tasks = [
            MockTask("Task with +ha"),               # Should SHOW
            MockTask("Task with +ha +per"),          # Should HIDE (has exclude)
            MockTask("Task with +ha +personal"),      # Should SHOW (exact match protection)
            MockTask("Task with only +personal"),    # Should HIDE (missing include)
        ]
        
        entity._todotxt = MagicMock()
        entity._todotxt.tasks = tasks
        
        with patch('os.path.exists', return_value=True):
             entity._read_file()
        
        results = [t.line for idx, t in entity._filtered_tasks]
        self.assertIn("Task with +ha", results)
        self.assertIn("Task with +ha +personal", results)
        self.assertNotIn("Task with +ha +per", results)
        self.assertNotIn("Task with only +personal", results)

    def test_sorting_logic(self):
        """Test that tasks are sorted by completion, then priority, then due date."""
        entity = self.get_entity()
        
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        
        tasks = [
            MockTask("B task", priority="B"),
            MockTask("A task", priority="A"),
            MockTask("Done task", is_completed=True),
            MockTask("Due today due:" + today.isoformat()),
            MockTask("Due tomorrow due:" + tomorrow.isoformat()),
        ]
        
        entity._todotxt = MagicMock()
        entity._todotxt.tasks = tasks
        
        with patch('os.path.exists', return_value=True):
            entity._read_file()
        
        results = [t.line for idx, t in entity._filtered_tasks]
        self.assertEqual(results[0], "A task")
        self.assertEqual(results[1], "B task")
        self.assertEqual(results[2], "Due today due:" + today.isoformat())
        self.assertEqual(results[3], "Due tomorrow due:" + tomorrow.isoformat())
        self.assertEqual(results[4], "Done task")

    def test_create_task(self):
        """Test creating a task with filters and due date."""
        entity = self.get_entity(filter_tag="+work")
        entity._todotxt = MagicMock()
        entity._todotxt.tasks = []
        entity._todotxt.save = MagicMock()

        # Mock pytodotxt.Task to use our MockTask
        with patch('custom_components.todo_txt.todo.Task', side_effect=MockTask) as mock_task_cls:
            item = MockTodoItem(summary="Buy supplies", due=datetime.date(2026, 1, 30))
            
            # Need to run async method
            asyncio.run(entity.async_create_todo_item(item))
            
            # Check if task was added
            self.assertEqual(len(entity._todotxt.tasks), 1)
            created_task = entity._todotxt.tasks[0]
            
            # Verify content
            today = datetime.date.today().isoformat()
            expected_line_start = f"{today} Buy supplies"
            self.assertTrue(created_task.line.startswith(expected_line_start))
            self.assertIn("+work", created_task.line) # Auto-appended filter
            self.assertIn("due:2026-01-30", created_task.line) # Due date
            
            # Verify save called
            entity._todotxt.save.assert_called_once()

    def test_update_task(self):
        """Test updating a task's summary and due date."""
        entity = self.get_entity()
        entity._todotxt = MagicMock()
        
        # Original task
        original_task = MockTask("2026-01-01 Original task +tag")
        original_task.creation_date = datetime.date(2026, 1, 1)
        entity._todotxt.tasks = [original_task]
        entity._todotxt.save = MagicMock()

        with patch('custom_components.todo_txt.todo.Task', side_effect=MockTask):
            # Update to new summary and add due date
            item = MockTodoItem(
                summary="Updated task +tag", 
                uid="0", 
                status=MockTodoItemStatus.NEEDS_ACTION,
                due=datetime.date(2026, 2, 1)
            )
            
            asyncio.run(entity.async_update_todo_item(item))
            
            updated_task = entity._todotxt.tasks[0]
            self.assertIn("Updated task", updated_task.line)
            self.assertIn("due:2026-02-01", updated_task.line)
            # Should preserve creation date (MockTask implementation dependent, logic copies it)
            self.assertEqual(updated_task.creation_date, original_task.creation_date)

    def test_delete_task(self):
        """Test deleting tasks by index."""
        entity = self.get_entity()
        entity._todotxt = MagicMock()
        entity._todotxt.tasks = [
            MockTask("Task 0"),
            MockTask("Task 1"),
            MockTask("Task 2")
        ]
        entity._todotxt.save = MagicMock()
        
        # Delete index 0 and 2
        asyncio.run(entity.async_delete_todo_items(["0", "2"]))
        
        self.assertEqual(len(entity._todotxt.tasks), 1)
        self.assertEqual(entity._todotxt.tasks[0].line, "Task 1")
        entity._todotxt.save.assert_called_once()
    
    def test_file_reload(self):
        """Test that calling async_update reloads tasks from the file."""
        entity = self.get_entity()
        entity._todotxt = MagicMock()
        
        # 1. Initial State
        entity._todotxt.tasks = [MockTask("Task A")]
        
        # Simulate parse() doing nothing (since we set tasks manually above)
        entity._todotxt.parse = MagicMock()
        
        # Run update
        with patch('os.path.exists', return_value=True):
            asyncio.run(entity.async_update())
            
        # Verify filtering happened and we see Task A
        self.assertEqual(len(entity._filtered_tasks), 1)
        self.assertEqual(entity._filtered_tasks[0][1].line, "Task A")
        
        # 2. Simulate File Change (Syncthing updates the file)
        # In a real scenario, .parse() would read the new file content.
        # Here we mock .parse() to update the tasks list to mimic reading a new file.
        def mock_parse_side_effect():
            entity._todotxt.tasks = [MockTask("Task A"), MockTask("Task B (New)")]
        
        entity._todotxt.parse = MagicMock(side_effect=mock_parse_side_effect)
        
        # Run update again
        with patch('os.path.exists', return_value=True):
            asyncio.run(entity.async_update())
            
        # Verify that .parse() was called and the list is updated
        entity._todotxt.parse.assert_called()
        self.assertEqual(len(entity._filtered_tasks), 2)
        self.assertEqual(entity._filtered_tasks[1][1].line, "Task B (New)")

if __name__ == '__main__':
    unittest.main()
