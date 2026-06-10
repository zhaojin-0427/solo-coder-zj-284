from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from typing import Optional, Dict

from models.pest_disease import (
    PestDiseaseCreate, TreatmentUpdate, RecordStatusUpdate,
    SeverityLevel
)
from models import ApiResponse


router = APIRouter(prefix="/api/pest-disease", tags=["病虫害识别与隔离处置"])


def api_response(code: int, message: str, data=None) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": message, "data": data}
    )


@router.post("/report", response_model=ApiResponse, summary="上报植物病虫害症状")
async def report_pest_disease(
    request: Request,
    data: PestDiseaseCreate
):
    zone_service = request.app.state.zone_service
    pest_service = request.app.state.pest_disease_service
    plants_db = request.app.state.plants_db

    plant = plants_db.get(data.plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {data.plant_id} 不存在", data=None)

    try:
        record = pest_service.create_record(data)
        zone = zone_service.get_plant_zone(data.plant_id)
        zones_db = {z.id: z for z in zone_service.get_all_zones()}

        analysis = pest_service.analyze_pest_disease(
            record=record,
            plant=plant,
            zone=zone,
            zones_db=zones_db,
            plants_db=plants_db
        )

        zone_outbreak = None
        if zone:
            zone_outbreak = pest_service.analyze_zone_pest_outbreak(zone, plants_db)

    except Exception as e:
        return api_response(
            code=500,
            message=f"病虫害分析失败: {str(e)}",
            data=None
        )

    result = {
        "record": record.model_dump(mode="json"),
        "analysis": analysis.model_dump(mode="json")
    }

    if zone_outbreak:
        result["zone_outbreak_alert"] = zone_outbreak
        message = f"病虫害记录已创建，检测到{zone.name}可能存在{zone_outbreak['outbreak_type']}风险"
    else:
        message = "病虫害记录已创建，分析完成"

    return api_response(code=200, message=message, data=result)


@router.get("/records", response_model=ApiResponse, summary="获取病虫害记录列表")
async def get_records(
    request: Request,
    status: Optional[str] = Query(None, description="状态筛选: open, in_treatment, resolved, closed"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制")
):
    pest_service = request.app.state.pest_disease_service

    valid_statuses = ["open", "in_treatment", "resolved", "closed"]
    if status is not None and status not in valid_statuses:
        return api_response(
            code=400,
            message=f"无效的状态参数: {status}，有效值为: {', '.join(valid_statuses)}",
            data=None
        )

    try:
        records = pest_service.get_all_records(status=status, limit=limit)
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取记录列表失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取到 {len(records)} 条病虫害记录",
        data={
            "total": len(records),
            "records": [r.model_dump(mode="json") for r in records]
        }
    )


@router.get("/records/{record_id}", response_model=ApiResponse, summary="获取单条病虫害记录详情")
async def get_record(
    request: Request,
    record_id: str
):
    pest_service = request.app.state.pest_disease_service
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    record = pest_service.get_record(record_id)
    if not record:
        return api_response(code=404, message=f"记录ID {record_id} 不存在", data=None)

    try:
        plant = plants_db.get(record.plant_id)
        zone = zone_service.get_plant_zone(record.plant_id)
        zones_db = {z.id: z for z in zone_service.get_all_zones()}

        if plant:
            analysis = pest_service.analyze_pest_disease(
                record=record,
                plant=plant,
                zone=zone,
                zones_db=zones_db,
                plants_db=plants_db
            )
        else:
            analysis = None

    except Exception as e:
        return api_response(
            code=500,
            message=f"获取记录详情失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="获取记录详情成功",
        data={
            "record": record.model_dump(mode="json"),
            "analysis": analysis.model_dump(mode="json") if analysis else None
        }
    )


@router.get("/plant/{plant_id}", response_model=ApiResponse, summary="获取单株植物的病虫害历史")
async def get_plant_records(
    request: Request,
    plant_id: str
):
    pest_service = request.app.state.pest_disease_service
    plants_db = request.app.state.plants_db

    if plant_id not in plants_db:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)

    try:
        records = pest_service.get_plant_records(plant_id)
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取植物病虫害历史失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取到 {len(records)} 条病虫害记录",
        data={
            "plant_id": plant_id,
            "plant_name": plants_db[plant_id].name,
            "total": len(records),
            "records": [r.model_dump(mode="json") for r in records]
        }
    )


