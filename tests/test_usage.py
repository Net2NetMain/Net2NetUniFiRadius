from datetime import datetime, timezone

from app import main, usage
from test_api import client, sign_in


def entry(stamp, seconds=0, up=None, down=None, status='Interim-Update', sid='session-one',
          username='test-user', nas='192.0.2.10', up_high=None, down_high=None):
    record = {'User-Name': username, 'NAS-IP-Address': nas, 'Acct-Session-Id': sid,
              'Acct-Status-Type': status, 'Acct-Session-Time': seconds, 'Timestamp': stamp}
    for key, value in [('Acct-Input-Octets', up), ('Acct-Output-Octets', down),
                       ('Acct-Input-Gigawords', up_high), ('Acct-Output-Gigawords', down_high)]:
        if value is not None:
            record[key] = value
    return ('Time\n' + ''.join(f'\t{k} = "{v}"\n' for k, v in record.items()) + '\n').encode()


def write(data, host='192.0.2.10', append=False):
    folder = main.DATA / 'accounting' / host
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'detail-20261023'
    with path.open('ab' if append else 'wb') as stream:
        stream.write(data)
    return path


def all_usage():
    return usage.report('all')


def test_cumulative_duplicates_and_delayed_reports(client):
    write(entry(1000, status='Start') + entry(1010, 10, 100, 200) + entry(1011, 10, 100, 200) +
          entry(1020, 20, 250, 400) + entry(1030, 30, 400, 700, 'Stop') + entry(1040, 15, 150, 250))
    first = all_usage()
    assert first['summary']['upload_bytes'] == 400
    assert first['summary']['download_bytes'] == 700
    assert first['summary']['total_bytes'] == 1100
    assert all_usage()['summary'] == first['summary']
    assert first['sessions'][0]['state'] == 'Stop'
    assert first['sessions'][0]['upload_bytes'] == 400


def test_64bit_gigawords_and_32bit_wrap(client):
    write(entry(1000, 10, usage.WRAP - 10, 10, up_high=0, down_high=0) +
          entry(1010, 20, 20, 30, up_high=1, down_high=0))
    assert all_usage()['summary']['upload_bytes'] == usage.WRAP + 20
    write(entry(1000, 10, usage.WRAP - 10, 10, sid='without-gigawords') +
          entry(1010, 20, 20, 30, sid='without-gigawords'), append=True)
    assert all_usage()['summary']['upload_bytes'] == 2 * (usage.WRAP + 20)


def test_reused_session_id_and_conservative_counter_reset(client):
    write(entry(1000, status='Start') + entry(1010, 10, 1000, 1000) +
          entry(1020, 20, 100, 100) + entry(1030, 30, 200, 200, 'Stop') +
          entry(1040, status='Start') + entry(1050, 10, 500, 500, 'Stop'))
    result = all_usage()
    assert result['summary']['total_bytes'] == 3000
    assert result['users'][0]['sessions'] == 2
    assert len(result['sessions']) == 2
    assert result['counter_decreases'] > 0


def test_day_month_boundaries_and_highest_usage_ranking(client):
    stamp = int(datetime(2026, 10, 31, 21, 59, tzinfo=timezone.utc).timestamp())
    write(entry(stamp - 1, status='Start') + entry(stamp, 1, 100, 200) +
          entry(stamp + 120, 121, 160, 300) + entry(stamp + 125, 5, 1000, 2000, username='heavy-user'))
    result = usage.report('month', 120, now=stamp + 180)
    assert result['users'][0]['username'] == 'heavy-user'
    assert result['summary']['total_bytes'] == 3160
    monthly = {r['month']: r['total_bytes'] for r in result['monthly']}
    assert monthly == {'2026-11': 3160, '2026-10': 300}
    daily = {r['day']: r['total_bytes'] for r in usage.report('all', 120, now=stamp+180)['daily']}
    assert daily['2026-10-31'] == 300
    assert daily['2026-11-01'] == 3160
    filtered = usage.report('month', 120, 'test-user', now=stamp+180)
    assert filtered['summary']['total_bytes'] == 160


def test_partial_append_replay_rotation_and_persistent_history(client):
    first = entry(1000, 10, 100, 200)
    second = entry(1010, 20, 250, 400)
    path = write(first + second[:-2])
    assert all_usage()['summary']['total_bytes'] == 300
    write(second[-2:], append=True)
    assert all_usage()['summary']['total_bytes'] == 650
    path.unlink()
    usage.initialize()
    assert all_usage()['summary']['total_bytes'] == 650
    write(first + second)
    assert all_usage()['summary']['total_bytes'] == 650


def test_missing_counters_are_unknown_and_nas_sessions_stay_separate(client):
    write(entry(1000, status='Start'))
    write(entry(1000, 1, 50, 60, nas='192.0.2.11'), host='192.0.2.11')
    result = all_usage()
    assert result['summary']['total_bytes'] == 110
    assert len(result['sessions']) == 2
    unknown = next(s for s in result['sessions'] if s['state'] == 'Start')
    assert unknown['upload_bytes'] is None and unknown['download_bytes'] is None


def test_full_log_ingestion_beyond_old_recent_log_limit(client):
    data = b''.join(entry(1000 + n, n, n * 10, n * 20) for n in range(2601))
    assert len(data) > 512_000
    write(data)
    result = all_usage()
    assert result['summary']['total_bytes'] == 2600 * 30
    with main.db() as c:
        assert c.execute('SELECT COUNT(*) FROM usage_events').fetchone()[0] == 2601


def test_usage_authentication_and_query_validation(client):
    assert client.get('/api/usage').status_code == 401
    sign_in(client)
    assert client.get('/api/usage?period=all').status_code == 200
    assert client.get('/api/usage?period=invalid').status_code == 422
    assert client.get('/api/usage?offset_minutes=900').status_code == 422
    assert client.get('/api/usage?timezone_name=Unknown/Timezone').status_code == 422


def test_retransmitted_start_after_progress_does_not_double_count(client):
    write(entry(1000, status='Start') + entry(1030, 30, 100, 200) +
          entry(1060, status='Start') + entry(1090, 90, 250, 400, 'Stop'))
    assert all_usage()['summary']['total_bytes'] == 650
    assert all_usage()['users'][0]['sessions'] == 1


def test_named_timezone_uses_historical_daylight_saving_offsets(client):
    stamp = int(datetime(2026, 7, 1, 4, 30, tzinfo=timezone.utc).timestamp())
    write(entry(stamp, 10, 100, 200))
    result = usage.report('all', offset=-300, now=stamp+10, timezone_name='America/New_York')
    assert result['daily'][0]['day'] == '2026-07-01'
