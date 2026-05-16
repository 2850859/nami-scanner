from __future__ import annotations

from unittest.mock import MagicMock, patch

import send_mail


def test_filter_signals():
    rows = [
        {"code": "1", "rank": "B", "gc_today": False},
        {"code": "2", "rank": "S", "gc_today": False},
        {"code": "3", "rank": "C", "gc_today": True},
    ]
    got = send_mail.filter_signals(rows)
    assert len(got) == 2
    codes = {r["code"] for r in got}
    assert codes == {"2", "3"}


def test_make_csv_contains_header():
    rows = [
        {
            "rank": "S",
            "code": "7203.T",
            "name": "Test",
            "close": 100,
            "ma5": 99,
            "ma10": 98,
            "diff_pct": 1.0,
            "score": 80,
            "gc_today": False,
            "ma5_above": True,
            "ma5_slope": 0.1,
            "ma10_slope": 0.2,
        }
    ]
    csv_text = send_mail.make_csv(rows, "JPX400")
    assert "市場" in csv_text
    assert "JPX400" in csv_text
    assert "7203.T" in csv_text


@patch.dict(
    "os.environ",
    {"RESEND_API_KEY": "re_test_key", "NOTIFY_EMAIL": "test@example.com"},
    clear=False,
)
@patch.object(send_mail, "send_email", return_value=True)
def test_main_test_mode_calls_send(mock_send: MagicMock):
    send_mail.main(test=True)
    assert mock_send.called
    args, kwargs = mock_send.call_args
    assert args[1] == "test@example.com"
    assert "[テスト]" in args[2]
