from datetime import datetime
from credit_system.subscriptions import anniversary


def test_anniversary_preserves_time_and_original_day_after_short_months():
    start=datetime(2028,1,31,13,45,12)
    assert anniversary(start,1)==datetime(2028,2,29,13,45,12)
    assert anniversary(start,2)==datetime(2028,3,31,13,45,12)
    assert anniversary(start,12)==datetime(2029,1,31,13,45,12)
