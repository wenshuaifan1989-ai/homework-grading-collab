from .homework import router as homework_router
from .user import router as user_router
from .statistics import router as statistics_router
from .models import router as models_router
from .classroom import router as classroom_router
from .school import router as school_router
from .relations import router as relations_router
from .platform import router as platform_router
from .paper import router as paper_router
from .learning import router as learning_router
from .assignment_plans import router as assignment_plans_router

__all__ = [
    "homework_router",
    "user_router",
    "statistics_router",
    "models_router",
    "classroom_router",
    "school_router",
    "relations_router",
    "platform_router",
    "paper_router",
    "learning_router",
    "assignment_plans_router",
]
