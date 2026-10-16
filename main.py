from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from contextlib import asynccontextmanager
from config import settings
from app.v1 import homework, user, statistics, answers, models, classroom, school, relations, platform, paper, learning, assignment_plans, known_assignments
from utils.database import create_tables, SessionLocal
from utils.seed_data import check_standard_answers
from utils.logger import logger
from utils.exceptions import BusinessException


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    logger.info("启动服务...")
    if settings.AUTO_CREATE_TABLES:
        create_tables()
        db = SessionLocal()
        try:
            check_standard_answers(db)
        finally:
            db.close()
    else:
        logger.info("启动期自动建表与标准答案初始化已关闭")

    # 检查大模型配置
    model_list = settings.parsed_models
    if settings.is_llm_enabled:
        names = [m.name for m in settings.text_models]
        logger.info(f"大模型已启用: text_models={names}, grading_mode={settings.GRADING_MODE}")
    else:
        logger.warning("大模型未启用（MODELS_CONFIG 未配置或所有模型 disabled），批改将使用 Mock 模式")

    logger.info(f"服务启动成功，访问地址：http://{settings.HOST}:{settings.PORT}")
    yield
    logger.info("服务正在关闭...")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=app_lifespan,
)

# 配置CORS---中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


# 全局异常处理
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    logger.error(f"业务异常: {exc.message}")
    return JSONResponse(
        status_code=exc.code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.opt(exception=exc).error("系统异常: {}", str(exc))
    return JSONResponse(
        status_code=500, content={"code": 500, "message": "系统内部错误", "data": None}
    )


# 注册路由
app.include_router(homework.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")
app.include_router(statistics.router, prefix="/api/v1")
app.include_router(answers.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(classroom.router, prefix="/api/v1")
app.include_router(school.router, prefix="/api/v1")
app.include_router(relations.router, prefix="/api/v1")
app.include_router(platform.router, prefix="/api/v1")
app.include_router(paper.router, prefix="/api/v1")
app.include_router(learning.router, prefix="/api/v1")
app.include_router(assignment_plans.router, prefix="/api/v1")
app.include_router(known_assignments.router, prefix="/api/v1")
from app.v1 import learning_advice
app.include_router(learning_advice.router, prefix="/api/v1")
from app.v1 import teacher_v2
app.include_router(teacher_v2.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "message": "欢迎使用中小学作业批改系统 API",
    }


# 健康检查
@app.get("/status")
async def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/api/v1/config")
async def get_config():
    """获取系统配置"""
    from schemas.model import ConfigResponse
    return {
        "code": 200,
        "message": "success",
        "data": ConfigResponse(
            grading_mode=settings.GRADING_MODE,
            ocr_enabled=settings.is_aliyun_ocr_enabled,
            models_count=len(settings.parsed_models),
            upload_limits={
                "max_size": settings.MAX_UPLOAD_SIZE,
                "allowed_extensions": settings.ALLOWED_EXTENSIONS,
            },
            app_name=settings.APP_NAME,
            app_version=settings.APP_VERSION,
        ).model_dump(),
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
