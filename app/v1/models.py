from fastapi import APIRouter, HTTPException
from config import settings, ModelConfig
from schemas.model import ModelInfo, ModelsResponse, ModelToggleRequest
from utils.logger import logger

router = APIRouter(prefix="/models", tags=["模型管理"])


@router.get("")
async def list_models():
    """获取所有可用模型列表"""
    models_list = [
        {
            "name": m.name, 
            "provider": m.provider, 
            "type": m.type,
            "model_id": m.model_id, 
            "enabled": m.enabled,
            "max_tokens": m.max_tokens,
            "temperature": m.temperature,
        }
        for m in settings.parsed_models
    ]
    return {
        "code": 200,
        "message": "success",
        "data": {"models": models_list},
    }


@router.get("/stats")
async def get_models_stats():
    """获取模型统计信息"""
    all_models = settings.parsed_models
    text_count = len([m for m in all_models if m.type == "text"])
    vision_count = len([m for m in all_models if m.type == "vision"])
    enabled_count = len([m for m in all_models if m.enabled])
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": len(all_models),
            "text_count": text_count,
            "vision_count": vision_count,
            "enabled_count": enabled_count,
            "disabled_count": len(all_models) - enabled_count,
        }
    }


@router.get("/types/{model_type}")
async def list_models_by_type(model_type: str):
    """按类型获取模型列表"""
    if model_type not in ["text", "vision"]:
        raise HTTPException(status_code=400, detail="无效的模型类型")
    
    models_list = [
        {
            "name": m.name, 
            "provider": m.provider, 
            "type": m.type,
            "model_id": m.model_id, 
            "enabled": m.enabled,
        }
        for m in settings.parsed_models 
        if m.type == model_type and m.enabled
    ]
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "models": models_list,
            "type": model_type,
            "count": len(models_list),
        }
    }


@router.get("/{model_name}")
async def get_model(model_name: str):
    """获取单个模型详情"""
    model = settings.get_model_by_name(model_name)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "name": model.name,
            "provider": model.provider,
            "type": model.type,
            "model_id": model.model_id,
            "enabled": model.enabled,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
            "base_url": model.base_url,
        }
    }


@router.put("/{model_name}/toggle")
async def toggle_model(model_name: str, request: ModelToggleRequest):
    """启用/禁用模型"""
    model = settings.get_model_by_name(model_name)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    
    model.enabled = request.enabled
    logger.info(f"模型状态更新: {model_name} -> {'启用' if request.enabled else '禁用'}")
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "name": model.name,
            "enabled": model.enabled,
        }
    }
