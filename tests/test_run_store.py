from app.core.run_store import SQLiteRunStore
from app.core.state import initial_state


def test_sqlite_run_store_persists_records(tmp_path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite3")
    run = store.create("starter_three_node", {"x": 1})
    state = initial_state(run_id=run.run_id, workflow_name=run.workflow_name, inputs=run.inputs)
    state["final_report"] = "done"

    store.mark_running(run.run_id)
    completed = store.mark_completed(run.run_id, state)
    loaded = store.get(run.run_id)

    assert completed.status == "completed"
    assert loaded is not None
    assert loaded.state is not None
    assert loaded.state["final_report"] == "done"
