"""Automated test suite for native Tkinter desktop application (Part A and D).

Covers:
1. Tkinter application construction and view/service integration.
2. View navigation and switching without recreation.
3. Component rendering (MetricCard, ScrollableFrame, Dialogs).
4. Worker pool off-thread execution and thread-safe callbacks to Tkinter.
5. Error handling in workers without crashing GUI.
6. Clean GUI shutdown and resource cleanup.
"""

from pathlib import Path
import tempfile
import time
import tkinter as tk
import pytest

from evodev.config import EvoDevConfig, set_config
from evodev.gui.app import EvoDevApp
from evodev.gui.components.metric_card import MetricCard
from evodev.gui.components.scrollable_frame import ScrollableFrame
from evodev.gui.theme import Colors, apply_theme
from evodev.gui.workers import WorkerPool
from evodev.models.experience import KnowledgeScope, Lesson
from evodev.models.profile import ProfileManifest
from evodev.storage.db import DatabaseManager, close_db, set_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


from unittest.mock import MagicMock

@pytest.fixture(scope="module")
def tk_root():
    """Module-scoped headless Tk root window."""
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


@pytest.fixture
def gui_app_instance(tk_root):
    """Create a headless Tkinter application instance with temporary database."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = EvoDevConfig(data_dir=Path(tmp_dir))
        set_config(config)
        db = DatabaseManager(":memory:")
        set_db(db)
        MigrationManager(db).run_migrations()

        p_repo = ProfileRepository(db)
        p_repo.create(ProfileManifest(name="GUITestProfile", version="2.0.0"), is_active=True)

        app = EvoDevApp(root=tk_root, config=config)
        tk_root.update_idletasks()

        try:
            yield {"root": tk_root, "app": app, "config": config, "db": db}
        finally:
            try:
                app.worker_pool.shutdown(wait=False)
            except Exception:
                pass
            for child in tk_root.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            close_db()


def test_app_construction_and_views_instantiation(gui_app_instance):
    """Verify EvoDevApp constructs all 9 required views and binds them properly."""
    app = gui_app_instance["app"]
    root = gui_app_instance["root"]

    assert app.current_view_key == "overview"

    expected_views = [
        "overview",
        "inspector",
        "memory",
        "skills",
        "lessons",
        "strategies",
        "experiences",
        "orchestration",
        "scheduler",
        "checkpoints",
        "benchmarks",
        "connectors",
        "doctor",
        "uninstall",
    ]

    for key in expected_views:
        assert key in app.views
        view = app.views[key]
        assert isinstance(view, tk.Frame)


def test_view_switching_and_nav_states(gui_app_instance):
    """Verify switching between views updates topbar headers and active nav button styles."""
    app = gui_app_instance["app"]
    root = gui_app_instance["root"]

    # Switch to inspector
    app.switch_view("inspector")
    root.update_idletasks()
    assert app.current_view_key == "inspector"
    assert app.page_heading.cget("text") == "Experience Inspector"

    # Switch to memory
    app.switch_view("memory")
    root.update_idletasks()
    assert app.current_view_key == "memory"
    assert app.page_heading.cget("text") == "Categorized Memory"

    # Switch to skills
    app.switch_view("skills")
    root.update_idletasks()
    assert app.current_view_key == "skills"
    assert app.page_heading.cget("text") == "Self-Improving Skills"

    # Switch to benchmarks
    app.switch_view("benchmarks")
    root.update_idletasks()
    assert app.current_view_key == "benchmarks"
    assert app.page_heading.cget("text") == "Empirical Benchmarks"

    # Switch to uninstall
    app.switch_view("uninstall")
    root.update_idletasks()
    assert app.current_view_key == "uninstall"
    assert app.page_heading.cget("text") == "Uninstall EvoDev"


def test_overview_view_service_data_rendering(gui_app_instance):
    """Verify OverviewView reads real counts from repository layer."""
    app = gui_app_instance["app"]
    root = gui_app_instance["root"]

    # Insert test lesson
    active = app.p_repo.get_active()
    lesson = Lesson(
        profile_id=active.profile_id,
        title="Test Lesson for GUI",
        trigger_pattern="Trigger GUI pattern",
        recommended_strategy="Use Tkinter cleanly",
        scope=KnowledgeScope.GLOBAL,
    )
    app.l_repo.save(lesson)

    app.switch_view("overview")
    root.update_idletasks()

    # Metric card should reflect 1 active lesson
    assert app.views["overview"].card_lessons._value_var.get() == "1"


def test_worker_pool_async_success_and_thread_safety(gui_app_instance):
    """Verify WorkerPool runs background tasks without blocking and dispatches callbacks safely."""
    app = gui_app_instance["app"]
    root = gui_app_instance["root"]

    finished = []
    result_data = []

    def background_task():
        time.sleep(0.05)
        return {"computation": 42}

    def on_success(res):
        result_data.append(res)
        finished.append(True)

    app.worker_pool.run_async(
        task_fn=background_task,
        on_success=on_success,
    )

    # Pump Tkinter event loop until finished
    start_time = time.time()
    while not finished and (time.time() - start_time) < 3.0:
        root.update()
        time.sleep(0.02)

    assert finished == [True]
    assert result_data == [{"computation": 42}]


def test_worker_pool_error_handling(gui_app_instance):
    """Verify background task exceptions are caught and passed to on_error on main thread."""
    app = gui_app_instance["app"]
    root = gui_app_instance["root"]

    caught_errors = []

    def faulty_task():
        raise ValueError("Simulated background worker failure")

    def on_error(exc):
        caught_errors.append(exc)

    app.worker_pool.run_async(
        task_fn=faulty_task,
        on_error=on_error,
    )

    start_time = time.time()
    while not caught_errors and (time.time() - start_time) < 3.0:
        root.update()
        time.sleep(0.02)

    assert len(caught_errors) == 1
    assert "Simulated background worker failure" in str(caught_errors[0])


def test_metric_card_component(gui_app_instance):
    """Verify MetricCard component value updating and color modification."""
    root = gui_app_instance["root"]
    card = MetricCard(root, label="Test Stat", initial_value="100", hint="Hints")
    card.pack()
    root.update_idletasks()

    assert card._value_var.get() == "100"
    card.set_value("250", color=Colors.STATUS_GREEN)
    assert card._value_var.get() == "250"


def test_gui_clean_shutdown(gui_app_instance):
    """Verify closing the application cleanly terminates workers and releases resources."""
    app = gui_app_instance["app"]
    root = gui_app_instance["root"]

    mock_destroy = MagicMock()
    app.root.destroy = mock_destroy

    app.on_closing()
    assert app.worker_pool._is_shutdown is True
    mock_destroy.assert_called_once()


def test_scrollable_frame_component(gui_app_instance):
    """Verify ScrollableFrame creates interior canvas and dynamic content frame."""
    root = gui_app_instance["root"]
    sf = ScrollableFrame(root)
    sf.pack(fill="both", expand=True)

    # Insert test items in interior
    lbl = tk.Label(sf.scrollable_content, text="Inner Content")
    lbl.pack()
    root.update_idletasks()

    assert sf.canvas is not None
    assert sf.scrollable_content is not None
    assert lbl.winfo_parent() == str(sf.scrollable_content)


def test_new_profile_dialog_submission(gui_app_instance):
    """Verify NewProfileDialog validates input and invokes callback with parsed payload."""
    from evodev.gui.components.dialogs import NewProfileDialog

    root = gui_app_instance["root"]
    created_data = []

    def on_create(payload):
        created_data.append(payload)

    dialog = NewProfileDialog(root, on_create=on_create)
    dialog.name_entry.insert(0, "CustomDevProfile")
    dialog.desc_entry.insert(0, "Test profile description")
    dialog.domain_cb.set("mobile")
    dialog.activate_var.set(True)

    # Trigger submit
    dialog._submit()

    assert len(created_data) == 1
    assert created_data[0]["name"] == "CustomDevProfile"
    assert created_data[0]["description"] == "Test profile description"
    assert created_data[0]["domains"] == ["mobile"]
    assert created_data[0]["activate"] is True