@router.get("/zone/{zone_id}", response_model=ApiResponse, summary="获取分区内的病虫害记录")
async def get_zone_records(
    request: Request,
    zone_id: str
):
    pest_service = request.app.state.pest_disease_service
    zone_service = request.app.state.zone_service

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    try:
        zones_db = {z.id: z for z in zone_service.get_all_zones()}
        records = pest_service.get_zone_records(zone_id, zones_db)
        outbreak = pest_service.analyze_zone_pest_outbreak(zone, request.app.state.plants_db)
    except Exception as e:
        return api_response(
            code=500,
            message=f"获取分区病虫害记录失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message=f"获取到 {len(records)} 条病虫害记录",
        data={
            "zone_id": zone_id,
            "zone_name": zone.name,
            "total": len(records),
            "outbreak_alert": outbreak,
            "records": [r.model_dump(mode="json") for r in records]
        }
    )


@router.put("/records/{record_id}/status", response_model=ApiResponse, summary="更新记录状态")
async def update_record_status(
    request: Request,
    record_id: str,
    update: RecordStatusUpdate
):
    pest_service = request.app.state.pest_disease_service

    valid_statuses = ["open", "in_treatment", "resolved", "closed"]
    if update.status not in valid_statuses:
        return api_response(
            code=400,
            message=f"无效状态，有效值为: {', '.join(valid_statuses)}",
            data=None
        )

    record = pest_service.update_record_status(record_id, update.status, update.notes)
    if not record:
        return api_response(code=404, message=f"记录ID {record_id} 不存在", data=None)

    return api_response(
        code=200,
        message=f"记录状态已更新为 {update.status}",
        data=record.model_dump(mode="json")
    )


@router.post("/treatment", response_model=ApiResponse, summary="上报处置措施")
async def add_treatment(
    request: Request,
    update: TreatmentUpdate
):
    pest_service = request.app.state.pest_disease_service

    record = pest_service.add_treatment(update)
    if not record:
        return api_response(code=404, message=f"记录ID {update.record_id} 不存在", data=None)

    return api_response(
        code=200,
        message="处置措施已记录",
        data=record.model_dump(mode="json")
    )


@router.get("/analysis/{record_id}", response_model=ApiResponse, summary="重新分析病虫害记录")
async def reanalyze_record(
    request: Request,
    record_id: str
):
    pest_service = request.app.state.pest_disease_service
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    record = pest_service.get_record(record_id)
    if not record:
        return api_response(code=404, message=f"记录ID {record_id} 不存在", data=None)

    plant = plants_db.get(record.plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {record.plant_id} 不存在", data=None)

    try:
        zone = zone_service.get_plant_zone(record.plant_id)
        zones_db = {z.id: z for z in zone_service.get_all_zones()}

        analysis = pest_service.analyze_pest_disease(
            record=record,
            plant=plant,
            zone=zone,
            zones_db=zones_db,
            plants_db=plants_db
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"病虫害分析失败: {str(e)}",
            data=None
        )

    return api_response(
        code=200,
        message="重新分析完成",
        data=analysis.model_dump(mode="json")
    )


@router.get("/outbreak/zone/{zone_id}", response_model=ApiResponse, summary="检测分区病虫害爆发风险")
async def detect_zone_outbreak(
    request: Request,
    zone_id: str
):
    pest_service = request.app.state.pest_disease_service
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    try:
        outbreak = pest_service.analyze_zone_pest_outbreak(zone, plants_db)
    except Exception as e:
        return api_response(
            code=500,
            message=f"疫情检测失败: {str(e)}",
            data=None
        )

    if outbreak:
        return api_response(
            code=200,
            message=f"检测到{zone.name}存在{outbreak['outbreak_type']}风险",
            data=outbreak
        )
    else:
        return api_response(
            code=200,
            message=f"{zone.name}未检测到病虫害爆发风险",
            data={"outbreak_detected": False, "zone_id": zone_id, "zone_name": zone.name}
        )


@router.get("/statistics", response_model=ApiResponse, summary="获取病虫害统计信息")
async def get_statistics(
    request: Request,
    zone_id: Optional[str] = Query(None, description="分区ID，可选")
):
    pest_service = request.app.state.pest_disease_service
    zone_service = request.app.state.zone_service

    zones_db = None
    if zone_id:
        zone = zone_service.get_zone(zone_id)
        if not zone:
            return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)
        zones_db = {z.id: z for z in zone_service.get_all_zones()}

    try:
        stats = pest_service.get_statistics(zone_id=zone_id, zones_db=zones_db)
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


