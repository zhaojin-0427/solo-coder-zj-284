from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from typing import Optional, Dict

from models.maintenance_log import (
    MaintenanceLogCreate, MaintenanceLogUpdate, MaintenanceLog,
    FollowUpObservation, MaintenanceOperationType, OperationEffectiveness
)
from models import ApiResponse


router = APIRouter(prefix="/api/maintenance", tags=["植物养护操作日志与恢复效果追踪"])


def api_response(code: int, message: str, data=None) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": message, "data": data}
    )


@router.post("/log", response_model=ApiResponse, summary="记录养护操作")
async def create_maintenance_log(
    request: Request,
    data: MaintenanceLogCreate
):
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db
    zone_service = request.app.state.zone_service

    if data.target_type not in ["plant", "zone"]:
        return api_response(
            code=400,
            message="无效的目标类型，有效值为: plant, zone",
            data=None
        )

    if data.target_type == "plant":
        if data.target_id not in plants_db:
            return api_response(
                code=404,
                message=f"植物ID {data.target_id} 不存在",
                data=None
            )
    elif data.target_type == "zone":
        zone = zone_service.get_zone(data.target_id)
        if not zone:
            return api_response(
                code=404,
                message=f"分区ID {data.target_id} 不存在",
                data=None
            )

    if data.related_pest_disease_record_id:
        pest_service = request.app.state.pest_disease_service
        pest_record = pest_service.get_record(data.related_pest_disease_record_id)
        if not pest_record:
            return api_response(
                code=404,
                message=f"关联的病虫害记录ID {data.related_pest_disease_record_id} 不存在",
                data=None
            )

    try:
        log = maintenance_service.create_log(data)
    except Exception as e:
        return api_response(
            code=500,
            message=f"创建养护日志失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="养护操作记录已创建",
        data=log.model_dump(mode="json")
    )


@router.get("/logs", response_model=ApiResponse, summary="获取养护日志列表")
async def get_maintenance_logs(
    request: Request,
    target_type: Optional[str] = Query(None, description="目标类型筛选: plant, zone"),
    operation_type: Optional[str] = Query(None, description="操作类型筛选"),
    effectiveness: Optional[str] = Query(None, description="有效性筛选: very_effective, effective, partially_effective, ineffective, harmful, pending"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制")
):
    maintenance_service = request.app.state.maintenance_log_service

    if target_type and target_type not in ["plant", "zone"]:
        return api_response(
            code=400,
            message="无效的目标类型，有效值为: plant, zone",
            data=None
        )

    try:
        op_type_enum = MaintenanceOperationType(operation_type) if operation_type else None
        eff_enum = OperationEffectiveness(effectiveness) if effectiveness else None
    except ValueError as e:
        return api_response(
            code=400,
            message=f"参数无效: {str(e)}",
            data=None
        )

    try:
        logs = maintenance_service.get_all_logs(
            target_type=target_type,
            operation_type=op_type_enum,
            effectiveness=eff_enum,
            limit=limit
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取养护日志失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取到 {len(logs)} 条养护日志",
        data={
            "total": len(logs),
            "logs": [log.model_dump(mode="json") for log in logs]
        }
    )


@router.get("/logs/{log_id}", response_model=ApiResponse, summary="获取单条养护日志详情")
async def get_maintenance_log(
    request: Request,
    log_id: str
):
    maintenance_service = request.app.state.maintenance_log_service

    log = maintenance_service.get_log(log_id)
    if not log:
        return api_response(
            code=404,
            message=f"养护日志ID {log_id} 不存在",
            data=None
        )

    return api_response(
        code=200,
        message="获取养护日志详情成功",
        data=log.model_dump(mode="json")
    )


@router.put("/logs/{log_id}", response_model=ApiResponse, summary="更新养护日志")
async def update_maintenance_log(
    request: Request,
    log_id: str,
    update: MaintenanceLogUpdate
):
    maintenance_service = request.app.state.maintenance_log_service

    log = maintenance_service.get_log(log_id)
    if not log:
        return api_response(
            code=404,
            message=f"养护日志ID {log_id} 不存在",
            data=None
        )

    try:
        updated_log = maintenance_service.update_log(log_id, update)
    except Exception as e:
        return api_response(
            code=500,
            message=f"更新养护日志失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="养护日志已更新",
        data=updated_log.model_dump(mode="json")
    )


@router.delete("/logs/{log_id}", response_model=ApiResponse, summary="删除养护日志")
async def delete_maintenance_log(
    request: Request,
    log_id: str
):
    maintenance_service = request.app.state.maintenance_log_service

    deleted = maintenance_service.delete_log(log_id)
    if not deleted:
        return api_response(
            code=404,
            message=f"养护日志ID {log_id} 不存在",
            data=None
        )

    return api_response(
        code=200,
        message="养护日志已删除",
        data={"log_id": log_id}
    )


@router.get("/plant/{plant_id}", response_model=ApiResponse, summary="获取单株植物的养护日志")
async def get_plant_maintenance_logs(
    request: Request,
    plant_id: str,
    limit: int = Query(100, ge=1, le=500, description="返回数量限制")
):
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db

    if plant_id not in plants_db:
        return api_response(
            code=404,
            message=f"植物ID {plant_id} 不存在",
            data=None
        )

    try:
        logs = maintenance_service.get_plant_logs(plant_id, limit=limit)
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取植物养护日志失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取到 {len(logs)} 条养护日志",
        data={
            "plant_id": plant_id,
            "plant_name": plants_db[plant_id].name,
            "total": len(logs),
            "logs": [log.model_dump(mode="json") for log in logs]
        }
    )


