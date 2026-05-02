# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import logging
import asyncio
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/habit", tags=["习惯学习"])


def _get_habit_dao():
    from miloco_server.dao.habit_dao import HabitDAO
    existing = HabitDAO.get_instance()
    if existing is not None:
        return existing
    from miloco_server.utils.database import get_db_connector
    db = get_db_connector()
    dao = HabitDAO(db)
    dao.initialize()
    return dao


async def _ensure_collector():
    from miloco_server.service.habit_collector import HabitCollector
    collector = HabitCollector.get_instance()
    if collector is not None:
        return collector

    from miloco_server.config.normal_config import HABIT_LEARNING_CONFIG
    collector_config = HABIT_LEARNING_CONFIG.get("collector", {})
    noise_config = collector_config.get("noise_filter", {})

    habit_dao = _get_habit_dao()
    from miloco_server.service.context_provider import ContextProvider
    ctx_provider = ContextProvider.get_instance()
    collector = HabitCollector(
        habit_dao=habit_dao,
        flush_interval=collector_config.get("flush_interval", 5),
        context_provider=ctx_provider,
    )

    if noise_config.get("ignore_states"):
        collector._noise_states.update(noise_config["ignore_states"])
    if noise_config.get("ignore_entities"):
        collector._noise_entities.update(noise_config["ignore_entities"])

    await collector.start()
    logger.info("HabitCollector created and started by controller")
    return collector


@router.get("/stats")
async def get_habit_stats():
    try:
        from miloco_server.service.habit_collector import HabitCollector
        from miloco_server.service.behavior_learner import BehaviorLearner
        from miloco_server.service.decision_engine import DecisionEngine
        from miloco_server.config.normal_config import HABIT_LEARNING_CONFIG

        config = HABIT_LEARNING_CONFIG
        collector_stats = {}
        learner_stats = {}
        engine_stats = {}

        collector = HabitCollector.get_instance()
        if collector:
            collector_stats = collector.get_stats()

        learner = BehaviorLearner.get_instance()
        if learner:
            learner_stats = learner.get_stats()

        engine = DecisionEngine.get_instance()
        if engine:
            engine_stats = engine.get_stats()

        habit_dao = _get_habit_dao()
        event_stats = habit_dao.get_event_stats()

        is_enabled = config.get("enabled", False) or bool(collector)

        return {
            "success": True,
            "stats": {
                "enabled": is_enabled,
                "collector": collector_stats,
                "learner": learner_stats,
                "engine": engine_stats,
                "events": event_stats,
                "config": {
                    "collector": config.get("collector", {}),
                    "learner": config.get("learner", {}),
                    "decision_engine": config.get("decision_engine", {}),
                },
            },
        }
    except Exception as e:
        logger.error("获取习惯学习统计失败: %s", e, exc_info=True)
        return {
            "success": True,
            "stats": {
                "enabled": False,
                "collector": {},
                "learner": {},
                "engine": {},
                "events": {"total_events": 0, "table_stats": [], "total_patterns": 0},
                "config": {},
            },
        }


@router.get("/patterns")
async def get_patterns(
    min_confidence: float = Query(0.3, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=1000),
):
    try:
        habit_dao = _get_habit_dao()
        patterns = habit_dao.get_all_patterns(min_confidence=min_confidence)
        patterns = patterns[:limit]

        entity_names = {}
        try:
            from miloco_server.service.context_provider import ContextProvider
            provider = ContextProvider.get_instance()
            if provider:
                all_entities = provider.get_all_entities()
                for entity in all_entities:
                    entity_names[entity["entity_id"]] = entity["friendly_name"] or entity["entity_id"]
        except Exception:
            pass

        result_patterns = []
        for p in patterns:
            p_dict = p.to_dict()
            entity_id = p.entity_id
            if entity_id and entity_id in entity_names:
                p_dict["entity_name"] = entity_names[entity_id]
            else:
                p_dict["entity_name"] = entity_id or "未知实体"
            result_patterns.append(p_dict)

        return {
            "success": True,
            "patterns": result_patterns,
            "total": len(result_patterns),
        }
    except Exception as e:
        logger.error("获取行为模式失败: %s", e)
        return {"success": True, "patterns": [], "total": 0}


@router.get("/predictions")
async def get_predictions():
    try:
        from datetime import datetime
        from miloco_server.service.behavior_learner import BehaviorLearner
        from miloco_server.schema.habit_schema import PredictionContext

        learner = BehaviorLearner.get_instance()
        if learner is None:
            return {"success": True, "predictions": [], "total": 0}

        now = datetime.now()
        context = PredictionContext(
            current_time=now,
            day_of_week=now.weekday(),
            hour_of_day=now.hour,
            minute_of_hour=now.minute,
            is_weekend=now.weekday() >= 5,
        )
        predictions = await learner.predict()

        entity_names = {}
        try:
            from miloco_server.service.context_provider import ContextProvider
            provider = ContextProvider.get_instance()
            if provider:
                all_entities = provider.get_all_entities()
                for entity in all_entities:
                    entity_names[entity["entity_id"]] = entity["friendly_name"] or entity["entity_id"]
        except Exception:
            pass

        result_predictions = []
        for p in predictions:
            p_dict = p.to_dict()
            entity_id = p.entity_id
            if entity_id and entity_id in entity_names:
                p_dict["entity_name"] = entity_names[entity_id]
            else:
                p_dict["entity_name"] = entity_id or "未知实体"
            result_predictions.append(p_dict)

        return {
            "success": True,
            "predictions": result_predictions,
            "total": len(result_predictions),
        }
    except Exception as e:
        logger.error("获取预测结果失败: %s", e)
        return {"success": True, "predictions": [], "total": 0}


