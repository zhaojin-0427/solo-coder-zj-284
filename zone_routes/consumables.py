from fastapi import APIRouter, Request, Query
from typing import Optional, Dict

from models import (
    ConsumableCreate, ConsumableUpdate, ConsumableCategory,
    StockAdjustment, ApiResponse
)


router = APIRouter(prefix="/api/consumables", tags=["耗材库存与采购补货管理"])


def api_response(code: int, message: str, data=None) -> Dict:
    return {"code": code, "message": message, "data": data}


@router.post("", response_model=ApiResponse, summary="创建耗材库存档案")
async def create_consumable(request: Request, data: ConsumableCreate):
    service = request.app.state.consumable_service
    consumable = service.create_consumable(data)

    return api_response(
        code=200,
        message="耗材档案创建成功",
        data=consumable.model_dump(mode="json")
    )


@router.get("", response_model=ApiResponse, summary="获取耗材库存列表")
async def get_consumables(
    request: Request,
    category: Optional[ConsumableCategory] = Query(None, description="按分类筛选"),
    low_stock_only: bool = Query(False, description="仅显示低库存"),
    critical_only: bool = Query(False, description="仅显示关键耗材")
):
    service = request.app.state.consumable_service
    consumables = service.get_all_consumables(
        category=category,
        low_stock_only=low_stock_only,
        critical_only=critical_only
    )

    return api_response(
        code=200,
        message=f"获取到 {len(consumables)} 条耗材档案",
        data={
            "total": len(consumables),
            "consumables": [c.model_dump(mode="json") for c in consumables]
        }
    )


@router.get("/{consumable_id}", response_model=ApiResponse, summary="获取单个耗材详情")
async def get_consumable(request: Request, consumable_id: str):
    service = request.app.state.consumable_service
    consumable = service.get_consumable(consumable_id)
    if not consumable:
        return api_response(code=404, message=f"耗材ID {consumable_id} 不存在", data=None)

    return api_response(
        code=200,
        message="获取耗材信息成功",
        data=consumable.model_dump(mode="json")
    )


@router.put("/{consumable_id}", response_model=ApiResponse, summary="更新耗材档案")
async def update_consumable(
    request: Request,
    consumable_id: str,
    data: ConsumableUpdate
):
    service = request.app.state.consumable_service
    consumable = service.update_consumable(consumable_id, data)
    if not consumable:
        return api_response(code=404, message=f"耗材ID {consumable_id} 不存在", data=None)

    return api_response(
        code=200,
        message="耗材档案更新成功",
        data=consumable.model_dump(mode="json")
    )


@router.delete("/{consumable_id}", response_model=ApiResponse, summary="删除耗材档案")
async def delete_consumable(request: Request, consumable_id: str):
    service = request.app.state.consumable_service
    success = service.delete_consumable(consumable_id)
    if not success:
        return api_response(code=404, message=f"耗材ID {consumable_id} 不存在", data=None)

    return api_response(
        code=200,
        message="耗材档案删除成功",
        data={"consumable_id": consumable_id}
    )


@router.post("/stock/adjust", response_model=ApiResponse, summary="调整耗材库存（入库/消耗/报废）")
async def adjust_stock(request: Request, adjustment: StockAdjustment):
    service = request.app.state.consumable_service
    consumable = service.get_consumable(adjustment.consumable_id)
    if not consumable:
        return api_response(code=404, message=f"耗材ID {adjustment.consumable_id} 不存在", data=None)

    transaction = service.adjust_stock(adjustment)
    if not transaction:
        return api_response(
            code=400,
            message="库存调整失败：库存不足或参数错误",
            data={"current_stock": consumable.current_stock}
        )

    return api_response(
        code=200,
        message="库存调整成功",
        data={
            "transaction": transaction.model_dump(mode="json"),
            "current_stock": consumable.current_stock,
            "unit": consumable.unit
        }
    )


@router.get("/{consumable_id}/transactions", response_model=ApiResponse, summary="获取耗材库存变动记录")
async def get_transactions(
    request: Request,
    consumable_id: str,
    limit: int = Query(100, description="返回条数限制", ge=1, le=500)
):
    service = request.app.state.consumable_service
    consumable = service.get_consumable(consumable_id)
    if not consumable:
        return api_response(code=404, message=f"耗材ID {consumable_id} 不存在", data=None)

    transactions = service.get_transactions(consumable_id=consumable_id, limit=limit)

    return api_response(
        code=200,
        message=f"获取到 {len(transactions)} 条库存变动记录",
        data={
            "consumable_id": consumable_id,
            "consumable_name": consumable.name,
            "total": len(transactions),
            "transactions": [t.model_dump(mode="json") for t in transactions]
        }
    )