@router.get("/zone/{zone_id}", response_model=ApiResponse, summary="获取分区的养护日志")
async def get_zone_maintenance_logs(
    request: Request,
    zone_id: str,
    limit: int = Query(100, ge=1, le=500, description="返回数量限制")
):
    maintenance_service = request.app.state.maintenance_log_service
    zone_service = request.app.state.zone_service

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(
            code=404,
            message=f"分区ID {zone_id} 不存在",
            data=None
        )

    try:
        logs = maintenance_service.get_zone_logs(zone_id, limit=limit)
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取分区养护日志失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取到 {len(logs)} 条养护日志",
        data={
            "zone_id": zone_id,
            "zone_name": zone.name,
            "total": len(logs),
            "logs": [log.model_dump(mode="json") for log in logs]
        }
    )


@router.post("/observation", response_model=ApiResponse, summary="添加后续观察记录")
async def add_follow_up_observation(
    request: Request,
    observation: FollowUpObservation
):
    maintenance_service = request.app.state.maintenance_log_service

    log = maintenance_service.get_log(observation.log_id)
    if not log:
        return api_response(
            code=404,
            message=f"养护日志ID {observation.log_id} 不存在",
            data=None
        )

    try:
        updated_log = maintenance_service.add_follow_up_observation(observation)
    except Exception as e:
        return api_response(
            code=500,
            message=f"添加观察记录失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="观察记录已添加，养护效果已重新评估",
        data=updated_log.model_dump(mode="json")
    )


@router.get("/analysis/{log_id}", response_model=ApiResponse, summary="分析单条养护操作的效果")
async def analyze_maintenance_operation(
    request: Request,
    log_id: str
):
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db
    zone_service = request.app.state.zone_service

    log = maintenance_service.get_log(log_id)
    if not log:
        return api_response(
            code=404,
            message=f"养护日志ID {log_id} 不存在",
            data=None
        )

    plant = None
    zone = None
    zones_db = {z.id: z for z in zone_service.get_all_zones()}

    try:
        if log.target_type == "plant":
            plant = plants_db.get(log.target_id)
            zone = zone_service.get_plant_zone(log.target_id)
        elif log.target_type == "zone":
            zone = zones_db.get(log.target_id)

        analysis = maintenance_service.analyze_operation(
            log=log,
            plant=plant,
            zone=zone,
            plants_db=plants_db
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"养护操作分析失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="养护操作分析完成",
        data=analysis.model_dump(mode="json")
    )


@router.get("/suggestions/{target_type}/{target_id}", response_model=ApiResponse, summary="生成养护调整建议")
async def generate_adjustment_suggestions(
    request: Request,
    target_type: str,
    target_id: str
):
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db
    zone_service = request.app.state.zone_service

    if target_type not in ["plant", "zone"]:
        return api_response(
            code=400,
            message="无效的目标类型，有效值为: plant, zone",
            data=None
        )

    if target_type == "plant":
        if target_id not in plants_db:
            return api_response(
                code=404,
                message=f"植物ID {target_id} 不存在",
                data=None
            )
    elif target_type == "zone":
        zone = zone_service.get_zone(target_id)
        if not zone:
            return api_response(
                code=404,
                message=f"分区ID {target_id} 不存在",
                data=None
            )

    try:
        zones_db = {z.id: z for z in zone_service.get_all_zones()}
        suggestions = maintenance_service.generate_adjustment_suggestions(
            target_type=target_type,
            target_id=target_id,
            plants_db=plants_db,
            zones_db=zones_db
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"生成调整建议失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"生成 {len(suggestions)} 条调整建议",
        data={
            "target_type": target_type,
            "target_id": target_id,
            "total_suggestions": len(suggestions),
            "suggestions": [s.model_dump(mode="json") for s in suggestions]
        }
    )


@router.get("/zone/analysis/{zone_id}", response_model=ApiResponse, summary="分析分区养护操作整体效果")
async def analyze_zone_operations(
    request: Request,
    zone_id: str
):
    maintenance_service = request.app.state.maintenance_log_service
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(
            code=404,
            message=f"分区ID {zone_id} 不存在",
            data=None
        )

    try:
        analysis = maintenance_service.analyze_zone_operations(
            zone=zone,
            plants_db=plants_db
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"分区养护分析失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="分区养护操作分析完成",
        data=analysis.model_dump(mode="json")
    )


