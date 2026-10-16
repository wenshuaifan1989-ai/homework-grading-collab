"""Four additive 014 tables; rollback only when all four are empty."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect,text
from sqlalchemy.engine.url import make_url
from config import settings
from utils.database import engine
from models.base import Base
from models.learning_advice import EvidenceSnapshot,TierSuggestion,SuggestionDecision,PracticeRecommendation
TABLES=[c.__table__ for c in (EvidenceSnapshot,TierSuggestion,SuggestionDecision,PracticeRecommendation)]

def migrate(target,rollback=False):
    existing=inspect(target).get_table_names()
    with target.connect() as conn:
        before={n:conn.execute(text(f'SELECT COUNT(*) FROM `{n}`')).scalar_one() for n in existing}
    if rollback:
        if any(before.get(t.name,0) for t in TABLES):raise RuntimeError('Refusing rollback: retain nonempty 014 records/audits')
        Base.metadata.drop_all(target,tables=list(reversed(TABLES)),checkfirst=True)
    else:
        Base.metadata.create_all(target,tables=TABLES,checkfirst=True)
    remaining=set(inspect(target).get_table_names())
    with target.connect() as conn:
        after={n:conn.execute(text(f'SELECT COUNT(*) FROM `{n}`')).scalar_one() for n in before if n in remaining}
    protected={n:v for n,v in before.items() if n in remaining}
    if protected!=after:raise RuntimeError('Existing data changed during migration')
    return {'migration':'014','rollback':rollback,'before':before,'after':after,'existing_rows_unchanged':True,'tables':[t.name for t in TABLES if t.name in remaining]}

if __name__=='__main__':
    url=make_url(settings.DATABASE_URL)
    if '--target-local-demo' not in sys.argv or url.host not in ('127.0.0.1','localhost') or url.database!='homework_grading_local':raise SystemExit('Refusing nonisolated local database')
    print(json.dumps(migrate(engine,'--rollback-empty' in sys.argv),indent=2))
