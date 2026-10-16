from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from utils.database import get_db
from models.homework import HomeworkTask, GradingResult
from models.user import User
from schemas.common import APIResponse
from utils.logger import logger
from utils.deps import get_current_user

router = APIRouter(prefix="/statistics", tags=["统计分析"])


@router.get("/user/{user_id}", response_model=APIResponse)
async def get_user_statistics(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户统计信息"""
    try:
        if current_user.id != user_id:
            raise HTTPException(status_code=404, detail="统计信息不存在")
        # 统计用户提交的作业数量
        task_count = (
            db.query(func.count(HomeworkTask.id))
            .filter(HomeworkTask.user_id == user_id)
            .scalar()
        )

        # 统计已完成的作业数量
        completed_count = (
            db.query(func.count(HomeworkTask.id))
            .filter(HomeworkTask.user_id == user_id, HomeworkTask.status == "SUCCESS")
            .scalar()
        )

        # 统计平均得分
        avg_score = (
            db.query(func.avg(HomeworkTask.total_score))
            .filter(HomeworkTask.user_id == user_id, HomeworkTask.status == "SUCCESS")
            .scalar()
        )

        # 获取最近一次作业得分
        latest_task = (
            db.query(HomeworkTask)
            .filter(HomeworkTask.user_id == user_id, HomeworkTask.status == "SUCCESS")
            .order_by(HomeworkTask.created_at.desc())
            .first()
        )
        latest_score = float(latest_task.total_score) if latest_task else 0

        avg_accuracy = (
            db.query(func.avg(GradingResult.accuracy))
            .join(HomeworkTask, GradingResult.task_id == HomeworkTask.task_id)
            .filter(HomeworkTask.user_id == user_id, HomeworkTask.status == "SUCCESS")
            .scalar()
        )

        return APIResponse(
            data={
                "task_count": task_count,
                "completed_count": completed_count,
                "avg_score": float(avg_score) if avg_score else 0,
                "avg_accuracy": float(avg_accuracy) if avg_accuracy else 0,
                "latest_score": latest_score,
            }
        )

    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"获取用户统计信息失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取用户统计信息失败")


@router.get("/global", response_model=APIResponse)
async def get_global_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取全局统计信息"""
    try:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="无权查看全局统计")
        # 统计总用户数
        user_count = db.query(func.count(User.id)).scalar()

        # 统计总作业数
        task_count = db.query(func.count(HomeworkTask.id)).scalar()

        # 统计已完成作业数
        completed_count = (
            db.query(func.count(HomeworkTask.id))
            .filter(HomeworkTask.status == "SUCCESS")
            .scalar()
        )

        # 统计平均得分
        avg_score = (
            db.query(func.avg(HomeworkTask.total_score))
            .filter(HomeworkTask.status == "SUCCESS")
            .scalar()
        )

        avg_accuracy = (
            db.query(func.avg(GradingResult.accuracy))
            .join(HomeworkTask, GradingResult.task_id == HomeworkTask.task_id)
            .filter(HomeworkTask.status == "SUCCESS")
            .scalar()
        )

        return APIResponse(
            data={
                "user_count": user_count,
                "task_count": task_count,
                "completed_count": completed_count,
                "avg_score": float(avg_score) if avg_score else 0,
                "avg_accuracy": float(avg_accuracy) if avg_accuracy else 0,
            }
        )

    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"获取全局统计信息失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取全局统计信息失败")