@router.post("/train")
async def trigger_training():
    try:
        from miloco_server.service.behavior_learner import BehaviorLearner
        from miloco_server.service.model_trainer import ModelTrainer

        learner = BehaviorLearner.get_instance()
        if learner is None:
            raise HTTPException(status_code=400, detail="行为学习服务未初始化，请检查习惯学习是否启用")

        habit_dao = _get_habit_dao()
        trainer = ModelTrainer(behavior_learner=learner, habit_dao=habit_dao)
        result = await trainer.train_all()
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("手动训练失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collector/enable")
async def enable_collector():
    try:
        collector = await _ensure_collector()
        collector.set_enabled(True)
        return {"success": True, "message": "采集服务已启用"}
    except Exception as e:
        logger.error("启用采集服务失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collector/disable")
async def disable_collector():
    try:
        collector = await _ensure_collector()
        collector.set_enabled(False)
        return {"success": True, "message": "采集服务已禁用"}
    except Exception as e:
        logger.error("禁用采集服务失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/engine/enable")
async def enable_engine():
    try:
        from miloco_server.service.decision_engine import DecisionEngine
        from miloco_server.config.normal_config import update_habit_config

        engine = DecisionEngine.get_instance()
        if engine is None:
            raise HTTPException(status_code=400, detail="决策引擎实例不存在，请重启服务")

        if engine._running:
            update_habit_config("decision_engine", "enabled", "true")
            return {"success": True, "running": True, "message": "决策引擎已在运行中"}

        await engine.start()
        update_habit_config("decision_engine", "enabled", "true")
        return {"success": True, "running": True, "message": "决策引擎已启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("启用决策引擎失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/engine/disable")
async def disable_engine():
    try:
        from miloco_server.service.decision_engine import DecisionEngine
        from miloco_server.config.normal_config import update_habit_config

        engine = DecisionEngine.get_instance()
        if engine is None:
            return {"success": True, "running": False, "message": "决策引擎未运行"}

        if not engine._running:
            update_habit_config("decision_engine", "enabled", "false")
            return {"success": True, "running": False, "message": "决策引擎未运行"}

        await engine.stop()
        update_habit_config("decision_engine", "enabled", "false")
        return {"success": True, "running": False, "message": "决策引擎已停止"}
    except Exception as e:
        logger.error("停止决策引擎失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class UpdateConfigRequest(BaseModel):
    section: str
    key: str
    value: str


@router.get("/context")
async def get_context():
    try:
        from miloco_server.service.context_provider import ContextProvider
        provider = ContextProvider.get_instance()
        if provider is None:
            return {"temperature": None, "humidity": None, "is_home": True, "is_anyone_present": True}
        env = provider.get_context()
        return env.to_dict()
    except Exception as e:
        logger.error("获取环境上下文失败: %s", e)
        return {"temperature": None, "humidity": None, "is_home": True, "is_anyone_present": True}


@router.get("/context/entities")
async def get_context_entities():
    try:
        from miloco_server.config.normal_config import get_context_entities_config
        from miloco_server.service.context_provider import ContextProvider, CONTEXT_ENTITY_KEYS
        provider = ContextProvider.get_instance()
        saved = get_context_entities_config()
        live = provider.get_context_entities() if provider else {}
        return {
            "configured": saved,
            "live": live,
            "available_keys": CONTEXT_ENTITY_KEYS,
        }
    except Exception as e:
        logger.error("获取上下文实体配置失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class ContextEntitiesRequest(BaseModel):
    entities: Dict[str, str]


@router.get("/context/debug")
async def debug_context():
    from miloco_server.service.context_provider import ContextProvider
    provider = ContextProvider.get_instance()
    if not provider:
        return {"error": "ContextProvider not initialized", "hint": "habit_learning may be disabled"}
    states = provider._get_all_states()
    configured = provider.get_context_entities()
    debug = {"states_count": len(states), "configured_entities": configured, "entity_lookup": {}}
    for key, entity_id in configured.items():
        state_obj = states.get(entity_id, {})
        debug["entity_lookup"][key] = {
            "entity_id": entity_id,
            "found_in_cache": entity_id in states,
            "state": state_obj.get("state") if state_obj else None,
            "attributes_keys": list(state_obj.get("attributes", {}).keys()) if state_obj else [],
        }
    return debug


@router.get("/context/all_entities")
async def get_all_ha_entities():
    from miloco_server.service.context_provider import ContextProvider
    provider = ContextProvider.get_instance()
    if not provider:
        return []
    return provider.get_all_entities()


@router.post("/context/entities")
async def save_context_entities(request: ContextEntitiesRequest):
    try:
        from miloco_server.config.normal_config import save_context_entities_config
        from miloco_server.service.context_provider import CONTEXT_ENTITY_KEYS
        valid_keys = set(CONTEXT_ENTITY_KEYS)
        filtered = {k: v for k, v in request.entities.items() if k in valid_keys and v}
        success = save_context_entities_config(filtered)
        if not success:
            raise HTTPException(status_code=400, detail="保存上下文实体配置失败")
        from miloco_server.service.context_provider import ContextProvider
        provider = ContextProvider.get_instance()
        if provider:
            provider.set_context_entities(filtered)
        return {"success": True, "entities": filtered, "message": "上下文实体配置已保存"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("保存上下文实体配置失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(request: UpdateConfigRequest):
    try:
        from miloco_server.config.normal_config import update_habit_config
        success = update_habit_config(request.section, request.key, request.value)
        if success:
            return {"success": True, "message": "配置已更新"}
        raise HTTPException(status_code=400, detail="更新配置失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新配置失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