@router.get("/statistics", response_model=ApiResponse, summary="获取养护日志统计信息")
async def get_maintenance_statistics(
    request: Request,
    target_type: Optional[str] = Query(None, description="目标类型: plant, zone"),
    target_id: Optional[str] = Query(None, description="目标ID")
):
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db
    zone_service = request.app.state.zone_service

    if target_type and target_id:
        if target_type not in ["plant", "zone"]:
            return api_response(
                code=400,
                message="无效的目标类型，有效值为: plant, zone",
                data=None
            )
        if target_type == "plant" and target_id not in plants_db:
            return api_response(
                code=404,
                message=f"植物ID {target_id} 不存在",
                data=None
            )
        if target_type == "zone":
            zone = zone_service.get_zone(target_id)
            if not zone:
                return api_response(
                    code=404,
                    message=f"分区ID {target_id} 不存在",
                    data=None
                )

    try:
        stats = maintenance_service.get_statistics(
            target_type=target_type,
            target_id=target_id
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取统计信息失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="获取统计信息成功",
        data=stats
    )


@router.get("/operation/types", response_model=ApiResponse, summary="获取支持的养护操作类型")
async def get_operation_types():
    types = [
        {"type": MaintenanceOperationType.WATERING.value, "name": "浇水", "description": "为植物补充水分"},
        {"type": MaintenanceOperationType.FERTILIZING.value, "name": "施肥", "description": "为植物补充营养"},
        {"type": MaintenanceOperationType.REPOTTING.value, "name": "换盆", "description": "更换花盆或盆土"},
        {"type": MaintenanceOperationType.PRUNING.value, "name": "修剪", "description": "修剪枝叶、整形"},
        {"type": MaintenanceOperationType.VENTILATION.value, "name": "通风", "description": "改善通风条件"},
        {"type": MaintenanceOperationType.ISOLATION.value, "name": "隔离", "description": "将植物隔离观察"},
        {"type": MaintenanceOperationType.SPRAYING.value, "name": "喷药", "description": "喷施农药或杀菌剂"},
        {"type": MaintenanceOperationType.REMOVE_DISEASED_LEAVES.value, "name": "清理病叶", "description": "剪除受感染的叶片"},
        {"type": MaintenanceOperationType.ADJUST_POSITION.value, "name": "调整摆放位置", "description": "改变植物摆放位置"},
        {"type": MaintenanceOperationType.SOIL_REPLACEMENT.value, "name": "更换盆土", "description": "全部或部分更换栽培介质"},
        {"type": MaintenanceOperationType.PEST_CONTROL.value, "name": "虫害防治", "description": "针对虫害的处置措施"},
        {"type": MaintenanceOperationType.DISEASE_TREATMENT.value, "name": "病害治疗", "description": "针对病害的治疗措施"},
        {"type": MaintenanceOperationType.LIGHT_ADJUSTMENT.value, "name": "调整光照", "description": "调整光照条件"},
        {"type": MaintenanceOperationType.HUMIDITY_ADJUSTMENT.value, "name": "调整湿度", "description": "调整环境湿度"},
        {"type": MaintenanceOperationType.TEMPERATURE_ADJUSTMENT.value, "name": "调整温度", "description": "调整环境温度"},
        {"type": MaintenanceOperationType.OTHER.value, "name": "其他", "description": "其他养护操作"}
    ]

    return api_response(
        code=200,
        message=f"共支持 {len(types)} 种养护操作类型",
        data={"operation_types": types}
    )


@router.get("/effectiveness/levels", response_model=ApiResponse, summary="获取操作有效性等级说明")
async def get_effectiveness_levels():
    levels = [
        {"level": OperationEffectiveness.VERY_EFFECTIVE.value, "name": "非常有效", "description": "健康评分提升20分以上", "action": "继续保持当前方案"},
        {"level": OperationEffectiveness.EFFECTIVE.value, "name": "有效", "description": "健康评分提升10-19分", "action": "继续观察，按计划执行"},
        {"level": OperationEffectiveness.PARTIALLY_EFFECTIVE.value, "name": "部分有效", "description": "健康评分提升0-9分", "action": "考虑微调养护方案"},
        {"level": OperationEffectiveness.INEFFECTIVE.value, "name": "无效", "description": "健康评分下降0-10分", "action": "建议更换养护方案"},
        {"level": OperationEffectiveness.HARMFUL.value, "name": "有害", "description": "健康评分下降10分以上", "action": "立即停止，采取补救措施"},
        {"level": OperationEffectiveness.PENDING.value, "name": "待评估", "description": "尚未有足够数据评估", "action": "继续观察，等待后续数据"}
    ]

    return api_response(
        code=200,
        message="获取有效性等级成功",
        data={"levels": levels}
    )
