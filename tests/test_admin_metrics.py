from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from webgal_backend.admin_metrics import dashboard_metrics


def test_daily_metrics_fill_empty_days_and_do_not_double_count_cached_tokens():
    responses = [
        [{'date':date(2026,10,7),'tasks':2,'completed':1,'failed':0}],
        [{'date':date(2026,10,7),'new_users':1}],
        [{'date':date(2026,10,7),'active_users':1}],
        [{'date':date(2026,10,7),'input_tokens':100,'output_tokens':20,'cached_input_tokens':40,'images':2,'tts_characters':1000,'settlements':3,'settlements_with_usage':2}],
        [{'date':date(2026,10,7),'credits':12}],
    ]
    queries=[]
    class Cursor:
        def execute(self,sql,args): queries.append((sql,args))
        def fetchall(self): return responses.pop(0)
        def fetchone(self): return {'users':1}
    @contextmanager
    def transaction(self): yield Cursor()
    with patch('webgal_backend.admin_metrics.AssetLibrary._transaction',transaction), patch('webgal_backend.admin_metrics.datetime') as clock:
        clock.now.return_value.date.return_value=date(2026,10,7)
        result=dashboard_metrics(7)
    assert len(result['daily'])==7
    assert result['daily'][0]['date']=='2026-10-01'
    assert result['daily'][0]['input_tokens']==0
    assert result['totals']['tokens']==120
    assert result['totals']['active_users']==1
    assert result['totals']['settlements_with_usage']==2
    assert any("status='CAPTURED'" in sql for sql,args in queries)
    assert any("action='CAPTURE'" in sql for sql,args in queries)
    assert all('CONVERT_TZ' in sql for sql,args in queries)
