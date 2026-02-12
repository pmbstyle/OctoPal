from broodmind.utils import is_heartbeat_ok
from broodmind.queen.router import should_send_worker_followup

def test_is_heartbeat_ok():
    assert is_heartbeat_ok("HEARTBEAT_OK") is True
    assert is_heartbeat_ok("heartbeat_ok") is True
    assert is_heartbeat_ok("  HEARTBEAT_OK  ") is True
    assert is_heartbeat_ok("HEARTBEAT_OK 😊") is True
    assert is_heartbeat_ok("Status: HEARTBEAT_OK") is True
    
    # Multiple lines should fail
    assert is_heartbeat_ok("HEARTBEAT_OK\nNext line") is False
    assert is_heartbeat_ok("HEARTBEAT_OK\n") is True  # strip() handles trailing newline
    assert is_heartbeat_ok("Line 1\nHEARTBEAT_OK") is False
    
    # Missing HEARTBEAT_OK should fail
    assert is_heartbeat_ok("OK") is False
    assert is_heartbeat_ok("") is False
    assert is_heartbeat_ok(None) is False

def test_should_send_worker_followup():
    assert should_send_worker_followup("HEARTBEAT_OK") is False
    assert should_send_worker_followup("HEARTBEAT_OK 😊") is False
    assert should_send_worker_followup("NO_USER_RESPONSE") is False
    assert should_send_worker_followup("I have finished the task.") is True
    assert should_send_worker_followup("HEARTBEAT_OK\nI did something else too.") is True

def test_queen_does_not_have_web_fetch():
    from broodmind.queen.router import _get_queen_tools
    class DummyQueen:
        store = None
    
    tool_specs, _ = _get_queen_tools(DummyQueen(), 0)
    tool_names = [spec.name for spec in tool_specs]
    assert "web_fetch" not in tool_names
    # Sanity check: verify some other tools ARE there
    assert "start_worker" in tool_names
    assert "fs_read" in tool_names