@router.get("/assessment/all", response_model=ApiResponse, summary="全面评估：消耗预测+风险评估+采购建议")
async def comprehensive_assessment(
    request: Request,
    horizon_days: int = Query(7, description="预测天数：7/14/30", ge=1, le=90)
):
    service = request.app.state.consumable_service
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    pest_service = request.app.state.pest_disease_service
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db

    zones_db = {z.id: z for z in zone_service.get_all_zones()}

    result = service.comprehensive_assessment(
        zones_db=zones_db,
        plants_db=plants_db,
        schedule_service=schedule_service,
        pest_service=pest_service,
        maintenance_service=maintenance_service,
        horizon_days=horizon_days
    )

    return api_response(
        code=200,
        message=f"未来 {horizon_days} 天耗材综合评估完成",
        data=result.model_dump(mode="json")
    )


@router.get("/assessment/consumption", response_model=ApiResponse, summary="耗材消耗预测评估")
async def assess_consumption(
    request: Request,
    horizon_days: int = Query(7, description="预测天数：7/14/30", ge=1, le=90)
):
    service = request.app.state.consumable_service
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    pest_service = request.app.state.pest_disease_service
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db

    zones_db = {z.id: z for z in zone_service.get_all_zones()}
    consumables = service.get_all_consumables()

    estimates = []
    for c in consumables:
        estimates.append(service.estimate_consumption(
            c, zones_db, plants_db, schedule_service, pest_service,
            maintenance_service, horizon_days
        ))

    return api_response(
        code=200,
        message=f"未来 {horizon_days} 天消耗预测完成",
        data={
            "horizon_days": horizon_days,
            "total_consumables": len(estimates),
            "consumption_estimates": [e.model_dump(mode="json") for e in estimates]
        }
    )


@router.get("/assessment/risks", response_model=ApiResponse, summary="库存风险与过期风险评估")
async def assess_risks(
    request: Request,
    horizon_days: int = Query(7, description="预测天数", ge=1, le=90)
):
    service = request.app.state.consumable_service
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    pest_service = request.app.state.pest_disease_service
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db

    zones_db = {z.id: z for z in zone_service.get_all_zones()}
    consumables = service.get_all_consumables()

    risk_assessments = []
    substitute_feasibility = []

    for c in consumables:
        con = service.estimate_consumption(
            c, zones_db, plants_db, schedule_service, pest_service,
            maintenance_service, horizon_days
        )
        risk_assessments.append(service.assess_stock_risk(c, con, zones_db, plants_db))
        substitute_feasibility.append(service.assess_substitute_feasibility(c))

    expiry_alerts = service.generate_expiry_alerts()

    return api_response(
        code=200,
        message="风险评估完成",
        data={
            "total_assessed": len(risk_assessments),
            "stock_risk_assessments": [r.model_dump(mode="json") for r in risk_assessments],
            "substitute_feasibility": [s.model_dump(mode="json") for s in substitute_feasibility],
            "expiry_alerts": [a.model_dump(mode="json") for a in expiry_alerts]
        }
    )


@router.get("/procurement/suggestions", response_model=ApiResponse, summary="获取补货建议与采购清单")
async def get_procurement_suggestions(
    request: Request,
    horizon_days: int = Query(14, description="预测天数", ge=1, le=90)
):
    service = request.app.state.consumable_service
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    pest_service = request.app.state.pest_disease_service
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db

    zones_db = {z.id: z for z in zone_service.get_all_zones()}
    consumables = service.get_all_consumables()

    procurement_items = []
    restock_suggestions = []
    risk_list = []

    for c in consumables:
        con = service.estimate_consumption(
            c, zones_db, plants_db, schedule_service, pest_service,
            maintenance_service, horizon_days
        )
        risk = service.assess_stock_risk(c, con, zones_db, plants_db)
        sub = service.assess_substitute_feasibility(c)
        risk_list.append(risk)

        item = service.generate_procurement_item(c, risk, con, sub)
        if item:
            procurement_items.append(item)
            restock_suggestions.append(service.generate_restock_suggestion(item, risk))

    procurement_items.sort(key=lambda i: i.priority_score, reverse=True)
    cost_overview = service.generate_cost_overview(procurement_items, service.generate_expiry_alerts())

    total_urgent = sum(1 for i in procurement_items if i.priority.value == "urgent")
    total_high = sum(1 for i in procurement_items if i.priority.value == "high")

    return api_response(
        code=200,
        message=f"生成 {len(procurement_items)} 条采购建议",
        data={
            "horizon_days": horizon_days,
            "summary": {
                "total_items": len(procurement_items),
                "urgent_count": total_urgent,
                "high_count": total_high,
                "medium_count": sum(1 for i in procurement_items if i.priority.value == "medium"),
                "low_count": sum(1 for i in procurement_items if i.priority.value == "low"),
                "total_estimated_cost": cost_overview.total_estimated_purchase_cost
            },
            "procurement_list": [i.model_dump(mode="json") for i in procurement_items],
            "restock_suggestions": [s.model_dump(mode="json") for s in restock_suggestions],
            "cost_overview": cost_overview.model_dump(mode="json")
        }
    )


