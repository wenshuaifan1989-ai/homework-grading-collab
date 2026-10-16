"""标准答案数据检查，仅在应用启动时验证表是否存在数据。"""
from sqlalchemy.orm import Session
from models.homework import StandardAnswer
from utils.logger import logger


def check_standard_answers(db: Session):
    """检查标准答案表，若为空则提示通过 API 导入"""
    count = db.query(StandardAnswer).count()
    if count == 0:
        logger.warning("标准答案表为空，可通过 POST /api/v1/answers 批量导入或逐条添加")
    else:
        logger.info(f"标准答案表已有 {count} 条数据")
