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


def test_sqlite_run_store_persists_events_in_timestamp_order(tmp_path) -> None:
    db_path = tmp_path / "runs.sqlite3"
    store = SQLiteRunStore(db_path)
    run = store.create("starter_three_node", {})

    first = store.append_event(run.run_id, "node_started", "doc_reader", {"status": "running"})
    second = store.append_event(run.run_id, "node_completed", "doc_reader", {"status": "completed"})

    events = SQLiteRunStore(db_path).list_events(run.run_id)

    assert [event.id for event in events] == [first.id, second.id]
    assert [event.event_type for event in events] == ["node_started", "node_completed"]
    assert events[1].payload == {"status": "completed"}