@router.get("/severity/levels", response_model=ApiResponse, summary="获取严重程度级别说明")
async def get_severity_levels():
    levels = [
        {"level": SeverityLevel.MILD.value, "description": "轻微 - 症状不明显，受影响面积小", "action": "观察，保持良好养护"},
        {"level": SeverityLevel.MODERATE.value, "description": "中等 - 症状明显，受影响面积中等", "action": "及时处理，防止扩散"},
        {"level": SeverityLevel.SEVERE.value, "description": "严重 - 症状显著，受影响面积大", "action": "必须隔离，积极治疗"},
        {"level": SeverityLevel.CRITICAL.value, "description": "危急 - 症状严重，威胁植物生命", "action": "紧急隔离，全力救治"}
    ]

    return api_response(
        code=200,
        message="获取严重程度级别成功",
        data={"levels": levels}
    )


@router.get("/symptom/guide", response_model=ApiResponse, summary="获取症状识别指南")
async def get_symptom_guide():
    guide = {
        "常见症状": [
            {"symptom": "霉斑 (mold)", "description": "叶片出现白色/灰色霉层", "可能原因": ["高湿度", "通风不良", "真菌感染"]},
            {"symptom": "黄叶 (yellow_leaf)", "description": "叶片发黄", "可能原因": ["浇水过多", "营养缺乏", "光照不足"]},
            {"symptom": "黑斑 (black_spot)", "description": "叶片出现黑色斑点", "可能原因": ["真菌病害", "高湿环境", "叶片积水"]},
            {"symptom": "卷叶 (leaf_curl)", "description": "叶片卷曲变形", "可能原因": ["虫害侵袭", "病毒感染", "水分不足"]},
            {"symptom": "叶斑 (leaf_spot)", "description": "叶片出现斑点", "可能原因": ["细菌/真菌感染", "环境胁迫"]},
            {"symptom": "萎蔫 (wilt)", "description": "植株失去挺立", "可能原因": ["水分不足", "根系腐烂", "温度胁迫"]},
            {"symptom": "腐烂 (rot)", "description": "组织软化腐烂", "可能原因": ["根系腐烂", "浇水过多", "细菌感染"]}
        ],
        "常见虫害": [
            {"pest": "蚜虫 (aphid)", "特征": "小型绿色/黑色昆虫，聚集在新梢", "危害": "吸食汁液，传播病毒"},
            {"pest": "介壳虫 (scale)", "特征": "褐色/白色硬壳，附着在茎和叶背", "危害": "吸食汁液，导致落叶"},
            {"pest": "红蜘蛛 (spider_mite)", "特征": "微小红色螨虫，叶背结网", "危害": "叶片失绿，出现斑点"},
            {"pest": "粉虱 (whitefly)", "特征": "白色小飞虫，惊扰时成群飞起", "危害": "吸食汁液，分泌蜜露"}
        ]
    }

    return api_response(
        code=200,
        message="获取症状识别指南成功",
        data=guide
    )
