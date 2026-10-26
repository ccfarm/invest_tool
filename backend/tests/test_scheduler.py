import pytest

from app import scheduler

pytestmark = pytest.mark.no_db


def test_loop_retries_after_task_failure(monkeypatch, caplog):
    waits = []
    attempts = []

    class StopLoop(Exception):
        pass

    class Event:
        def wait(self, seconds):
            waits.append(seconds)
            if len(waits) == 3:
                raise StopLoop

    def task():
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError("采集暂时失败")

    monkeypatch.setattr(scheduler.threading, "Event", Event)
    with pytest.raises(StopLoop):
        scheduler.loop("超跌板块", task, 3600, 90)
    assert waits == [90, 3600, 3600]
    assert len(attempts) == 2
    assert "超跌板块 采集失败" in caplog.text
