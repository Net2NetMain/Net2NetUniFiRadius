"""Persistent, incremental RADIUS accounting and conservative counter deltas."""
import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOG = logging.getLogger(__name__)
WRAP = 1 << 32
MAX_PASS = 16 * 1024 * 1024
MAX_FILE = 4 * 1024 * 1024


def initialize():
    from . import main as m
    with m.db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS usage_cursors(path TEXT PRIMARY KEY, signature TEXT, offset INTEGER, tail TEXT);
        CREATE TABLE IF NOT EXISTS usage_events(
          id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, base TEXT NOT NULL,
          username TEXT, nas TEXT, session_id TEXT, mac TEXT, stamp INTEGER,
          status TEXT, seconds INTEGER, up INTEGER, down INTEGER, up_wide INTEGER, down_wide INTEGER);
        CREATE INDEX IF NOT EXISTS usage_events_base ON usage_events(base,stamp,id);
        CREATE TABLE IF NOT EXISTS usage_deltas(
          event_id INTEGER PRIMARY KEY, base TEXT, session_key TEXT, username TEXT, stamp INTEGER,
          up INTEGER, down INTEGER, has_up INTEGER, has_down INTEGER);
        CREATE INDEX IF NOT EXISTS usage_deltas_date ON usage_deltas(stamp,username);
        CREATE INDEX IF NOT EXISTS usage_deltas_base ON usage_deltas(base);
        CREATE TABLE IF NOT EXISTS usage_sessions(
          session_key TEXT PRIMARY KEY, base TEXT, username TEXT, nas TEXT, session_id TEXT,
          mac TEXT, first_seen INTEGER, last_seen INTEGER, status TEXT, seconds INTEGER,
          up INTEGER, down INTEGER, has_up INTEGER, has_down INTEGER, counter_decreases INTEGER);
        CREATE INDEX IF NOT EXISTS usage_sessions_base ON usage_sessions(base);
        CREATE INDEX IF NOT EXISTS usage_sessions_date ON usage_sessions(last_seen);
        ''')
        if 'tail' not in {r[1] for r in c.execute('PRAGMA table_info(usage_cursors)')}:
            c.execute('ALTER TABLE usage_cursors ADD COLUMN tail TEXT')


def integer(value, maximum=(1 << 63) - 1):
    try:
        value = int(value)
        return value if 0 <= value <= maximum else None
    except (TypeError, ValueError):
        return None


def counter(record, direction):
    low = integer(record.get('Acct-' + direction + '-Octets'), WRAP - 1)
    if low is None:
        return None, 0
    high = integer(record.get('Acct-' + direction + '-Gigawords'), (1 << 31) - 1)
    return (low + (high or 0) * WRAP), int(high is not None)


def parse(block, source, fallback_stamp):
    record = {}
    for line in block.decode(errors='replace').splitlines():
        match = re.match(r'\s+([A-Za-z0-9-]+) = (.*)', line)
        if match:
            record[match[1]] = match[2].strip().strip('"')
    if not record.get('Acct-Session-Id') or not record.get('User-Name'):
        return None
    status = record.get('Acct-Status-Type')
    if status not in ('Start', 'Interim-Update', 'Stop'):
        return None
    stamp = integer(record.get('Timestamp')) or int(fallback_stamp)
    # Timestamp is the local receive time; compensate known retransmit delay.
    stamp -= integer(record.get('Acct-Delay-Time'), 86400 * 365) or 0
    up, up_wide = counter(record, 'Input')
    down, down_wide = counter(record, 'Output')
    username = record['User-Name']
    nas = record.get('NAS-IP-Address') or record.get('NAS-IPv6-Address') or source
    session_id = record['Acct-Session-Id']
    mac = record.get('Calling-Station-Id', '')
    identity = [source, nas, record.get('NAS-Identifier', ''), session_id, username, mac]
    base = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    values = [base, username, nas, session_id, mac, stamp, status,
              integer(record.get('Acct-Session-Time')), up, down, up_wide, down_wide]
    fingerprint = hashlib.sha256(json.dumps(values).encode()).hexdigest()
    return [fingerprint, *values]


def rebuild(c, base):
    """Recompute one NAS/session identity so delayed reports cannot inflate totals."""
    c.execute('DELETE FROM usage_deltas WHERE base=?', (base,))
    c.execute('DELETE FROM usage_sessions WHERE base=?', (base,))
    groups = []
    current = None
    for r in c.execute('SELECT * FROM usage_events WHERE base=? ORDER BY stamp,id', (base,)).fetchall():
        # An active identity's retransmitted Start must never count its bytes twice.
        # A reused identity is a new generation only after an observed Stop.
        new = current is None or (r['status'] == 'Start' and current['status'] == 'Stop')
        if r['status'] == 'Start' and current is not None and not new:
            continue
        if new:
            current = {'session_key': f'{base}:{r["id"]}', 'base': base, 'username': r['username'],
                'nas': r['nas'], 'session_id': r['session_id'], 'mac': r['mac'],
                'first_seen': r['stamp'], 'last_seen': r['stamp'], 'status': r['status'],
                'seconds': 0, 'up': 0, 'down': 0, 'has_up': 0, 'has_down': 0,
                'counter_decreases': 0, 'wrap_up': 0, 'wrap_down': 0,
                'last_low_up': None, 'last_low_down': None}
            groups.append(current)
        duration = r['seconds']
        if duration is not None and duration < current['seconds'] and r['status'] != 'Start':
            # An older cumulative report arriving late is not a new contribution.
            continue
        if current['status'] == 'Stop' and r['status'] != 'Stop' and not new:
            continue
        deltas = {}
        for name in ('up', 'down'):
            value = r[name]
            deltas[name] = 0
            if value is None:
                continue
            old_low = current['last_low_' + name]
            if not r[name + '_wide']:
                # Infer only an unmistakable 32-bit wrap; ordinary decreases stay conservative.
                if old_low is not None and old_low >= 0xf0000000 and value <= 0x0fffffff and duration is not None and duration > current['seconds']:
                    current['wrap_' + name] += WRAP
                current['last_low_' + name] = value
                value += current['wrap_' + name]
            if value < current[name]:
                current['counter_decreases'] += 1
            deltas[name] = max(0, value - current[name])
            current[name] = max(current[name], value)
            current['has_' + name] = 1
        current['last_seen'] = max(current['last_seen'], r['stamp'])
        current['seconds'] = max(current['seconds'], duration or 0)
        current['status'] = r['status']
        c.execute('INSERT INTO usage_deltas VALUES (?,?,?,?,?,?,?,?,?)',
            (r['id'], base, current['session_key'], r['username'], r['stamp'],
             deltas['up'], deltas['down'], int(r['up'] is not None), int(r['down'] is not None)))
    for s in groups:
        c.execute('INSERT INTO usage_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple(s[k] for k in
            ('session_key','base','username','nas','session_id','mac','first_seen','last_seen','status',
             'seconds','up','down','has_up','has_down','counter_decreases')))


def ingest():
    from . import main as m
    budget, backlog, changed = MAX_PASS, False, set()
    with m.LOCK, m.db() as c:
        root = m.DATA / 'accounting'
        for path in sorted(root.glob('*/detail-*')):
            if not path.is_file():
                continue
            stat = path.stat()
            relative = path.relative_to(root).as_posix()
            with path.open('rb') as stream:
                prefix = stream.read(128)
                signature = str(stat.st_ino) + ':' + hashlib.sha256(prefix).hexdigest()
                previous = c.execute('SELECT * FROM usage_cursors WHERE path=?', (relative,)).fetchone()
                offset = previous['offset'] if previous and previous['signature'] == signature and previous['offset'] <= stat.st_size else 0
                if offset and previous['tail']:
                    stream.seek(max(0, offset - 128))
                    if hashlib.sha256(stream.read(min(128, offset))).hexdigest() != previous['tail']:
                        offset = 0
                if offset == stat.st_size:
                    continue
                if budget <= 0:
                    backlog = True
                    continue
                stream.seek(offset)
                chunk = stream.read(min(MAX_FILE, budget))
            budget -= len(chunk)
            separators = list(re.finditer(rb'\r?\n[ \t]*\r?\n', chunk))
            if not separators:
                # A partial final record remains on disk for the next pass.
                if offset + len(chunk) < stat.st_size:
                    backlog = True
                if len(chunk) >= MAX_FILE:
                    LOG.warning('Skipping oversized malformed accounting block')
                    end = offset + len(chunk)
                    c.execute('INSERT OR REPLACE INTO usage_cursors VALUES (?,?,?,?)',
                              (relative, signature, end, tail_hash(path, end)))
                continue
            complete = separators[-1].end()
            for block in re.split(rb'\r?\n[ \t]*\r?\n', chunk[:complete]):
                event = parse(block, path.parent.name, stat.st_mtime)
                if event:
                    inserted = c.execute('INSERT OR IGNORE INTO usage_events(fingerprint,base,username,nas,session_id,mac,stamp,status,seconds,up,down,up_wide,down_wide) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', event)
                    if inserted.rowcount:
                        changed.add(event[1])
            end = offset + complete
            c.execute('INSERT OR REPLACE INTO usage_cursors VALUES (?,?,?,?)', (relative, signature, end, tail_hash(path, end)))
            if offset + complete < stat.st_size and complete < len(chunk):
                # A trailing partial packet is expected; only whole unread chunks imply backlog.
                backlog = backlog or offset + len(chunk) < stat.st_size
            elif offset + complete < stat.st_size:
                backlog = True
        for base in changed:
            rebuild(c, base)
    return backlog


def tail_hash(path, end):
    with path.open('rb') as stream:
        stream.seek(max(0, end - 128))
        return hashlib.sha256(stream.read(min(128, end))).hexdigest()


def sessions(c, username='', now=None):
    now = time.time() if now is None else now
    rows = c.execute('SELECT * FROM usage_sessions ' + ('WHERE username=? ' if username else '') +
                     'ORDER BY last_seen DESC LIMIT 200', (username,) if username else ()).fetchall()
    return [{'session_id': r['session_id'], 'username': r['username'], 'nas': r['nas'], 'mac': r['mac'],
             'state': r['status'], 'seconds': r['seconds'], 'timestamp': r['last_seen'],
             'upload_bytes': r['up'] if r['has_up'] else None,
             'download_bytes': r['down'] if r['has_down'] else None,
             'total_bytes': r['up'] + r['down'] if r['has_up'] or r['has_down'] else None,
             'reporting': r['status'] != 'Stop' and now - r['last_seen'] <= 900,
             'counter_decreases': r['counter_decreases']} for r in rows]


def report(period='month', offset=0, username='', now=None, timezone_name=''):
    from . import main as m
    backlog = ingest()
    zone = ZoneInfo(timezone_name) if timezone_name else timezone(timedelta(minutes=offset))
    local = datetime.fromtimestamp(time.time() if now is None else now, zone)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    starts = {'today': midnight, 'month': midnight.replace(day=1),
              '7days': midnight - timedelta(days=6), '30days': midnight - timedelta(days=29)}
    start = int(starts[period].timestamp()) if period != 'all' else 0
    where = 'd.stamp>=?' + (' AND d.username=?' if username else '')
    args = (start, username) if username else (start,)
    with m.db() as c:
        c.create_function('usage_day', 1, lambda stamp: datetime.fromtimestamp(stamp, zone).strftime('%Y-%m-%d'))
        c.create_function('usage_month', 1, lambda stamp: datetime.fromtimestamp(stamp, zone).strftime('%Y-%m'))
        users = [dict(r) for r in c.execute(f'''SELECT d.username,COALESCE(u.display_name,d.username) display_name,
          SUM(d.up) upload_bytes,SUM(d.down) download_bytes,SUM(d.up+d.down) total_bytes,
          MAX(d.has_up) has_upload,MAX(d.has_down) has_download,
          COUNT(DISTINCT d.session_key) sessions,MAX(d.stamp) last_seen
          FROM usage_deltas d LEFT JOIN users u ON u.username=d.username WHERE {where}
          GROUP BY d.username ORDER BY total_bytes DESC,d.username''', args)]
        daily = [dict(r) for r in c.execute(f'''SELECT usage_day(d.stamp) day,
          SUM(d.up) upload_bytes,SUM(d.down) download_bytes,SUM(d.up+d.down) total_bytes,
          MAX(d.has_up) has_upload,MAX(d.has_down) has_download
          FROM usage_deltas d WHERE {where} AND d.stamp>=? GROUP BY day ORDER BY day''',
          (*args, int((midnight - timedelta(days=30)).timestamp())))]
        monthly = [dict(r) for r in c.execute('''SELECT usage_month(stamp) month,
          SUM(up) upload_bytes,SUM(down) download_bytes,SUM(up+down) total_bytes,
          MAX(has_up) has_upload,MAX(has_down) has_download
          FROM usage_deltas ''' + ('WHERE username=? ' if username else '') +
          'GROUP BY month ORDER BY month DESC LIMIT 12', (username,) if username else ())]
        latest = sessions(c, username, local.timestamp())
        global_last = c.execute('SELECT MAX(stamp) FROM usage_events').fetchone()[0]
        decreases = c.execute('SELECT SUM(counter_decreases) FROM usage_sessions').fetchone()[0] or 0
        recent = c.execute('SELECT COUNT(*) FROM usage_sessions WHERE status!=? AND last_seen>=?' +
                           (' AND username=?' if username else ''),
                           ('Stop', int(local.timestamp()) - 900, username) if username else
                           ('Stop', int(local.timestamp()) - 900)).fetchone()[0]
    total = sum(r['total_bytes'] for r in users)
    for row in users:
        row['share'] = row['total_bytes'] / total * 100 if total else 0
    return {'period': period, 'offset_minutes': offset, 'timezone': timezone_name, 'username': username, 'users': users,
            'daily': daily, 'monthly': monthly, 'sessions': latest,
            'summary': {'upload_bytes': sum(r['upload_bytes'] for r in users),
                        'download_bytes': sum(r['download_bytes'] for r in users), 'total_bytes': total,
                        'users': len(users), 'recent_sessions': recent,
                        'has_upload': any(r['has_upload'] for r in users),
                        'has_download': any(r['has_download'] for r in users)},
            'last_report': global_last, 'backlog': backlog, 'counter_decreases': decreases,
            'generated_at': int(local.timestamp())}


def worker(stop):
    while not stop.is_set():
        try:
            backlog = ingest()
        except Exception:
            LOG.exception('Accounting ingestion failed')
            backlog = False
        stop.wait(1 if backlog else 15)


def register_usage(app, admin):
    from fastapi import Depends, HTTPException

    @app.get('/api/usage', dependencies=[Depends(admin)])
    def usage(period: str = 'month', offset_minutes: int = 0, username: str = '', timezone_name: str = ''):
        if period not in ('today', 'month', '7days', '30days', 'all') or not -840 <= offset_minutes <= 840 or len(username) > 150 or len(timezone_name) > 100:
            raise HTTPException(422, 'Invalid report period, timezone offset or username')
        try:
            return report(period, offset_minutes, username, timezone_name=timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, 'Unknown reporting time zone')
