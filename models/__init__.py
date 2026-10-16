from .user import User
from .homework import (
    HomeworkTask,
    HomeworkImage,
    QuestionBlock,
    OCRResult,
    StandardAnswer,
    GradingResult,
)
from .knowledge import KnowledgePoint
from .classroom import Class, ClassMember, StudentRoster, Assignment
from .user_role import UserRole
from .identity_relations import Student, StudentUserBinding, ClassTeacher, Contract, School
from .paper import (
    QuestionAsset,
    QuestionAssetSource,
    QuestionDigitizationRun,
    MistakeRecord,
    PaperCorrectionAttempt,
)
from .model_usage import ModelCallAudit, ModelDailyUsage
from .submission import HomeworkSubmissionKey
from .learning import (
    StudentSubjectTier,
    StudentSubjectTierAudit,
    AssignmentVariantSet,
    AssignmentVariant,
    AssignmentVariantQuestion,
    AssignmentVariantTask,
)
from .assignment_plan import AssignmentPlan, AssignmentPlanQuestion
from .learning_advice import EvidenceSnapshot, TierSuggestion, SuggestionDecision, PracticeRecommendation
from .known_assignment import PageTemplate, QuestionPlacement, KnownPageMatch, ChoiceRead, ChoiceReviewAudit

__all__ = [
    "User",
    "HomeworkTask",
    "HomeworkImage",
    "QuestionBlock",
    "OCRResult",
    "StandardAnswer",
    "GradingResult",
    "KnowledgePoint",
    "Class",
    "ClassMember",
    "StudentRoster",
    "Assignment",
    "UserRole",
    "Student",
    "StudentUserBinding",
    "ClassTeacher",
    "Contract",
    "School",
    "QuestionAsset",
    "QuestionAssetSource",
    "QuestionDigitizationRun",
    "MistakeRecord",
    "PaperCorrectionAttempt",
    "ModelCallAudit",
    "ModelDailyUsage",
    "HomeworkSubmissionKey",
    "StudentSubjectTier",
    "StudentSubjectTierAudit",
    "AssignmentVariantSet",
    "AssignmentVariant",
    "AssignmentVariantQuestion",
    "AssignmentVariantTask",
    "AssignmentPlan",
    "AssignmentPlanQuestion",
    "PageTemplate", "QuestionPlacement", "KnownPageMatch", "ChoiceRead", "ChoiceReviewAudit",
]
