from fastapi import APIRouter, Request, Query
from typing import Dict

from models.schedule import (
    ScheduleGenerateRequest, ConflictDetectRequest,
    ReminderGenerateRequest, ReminderStatus, SchedulePriority
)
from models import ApiResponse


router = APIRouter(prefix="/api/schedules", tags=["智能排程与冲突分析"])


def api_response(code: int, message: str, data=None) -> Dict:
    return {"code": code, "message": message, "data": data}


@router.post("/generate", response_model=ApiResponse, summary="生成分区浇水排程")
async def generate_watering_schedule(
    request: Request,
    req: ScheduleGenerateRequest
):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(req.zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {req.zone_id} 不存在", data=None)

    if len(zone.plant_ids) == 0:
        return api_response(
            code=400,
            message="分区内没有绑定植物，请先绑定植物",
            data={"zone_id": req.zone_id}
        )

    try:
        schedule = schedule_service.generate_schedule(zone, plants_db, req.days_ahead)
        if not schedule:
            return api_response(
                code=500,
                message="排程生成失败，请确保分区内植物有浇水记录",
                data=None
            )
    except Exception as e:
        return api_response(
            code=500,
            message=f"排程生成失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"成功生成未来 {req.days_ahead} 天浇水排程",
        data=schedule.model_dump(mode="json")
    )


@router.get("/zone/{zone_id}", response_model=ApiResponse, summary="获取分区浇水排程")
async def get_zone_schedule(
    request: Request,
    zone_id: str,
    days_ahead: int = Query(7, ge=1, le=90, description="排程天数，支持7/14/30天")
):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    if len(zone.plant_ids) == 0:
        return api_response(
            code=400,
            message="分区内没有绑定植物",
            data={"zone_id": zone_id}
        )

    try:
        schedule = schedule_service.generate_schedule(zone, plants_db, days_ahead)
        if not schedule:
            return api_response(
                code=500,
                message="排程生成失败，请确保分区内植物有浇水记录",
                data=None
            )
    except Exception as e:
        return api_response(
            code=500,
            message=f"排程生成失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取未来 {days_ahead} 天排程成功",
        data=schedule.model_dump(mode="json")
    )


@router.get("/upcoming/{zone_id}", response_model=ApiResponse, summary="获取即将到来的浇水任务")
async def get_upcoming_tasks(
    request: Request,
    zone_id: str,
    hours_ahead: int = Query(48, ge=1, le=168, description="未来多少小时内的任务")
):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    tasks = schedule_service.get_upcoming_tasks(zone, plants_db, hours_ahead)

    return api_response(
        code=200,
        message=f"获取到 {len(tasks)} 个即将到来的浇水任务",
        data={
            "zone_id": zone_id,
            "zone_name": zone.name,
            "hours_ahead": hours_ahead,
            "total_tasks": len(tasks),
            "tasks": [t.model_dump(mode="json") for t in tasks]
        }
    )


@router.post("/conflicts/analyze", response_model=ApiResponse, summary="分析分区冲突")
async def analyze_zone_conflicts(
    request: Request,
    req: ConflictDetectRequest
):
    zone_service = request.app.state.zone_service
    conflict_service = request.app.state.conflict_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(req.zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {req.zone_id} 不存在", data=None)

    if len(zone.plant_ids) == 0:
        return api_response(
            code=400,
            message="分区内没有绑定植物",
            data={"zone_id": req.zone_id}
        )

    try:
        analysis = conflict_service.analyze_conflicts(zone, plants_db)
        if not analysis:
            return api_response(
                code=500,
                message="冲突分析失败",
                data=None
            )
    except Exception as e:
        return api_response(
            code=500,
            message=f"冲突分析失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"冲突分析完成，发现 {analysis.total_conflicts} 个冲突",
        data=analysis.model_dump(mode="json")
    )


@router.get("/conflicts/zone/{zone_id}", response_model=ApiResponse, summary="获取分区冲突分析")
async def get_zone_conflicts(
    request: Request,
    zone_id: str
):
    zone_service = request.app.state.zone_service
    conflict_service = request.app.state.conflict_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    if len(zone.plant_ids) == 0:
        return api_response(
            code=400,
            message="分区内没有绑定植物",
            data={"zone_id": zone_id}
        )

    try:
        analysis = conflict_service.analyze_conflicts(zone, plants_db)
        if not analysis:
            return api_response(
                code=500,
                message="冲突分析失败",
                data=None
            )
    except Exception as e:
        return api_response(
            code=500,
            message=f"冲突分析失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"冲突分析完成，发现 {analysis.total_conflicts} 个冲突",
        data=analysis.model_dump(mode="json")
    )


@router.get("/overview", response_model=ApiResponse, summary="获取全部分区排程概览")
async def get_all_schedules_overview(
    request: Request,
    days_ahead: int = Query(7, ge=1, le=30)
):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    plants_db = request.app.state.plants_db

    zones = zone_service.get_all_zones()
    overview = []

    for zone in zones:
        if len(zone.plant_ids) == 0:
            overview.append({
                "zone_id": zone.id,
                "zone_name": zone.name,
                "zone_type": zone.zone_type.value,
                "total_plants": 0,
                "total_tasks": 0,
                "critical_count": 0,
                "high_count": 0,
                "has_data": False
            })
            continue

        try:
            schedule = schedule_service.generate_schedule(zone, plants_db, days_ahead)
            if schedule:
                overview.append({
                    "zone_id": zone.id,
                    "zone_name": zone.name,
                    "zone_type": zone.zone_type.value,
                    "total_plants": len(zone.plant_ids),
                    "total_tasks": schedule.total_tasks,
                    "critical_count": schedule.priority_summary.get("critical", 0),
                    "high_count": schedule.priority_summary.get("high", 0),
                    "batch_groups_count": schedule.batch_groups_count,
                    "has_data": True
                })
            else:
                overview.append({
                    "zone_id": zone.id,
                    "zone_name": zone.name,
                    "zone_type": zone.zone_type.value,
                    "total_plants": len(zone.plant_ids),
                    "total_tasks": 0,
                    "critical_count": 0,
                    "high_count": 0,
                    "has_data": False,
                    "note": "植物浇水记录不足"
                })
        except Exception:
            overview.append({
                "zone_id": zone.id,
                "zone_name": zone.name,
                "zone_type": zone.zone_type.value,
                "total_plants": len(zone.plant_ids),
                "total_tasks": 0,
                "critical_count": 0,
                "high_count": 0,
                "has_data": False
            })

    total_plants = sum(o["total_plants"] for o in overview)
    total_tasks = sum(o["total_tasks"] for o in overview)
    total_critical = sum(o["critical_count"] for o in overview)
    total_high = sum(o["high_count"] for o in overview)

    return api_response(
        code=200,
        message="获取排程概览成功",
        data={
            "total_zones": len(overview),
            "total_plants": total_plants,
            "total_tasks": total_tasks,
            "total_critical": total_critical,
            "total_high": total_high,
            "days_ahead": days_ahead,
            "zones": overview
        }
    )


@router.post("/cache/clear", response_model=ApiResponse, summary="清除排程缓存")
async def clear_schedule_cache(
    request: Request,
    zone_id: str = None
):
    schedule_service = request.app.state.schedule_service
    schedule_service.invalidate_cache(zone_id)

    if zone_id:
        return api_response(
            code=200,
            message=f"分区 {zone_id} 的排程缓存已清除",
            data={"zone_id": zone_id}
        )
    else:
        return api_response(
            code=200,
            message="所有排程缓存已清除",
            data={}
        )


@router.post("/reminders/generate", response_model=ApiResponse, summary="生成智能浇水提醒")
async def generate_reminders(
    request: Request,
    req: ReminderGenerateRequest
):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    conflict_service = request.app.state.conflict_service
    reminder_service = request.app.state.reminder_service
    plants_db = request.app.state.plants_db

    all_reminders = []

    try:
        if req.zone_id:
            zone = zone_service.get_zone(req.zone_id)
            if not zone:
                return api_response(code=404, message=f"分区ID {req.zone_id} 不存在", data=None)

            if len(zone.plant_ids) == 0:
                return api_response(
                    code=400,
                    message="分区内没有绑定植物",
                    data={"zone_id": req.zone_id}
                )

            reminders = reminder_service.generate_reminders(
                zone=zone,
                plants_db=plants_db,
                schedule_service=schedule_service,
                conflict_service=conflict_service,
                hours_ahead=req.hours_ahead,
                config=req.config
            )
            all_reminders.extend(reminders)
        else:
            zones = zone_service.get_all_zones()
            for zone in zones:
                if len(zone.plant_ids) == 0:
                    continue
                reminders = reminder_service.generate_reminders(
                    zone=zone,
                    plants_db=plants_db,
                    schedule_service=schedule_service,
                    conflict_service=conflict_service,
                    hours_ahead=req.hours_ahead,
                    config=req.config
                )
                all_reminders.extend(reminders)

    except Exception as e:
        return api_response(
            code=500,
            message=f"生成提醒失败: {str(e)}",
            data=None
        )

    critical_count = sum(1 for r in all_reminders if r.priority == SchedulePriority.CRITICAL)
    high_count = sum(1 for r in all_reminders if r.priority == SchedulePriority.HIGH)
    task_reminders = sum(1 for r in all_reminders if r.reminder_type == "task_reminder")
    batch_reminders = sum(1 for r in all_reminders if r.reminder_type == "batch_summary")
    conflict_reminders = sum(1 for r in all_reminders if r.reminder_type == "conflict_alert")

    return api_response(
        code=200,
        message=f"成功生成 {len(all_reminders)} 条浇水提醒",
        data={
            "total_reminders": len(all_reminders),
            "critical_count": critical_count,
            "high_count": high_count,
            "task_reminders": task_reminders,
            "batch_summary_reminders": batch_reminders,
            "conflict_alert_reminders": conflict_reminders,
            "hours_ahead": req.hours_ahead,
            "reminders": [r.model_dump(mode="json") for r in all_reminders]
        }
    )


@router.get("/reminders", response_model=ApiResponse, summary="获取提醒列表")
async def get_reminders(
    request: Request,
    zone_id: str = None,
    status: ReminderStatus = None,
    priority: SchedulePriority = None,
    limit: int = Query(100, ge=1, le=500, description="返回数量限制")
):
    reminder_service = request.app.state.reminder_service

    try:
        result = reminder_service.get_reminders(
            zone_id=zone_id,
            status=status,
            priority=priority,
            limit=limit
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取提醒列表失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取到 {result.total_reminders} 条提醒",
        data=result.model_dump(mode="json")
    )


@router.get("/reminders/{reminder_id}", response_model=ApiResponse, summary="获取单个提醒详情")
async def get_reminder(
    request: Request,
    reminder_id: str
):
    reminder_service = request.app.state.reminder_service
    result = reminder_service.get_reminders(limit=1000)

    reminder = None
    for r in result.reminders:
        if r.reminder_id == reminder_id:
            reminder = r
            break

    if not reminder:
        return api_response(code=404, message=f"提醒ID {reminder_id} 不存在", data=None)

    return api_response(
        code=200,
        message="获取提醒详情成功",
        data=reminder.model_dump(mode="json")
    )


@router.put("/reminders/{reminder_id}/status", response_model=ApiResponse, summary="更新提醒状态")
async def update_reminder_status(
    request: Request,
    reminder_id: str,
    status: ReminderStatus
):
    reminder_service = request.app.state.reminder_service

    reminder = reminder_service.update_reminder_status(reminder_id, status)
    if not reminder:
        return api_response(code=404, message=f"提醒ID {reminder_id} 不存在", data=None)

    return api_response(
        code=200,
        message=f"提醒状态已更新为 {status.value}",
        data=reminder.model_dump(mode="json")
    )


@router.post("/reminders/{reminder_id}/dismiss", response_model=ApiResponse, summary="忽略提醒")
async def dismiss_reminder(
    request: Request,
    reminder_id: str
):
    reminder_service = request.app.state.reminder_service

    success = reminder_service.dismiss_reminder(reminder_id)
    if not success:
        return api_response(code=404, message=f"提醒ID {reminder_id} 不存在", data=None)

    return api_response(
        code=200,
        message="提醒已忽略",
        data={"reminder_id": reminder_id}
    )


@router.delete("/reminders", response_model=ApiResponse, summary="清除提醒")
async def clear_reminders(
    request: Request,
    zone_id: str = None
):
    reminder_service = request.app.state.reminder_service

    count = reminder_service.clear_reminders(zone_id)

    if zone_id:
        return api_response(
            code=200,
            message=f"已清除分区 {zone_id} 的 {count} 条提醒",
            data={"zone_id": zone_id, "cleared_count": count}
        )
    else:
        return api_response(
            code=200,
            message=f"已清除所有 {count} 条提醒",
            data={"cleared_count": count}
        )


@router.get("/reminders/statistics", response_model=ApiResponse, summary="获取提醒统计信息")
async def get_reminder_statistics(
    request: Request,
    zone_id: str = None
):
    reminder_service = request.app.state.reminder_service

    try:
        stats = reminder_service.get_reminder_statistics(zone_id)
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取统计信息失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="获取提醒统计信息成功",
        data=stats
    )


@router.post("/reminders/{reminder_id}/send", response_model=ApiResponse, summary="标记提醒为已发送")
async def mark_reminder_sent(
    request: Request,
    reminder_id: str
):
    reminder_service = request.app.state.reminder_service

    reminder = reminder_service.update_reminder_status(reminder_id, ReminderStatus.SENT)
    if not reminder:
        return api_response(code=404, message=f"提醒ID {reminder_id} 不存在", data=None)

    return api_response(
        code=200,
        message="提醒已标记为已发送",
        data=reminder.model_dump(mode="json")
    )
