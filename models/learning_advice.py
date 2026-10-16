"""014 additive evidence, teacher decisions and links to existing plans."""
from datetime import datetime
from sqlalchemy import BigInteger,Integer,String,Text,JSON,ForeignKey,DateTime,UniqueConstraint,Index,func
from sqlalchemy.orm import Mapped,mapped_column
from .base import Base
ID=BigInteger().with_variant(Integer,'sqlite')

class EvidenceSnapshot(Base):
    __tablename__='learning_evidence_snapshot'
    __table_args__=(UniqueConstraint('student_id','class_id','subject','evidence_hash',name='uq_learning_snapshot'),)
    id:Mapped[int]=mapped_column(ID,primary_key=True,autoincrement=True)
    student_id:Mapped[int]=mapped_column(ID,ForeignKey('student.id'))
    class_id:Mapped[int]=mapped_column(ID,ForeignKey('classroom.id'))
    subject:Mapped[str]=mapped_column(String(40))
    evidence_hash:Mapped[str]=mapped_column(String(64))
    evidence_json:Mapped[dict]=mapped_column(JSON)
    created_by:Mapped[int]=mapped_column(ID,ForeignKey('user.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())

class TierSuggestion(Base):
    __tablename__='tier_suggestion'
    __table_args__=(UniqueConstraint('snapshot_id','base_level','revision',name='uq_tier_suggestion_snapshot_level'),Index('ix_tier_suggestion_scope','class_id','subject','student_id'),)
    id:Mapped[int]=mapped_column(ID,primary_key=True,autoincrement=True)
    snapshot_id:Mapped[int]=mapped_column(ID,ForeignKey('learning_evidence_snapshot.id'))
    student_id:Mapped[int]=mapped_column(ID,ForeignKey('student.id'))
    class_id:Mapped[int]=mapped_column(ID,ForeignKey('classroom.id'))
    subject:Mapped[str]=mapped_column(String(40))
    base_level:Mapped[str]=mapped_column(String(10))
    revision:Mapped[int]=mapped_column(Integer,default=1)
    proposed_level:Mapped[str|None]=mapped_column(String(2),nullable=True)
    status:Mapped[str]=mapped_column(String(32))
    rationale_json:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())

class SuggestionDecision(Base):
    __tablename__='tier_suggestion_decision'
    __table_args__=(UniqueConstraint('suggestion_id','request_key',name='uq_suggestion_decision_key'),)
    id:Mapped[int]=mapped_column(ID,primary_key=True,autoincrement=True)
    suggestion_id:Mapped[int]=mapped_column(ID,ForeignKey('tier_suggestion.id'))
    request_key:Mapped[str]=mapped_column(String(64))
    action:Mapped[str]=mapped_column(String(20))
    from_level:Mapped[str|None]=mapped_column(String(2),nullable=True)
    to_level:Mapped[str|None]=mapped_column(String(2),nullable=True)
    reason:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[int]=mapped_column(ID,ForeignKey('user.id'))
    tier_audit_id:Mapped[int|None]=mapped_column(ID,ForeignKey('student_subject_tier_audit.id'),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())

class PracticeRecommendation(Base):
    __tablename__='practice_recommendation'
    __table_args__=(UniqueConstraint('teacher_id','request_key',name='uq_practice_teacher_key'),)
    id:Mapped[int]=mapped_column(ID,primary_key=True,autoincrement=True)
    teacher_id:Mapped[int]=mapped_column(ID,ForeignKey('user.id'))
    class_id:Mapped[int]=mapped_column(ID,ForeignKey('classroom.id'))
    subject:Mapped[str]=mapped_column(String(40))
    target_student_ids:Mapped[list]=mapped_column(JSON)
    snapshot_ids:Mapped[list]=mapped_column(JSON)
    knowledge_points:Mapped[list]=mapped_column(JSON)
    plan_id:Mapped[int|None]=mapped_column(ID,ForeignKey('assignment_plan.id'),nullable=True,unique=True)
    assignment_id:Mapped[int|None]=mapped_column(ID,ForeignKey('assignment.id'),nullable=True,unique=True)
    request_key:Mapped[str]=mapped_column(String(64))
    request_hash:Mapped[str]=mapped_column(String(64))
    status:Mapped[str]=mapped_column(String(32))
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
