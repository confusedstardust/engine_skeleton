"""Daily aggregates from registered jobs and immutable credit settlements."""
from datetime import datetime, timedelta, timezone

from .asset_library import AssetLibrary


def dashboard_metrics(days: int):
    today = datetime.now(timezone(timedelta(hours=8))).date()
    start = today - timedelta(days=days-1)
    end = today + timedelta(days=1)
    metrics = ('tasks', 'completed', 'failed', 'new_users', 'active_users', 'input_tokens',
               'output_tokens', 'cached_input_tokens', 'images', 'tts_characters', 'credits',
               'settlements', 'settlements_with_usage')
    daily = {str(start+timedelta(days=i)): {'date': str(start+timedelta(days=i)), **dict.fromkeys(metrics,0)} for i in range(days)}
    # CONVERT_TZ does not accept SYSTEM. Resolve that case to the server offset.
    db_zone = "IF(@@session.time_zone='SYSTEM',CONCAT(IF(TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(),NOW())<0,'-','+'),TIME_FORMAT(SEC_TO_TIME(ABS(TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(),NOW()))),'%%H:%%i')),@@session.time_zone)"
    date = lambda column: f"DATE(CONVERT_TZ({column},{db_zone},'+08:00'))"
    bounds = lambda column: f"{column} >= CONVERT_TZ(%s,'+08:00',{db_zone}) AND {column} < CONVERT_TZ(%s,'+08:00',{db_zone})"
    params = (str(start), str(end))
    usage = lambda field: f"COALESCE(SUM(GREATEST(0,CAST(JSON_UNQUOTE(JSON_EXTRACT(pricing_snapshot,'$.settlement.usage.{field}')) AS SIGNED))),0) AS {field}"
    queries = [
        (f"SELECT {date('created_at')} date,COUNT(*) tasks,SUM(status='SUCCEEDED') completed,SUM(status='FAILED') failed FROM generation_jobs WHERE {bounds('created_at')} GROUP BY date", params),
        (f"SELECT {date('created_at')} date,COUNT(*) new_users FROM users WHERE {bounds('created_at')} GROUP BY date", params),
        (f"SELECT date,COUNT(DISTINCT user_id) active_users FROM (SELECT {date('created_at')} date,owner_user_id user_id FROM generation_jobs WHERE {bounds('created_at')} UNION ALL SELECT {date('created_at')} date,user_id FROM credit_reservations WHERE {bounds('created_at')}) activity GROUP BY date", params+params),
        (f"SELECT {date('settled_at')} date,COUNT(*) settlements,SUM(JSON_EXTRACT(pricing_snapshot,'$.settlement.usage') IS NOT NULL) settlements_with_usage,{','.join(usage(field) for field in ('input_tokens','output_tokens','cached_input_tokens','images','tts_characters'))} FROM credit_reservations WHERE status='CAPTURED' AND {bounds('settled_at')} GROUP BY date", params),
        (f"SELECT {date('created_at')} date,COALESCE(SUM(delta_consumed),0) credits FROM credit_ledger WHERE action='CAPTURE' AND {bounds('created_at')} GROUP BY date", params),
    ]
    with AssetLibrary()._transaction() as cursor:
        for sql, args in queries:
            cursor.execute(sql,args)
            for row in cursor.fetchall():
                target = daily.get(str(row['date']))
                if target is not None:
                    target.update({key:int(value or 0) for key,value in row.items() if key != 'date'})
        cursor.execute(f"SELECT COUNT(DISTINCT user_id) users FROM (SELECT owner_user_id user_id FROM generation_jobs WHERE {bounds('created_at')} UNION ALL SELECT user_id FROM credit_reservations WHERE {bounds('created_at')}) activity", params+params)
        unique_users = int(cursor.fetchone()['users'])
    totals = {key:sum(row[key] for row in daily.values()) for key in metrics}
    totals['active_users'] = unique_users
    totals['tokens'] = totals['input_tokens']+totals['output_tokens']
    return {'timezone':'Asia/Shanghai','start':str(start),'end':str(today),'days':days,
            'daily':list(daily.values()),'totals':totals}
