import pytest

from app import oversold

pytestmark = pytest.mark.no_db


def test_calculate_rsi_handles_rising_falling_and_flat_prices():
    assert oversold.calculate_rsi([float(i) for i in range(30)])[-1] == 100.0
    assert oversold.calculate_rsi([float(i) for i in range(30, 0, -1)])[-1] == 0.0
    assert oversold.calculate_rsi([10.0] * 30)[-1] == 50.0


def test_percentile_uses_linear_interpolation():
    assert oversold.percentile([0.0, 10.0, 20.0], 5) == pytest.approx(1.0)


def test_fetch_board_closes_falls_back_to_another_eastmoney_node(monkeypatch):
    seen = []

    def fake_get(url):
        seen.append(url)
        if len(seen) == 1:
            raise OSError("node unavailable")
        return {"data": {"klines": ["2026-09-07,10,11"]}}

    monkeypatch.setattr(oversold, "_json_get", fake_get)
    monkeypatch.setattr(oversold.time_mod, "sleep", lambda seconds: None)
    assert oversold.fetch_board_closes("BK0475", 1) == [11.0]
    assert len(seen) == 2
    assert seen[0].split("/")[2] != seen[1].split("/")[2]


def test_evaluate_board_accepts_current_rsi_below_five_percent_threshold(monkeypatch):
    monkeypatch.setattr(oversold, "fetch_board_closes", lambda code, limit: [10.0] * limit)
    monkeypatch.setattr(
        oversold,
        "calculate_rsi",
        lambda closes, period: [float(i) for i in range(1, 200)] + [1.0],
    )
    board = {"code": "BK1031", "name": "半导体", "stock_count": 30}
    result = oversold.evaluate_board(board)
    assert result["rsi"] == 1.0
    assert result["percentile"] == 1.0
    assert result["stock_count"] == 30


def test_evaluate_board_rejects_current_rsi_above_threshold(monkeypatch):
    monkeypatch.setattr(oversold, "fetch_board_closes", lambda code, limit: [10.0] * limit)
    monkeypatch.setattr(
        oversold,
        "calculate_rsi",
        lambda closes, period: [float(i) for i in range(1, 201)],
    )
    board = {"code": "BK1031", "name": "半导体", "stock_count": 30}
    assert oversold.evaluate_board(board) is None


def test_screen_oversold_sorts_lowest_percentile_first(monkeypatch):
    boards = [
        {"code": "BK0001", "name": "甲", "stock_count": 20},
        {"code": "BK0002", "name": "乙", "stock_count": 30},
    ]
    results = {
        "BK0001": {**boards[0], "rsi": 20.0, "threshold": 22.0, "percentile": 4.0,
                   "url": "https://example.com"},
        "BK0002": {**boards[1], "rsi": 18.0, "threshold": 23.0, "percentile": 2.0,
                   "url": "https://example.com"},
    }
    monkeypatch.setattr(oversold, "get_last_trade_date", lambda: "2026-09-04")
    monkeypatch.setattr(oversold, "fetch_industry_boards", lambda: boards)
    monkeypatch.setattr(oversold, "evaluate_board", lambda board: results[board["code"]])
    monkeypatch.setattr(oversold, "save_oversold_snapshot", lambda day, items: None)
    result = oversold.screen_oversold(concurrency=1)
    assert [item["code"] for item in result["items"]] == ["BK0002", "BK0001"]
    assert [item["rank"] for item in result["items"]] == [1, 2]
