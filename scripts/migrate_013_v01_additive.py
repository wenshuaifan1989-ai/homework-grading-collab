"""Only create five additive geometry/audit tables in isolated loopback DB."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from sqlalchemy.engine.url import make_url
from config import settings
from utils.database import engine
from models.base import Base
from models.known_assignment import PageTemplate, QuestionPlacement, KnownPageMatch, ChoiceRead, ChoiceReviewAudit

TABLES=[c.__table__ for c in (PageTemplate,QuestionPlacement,KnownPageMatch,ChoiceRead,ChoiceReviewAudit)]

def migrate(target):
    existing=inspect(target).get_table_names()
    # Preserve ALL existing rows, not just nine protected tables.
    with target.connect() as conn:
        before={n:conn.execute(text(f'SELECT COUNT(*) FROM `{n}`')).scalar_one() for n in existing}
    Base.metadata.create_all(target,tables=TABLES,checkfirst=True)
    with target.connect() as conn:
        after={n:conn.execute(text(f'SELECT COUNT(*) FROM `{n}`')).scalar_one() for n in existing}
    if before!=after:raise RuntimeError('Existing table row counts changed')
    return {'migration':'013-V01','before':before,'after':after,'existing_rows_unchanged':before==after,'tables':[t.name for t in TABLES]}

if __name__=='__main__':
    url=make_url(settings.DATABASE_URL)
    if '--target-local-demo' not in sys.argv or url.host not in ('127.0.0.1','localhost') or url.database!='homework_grading_local':
        raise SystemExit('Refusing non-isolated local database')
    print(json.dumps(migrate(engine),indent=2))