@router.get("/alerts/expiry", response_model=ApiResponse, summary="获取临期与过期提醒")
async def get_expiry_alerts(request: Request):
    service = request.app.state.consumable_service
    alerts = service.generate_expiry_alerts()

    critical_count = sum(1 for a in alerts if a.severity == "critical")
    high_count = sum(1 for a in alerts if a.severity == "high")
    medium_count = sum(1 for a in alerts if a.severity == "medium")
    total_waste = sum(a.estimated_waste_cost or 0 for a in alerts)

    return api_response(
        code=200,
        message=f"获取到 {len(alerts)} 条临期提醒",
        data={
            "total": len(alerts),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "total_estimated_waste": round(total_waste, 2),
            "alerts": [a.model_dump(mode="json") for a in alerts]
        }
    )


@router.get("/cost/overview", response_model=ApiResponse, summary="获取成本概览")
async def get_cost_overview(
    request: Request,
    horizon_days: int = Query(30, description="预测采购天数", ge=1, le=90)
):
    service = request.app.state.consumable_service
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    pest_service = request.app.state.pest_disease_service
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db

    zones_db = {z.id: z for z in zone_service.get_all_zones()}
    consumables = service.get_all_consumables()

    procurement_items = []
    for c in consumables:
        con = service.estimate_consumption(
            c, zones_db, plants_db, schedule_service, pest_service,
            maintenance_service, horizon_days
        )
        risk = service.assess_stock_risk(c, con, zones_db, plants_db)
        sub = service.assess_substitute_feasibility(c)
        item = service.generate_procurement_item(c, risk, con, sub)
        if item:
            procurement_items.append(item)

    expiry_alerts = service.generate_expiry_alerts()
    cost_overview = service.generate_cost_overview(procurement_items, expiry_alerts)

    return api_response(
        code=200,
        message="成本概览生成成功",
        data=cost_overview.model_dump(mode="json")
    )


@router.get("/suggestions/adjustments", response_model=ApiResponse, summary="获取可解释的调整建议")
async def get_adjustment_suggestions(
    request: Request,
    horizon_days: int = Query(14, description="预测天数", ge=1, le=90)
):
    service = request.app.state.consumable_service
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service
    pest_service = request.app.state.pest_disease_service
    maintenance_service = request.app.state.maintenance_log_service
    plants_db = request.app.state.plants_db

    zones_db = {z.id: z for z in zone_service.get_all_zones()}
    consumables = service.get_all_consumables()

    consumptions = []
    risk_assessments = []
    procurement_items = []
    substitute_map = {}

    for c in consumables:
        con = service.estimate_consumption(
            c, zones_db, plants_db, schedule_service, pest_service,
            maintenance_service, horizon_days
        )
        consumptions.append(con)

        risk = service.assess_stock_risk(c, con, zones_db, plants_db)
        risk_assessments.append(risk)

        sub = service.assess_substitute_feasibility(c)
        substitute_map[c.id] = sub

        item = service.generate_procurement_item(c, risk, con, sub)
        if item:
            procurement_items.append(item)

    expiry_alerts = service.generate_expiry_alerts()

    adjustments = service.generate_adjustment_suggestions(
        zones_db, plants_db, schedule_service, pest_service,
        risk_assessments, procurement_items, consumptions,
        substitute_map, expiry_alerts
    )

    type_counter: Dict[str, int] = {}
    priority_counter: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in adjustments:
        t = a.suggestion_type.value
        type_counter[t] = type_counter.get(t, 0) + 1
        priority_counter[a.priority] = priority_counter.get(a.priority, 0) + 1

    return api_response(
        code=200,
        message=f"生成 {len(adjustments)} 条调整建议",
        data={
            "total": len(adjustments),
            "summary": {
                "by_type": type_counter,
                "by_priority": priority_counter
            },
            "suggestions": [a.model_dump(mode="json") for a in adjustments]
        }
    )
