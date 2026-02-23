"""Tests for harness.core.session module."""

from pathlib import Path

from harness.core.session import Session, new_session_id
from harness.types.providers import ChatMessage


class TestSession:
    def test_new_session_id(self):
        sid = new_session_id()
        assert len(sid) == 12
        assert sid.isalnum()

    def test_create_session(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        s = Session(cwd="/tmp/test")
        assert s.session_id
        assert s.turns == 0
        assert s.messages == []

    def test_add_message(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        s = Session(cwd="/tmp")
        msg = ChatMessage(role="user", content="hello")
        s.add_message(msg)
        assert len(s.messages) == 1
        assert s.messages[0].content == "hello"

    def test_record_turn(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        s = Session(cwd="/tmp")
        s.record_turn(tokens=100, cost=0.01)
        assert s.turns == 1
        assert s.total_tokens == 100
        assert s.total_cost == 0.01

    def test_persistence(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)

        # Create and populate session
        sid = "test12345678"
        s1 = Session(session_id=sid, cwd="/tmp")
        s1.save_metadata(provider="anthropic", model="claude-sonnet-4-6")
        s1.add_message(ChatMessage(role="user", content="hello"))
        s1.add_message(ChatMessage(role="assistant", content="hi there"))
        s1.record_turn(tokens=150, cost=0.02)

        # Load session from disk
        s2 = Session(session_id=sid, cwd="/tmp")
        assert s2.session_id == sid
        assert len(s2.messages) == 2
        assert s2.messages[0].content == "hello"
        assert s2.messages[1].content == "hi there"
        assert s2.turns == 1
        assert s2.total_tokens == 150

    def test_get_info(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        s = Session(cwd="/tmp/project")
        s.save_metadata(provider="anthropic", model="claude-sonnet-4-6")
        info = s.get_info()
        assert info.session_id == s.session_id
        assert info.provider == "anthropic"
        assert info.model == "claude-sonnet-4-6"
        assert info.cwd == "/tmp/project"


class TestSessionForking:
    def test_fork_creates_new_session(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        parent = Session(cwd="/tmp")
        parent.add_message(ChatMessage(role="user", content="hello"))
        parent.add_message(ChatMessage(role="assistant", content="hi"))

        child = parent.fork()
        assert child.session_id != parent.session_id
        assert len(child.messages) == 2
        assert child.messages[0].content == "hello"
        assert child.messages[1].content == "hi"

    def test_fork_records_parent_id(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        parent = Session(cwd="/tmp")
        parent.add_message(ChatMessage(role="user", content="msg"))

        child = parent.fork()
        info = child.get_info()
        assert info.parent_id == parent.session_id

    def test_fork_with_up_to(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        parent = Session(cwd="/tmp")
        parent.add_message(ChatMessage(role="user", content="msg1"))
        parent.add_message(ChatMessage(role="assistant", content="msg2"))
        parent.add_message(ChatMessage(role="user", content="msg3"))

        child = parent.fork(up_to=2)
        assert len(child.messages) == 2
        assert child.messages[0].content == "msg1"
        assert child.messages[1].content == "msg2"

    def test_fork_persists_to_disk(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        parent = Session(cwd="/tmp")
        parent.add_message(ChatMessage(role="user", content="hello"))

        child = parent.fork()

        # Load from disk
        loaded = Session(session_id=child.session_id, cwd="/tmp")
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "hello"

    def test_fork_empty_session(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        parent = Session(cwd="/tmp")

        child = parent.fork()
        assert len(child.messages) == 0
        assert child.session_id != parent.session_id

    def test_fork_independence(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path)
        parent = Session(cwd="/tmp")
        parent.add_message(ChatMessage(role="user", content="shared"))

        child = parent.fork()
        # Adding to parent doesn't affect child
        parent.add_message(ChatMessage(role="assistant", content="parent only"))
        assert len(child.messages) == 1

        # Adding to child doesn't affect parent
        child.add_message(ChatMessage(role="assistant", content="child only"))
        assert len(parent.messages) == 2
        assert len(child.messages) == 2
