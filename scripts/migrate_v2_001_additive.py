"""Three additive V2 tables. Nonempty snapshots are never dropped."""
import json
import sys
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from models.teacher_v2 import PaperBatch, PaperDocument, AssignmentPublication

TABLES = [c.__table__ for c in (PaperBatch, PaperDocument, AssignmentPublication)]


def migrate(target, rollback=False):
    before = set(inspect(target).get_table_names())
    if rollback:
        with target.connect() as conn:
            if any(conn.execute(text(f'SELECT COUNT(*) FROM `{t.name}`')).scalar_one()
                   for t in TABLES if t.name in before):
                raise ValueError('Refusing rollback of nonempty V2 tables')
        for table in reversed(TABLES):
            table.drop(target, checkfirst=True)
    else:
        for table in TABLES:
            table.create(target, checkfirst=True)
    after = set(inspect(target).get_table_names())
    return {'migration': 'V2-001', 'rollback': rollback,
            'created': sorted(after-before), 'removed': sorted(before-after),
            'legacy_tables_preserved': not (before-{t.name for t in TABLES})-after}


if __name__ == '__main__':
    from config import settings
    from sqlalchemy.engine.url import make_url
    from utils.database import engine
    url = make_url(settings.DATABASE_URL)
    if '--target-local-demo' not in sys.argv or url.host not in ('localhost', '127.0.0.1') or url.port != 3307 or url.database != 'homework_grading_local':
        raise SystemExit('Refusing database other than isolated local 3307/homework_grading_local')
    # One protected local-only dump before first table creation. Never send DB contents to governance.
    if not inspect(engine).has_table('v2_paper_batch') and '--rollback-empty' not in sys.argv:
        destination=Path(__file__).resolve().parents[1]/'.localdemo/backups'
        destination.mkdir(parents=True,exist_ok=True)
        backup=destination/f'pre-v2-001-{datetime.now():%Y%m%d-%H%M%S}.sql'
        with backup.open('xb') as stream:
            outcome=subprocess.run([r'D:\Docker\Docker\resources\bin\docker.exe','exec',
                'homework-local010-mysql','mysqldump','-uroot','--single-transaction',
                '--hex-blob','--routines','--triggers','--no-tablespaces','homework_grading_local'],
                stdout=stream,stderr=subprocess.PIPE,check=False)
        if outcome.returncode or backup.stat().st_size<100:
            raise SystemExit('Local database backup failed; V2 migration not attempted')
        print(json.dumps({'backup_file':str(backup),'sha256':hashlib.sha256(backup.read_bytes()).hexdigest()}))
    print(json.dumps(migrate(engine, '--rollback-empty' in sys.argv)))
