from fastapi import APIRouter, Request
from typing import Dict

from models.zone import (
    ZoneCreate, ZoneUpdate, ZoneBindPlant, ZoneUnbindPlant,
    ZoneType
)
from models import ApiResponse


router = APIRouter(prefix="/api/zones", tags=["分区管理"])


def api_response(code: int, message: str, data=None) -> Dict:
    return {"code": code, "message": message, "data": data}


@router.post("", response_model=ApiResponse, summary="创建养护分区")
async def create_zone(request: Request, zone_create: ZoneCreate):
    zone_service = request.app.state.zone_service
    zone = zone_service.create_zone(zone_create)

    return api_response(
        code=200,
        message="分区创建成功",
        data=zone.model_dump(mode="json")
    )


@router.get("", response_model=ApiResponse, summary="获取所有分区列表")
async def get_all_zones(request: Request):
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db
    zones = zone_service.get_zone_summaries(plants_db)

    return api_response(
        code=200,
        message="获取分区列表成功",
        data={
            "total": len(zones),
            "zones": [z.model_dump(mode="json") for z in zones]
        }
    )


@router.get("/{zone_id}", response_model=ApiResponse, summary="获取单个分区详情")
async def get_zone(request: Request, zone_id: str):
    zone_service = request.app.state.zone_service
    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    return api_response(
        code=200,
        message="获取分区信息成功",
        data=zone.model_dump(mode="json")
    )


@router.put("/{zone_id}", response_model=ApiResponse, summary="更新分区信息")
async def update_zone(request: Request, zone_id: str, zone_update: ZoneUpdate):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service

    zone = zone_service.update_zone(zone_id, zone_update)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    schedule_service.invalidate_cache(zone_id)

    return api_response(
        code=200,
        message="分区信息更新成功",
        data=zone.model_dump(mode="json")
    )


@router.delete("/{zone_id}", response_model=ApiResponse, summary="删除分区")
async def delete_zone(request: Request, zone_id: str):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service

    success = zone_service.delete_zone(zone_id)
    if not success:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    schedule_service.invalidate_cache(zone_id)

    return api_response(
        code=200,
        message="分区删除成功",
        data={"zone_id": zone_id}
    )


@router.post("/{zone_id}/plants", response_model=ApiResponse, summary="绑定植物到分区")
async def bind_plants_to_zone(request: Request, zone_id: str, bind_data: ZoneBindPlant):
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db
    schedule_service = request.app.state.schedule_service

    zone, success_ids, failed_ids = zone_service.bind_plants(zone_id, bind_data.plant_ids, plants_db)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    schedule_service.invalidate_cache(zone_id)

    return api_response(
        code=200,
        message=f"成功绑定 {len(success_ids)} 株植物，失败 {len(failed_ids)} 株",
        data={
            "zone_id": zone_id,
            "success_plant_ids": success_ids,
            "failed_plant_ids": failed_ids,
            "total_plants_in_zone": len(zone.plant_ids)
        }
    )


@router.delete("/{zone_id}/plants", response_model=ApiResponse, summary="从分区解绑植物")
async def unbind_plants_from_zone(request: Request, zone_id: str, unbind_data: ZoneUnbindPlant):
    zone_service = request.app.state.zone_service
    schedule_service = request.app.state.schedule_service

    zone, success_ids, failed_ids = zone_service.unbind_plants(zone_id, unbind_data.plant_ids)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    schedule_service.invalidate_cache(zone_id)

    return api_response(
        code=200,
        message=f"成功解绑 {len(success_ids)} 株植物，失败 {len(failed_ids)} 株",
        data={
            "zone_id": zone_id,
            "success_plant_ids": success_ids,
            "failed_plant_ids": failed_ids,
            "total_plants_in_zone": len(zone.plant_ids)
        }
    )


@router.get("/{zone_id}/plants", response_model=ApiResponse, summary="获取分区内的所有植物")
async def get_zone_plants(request: Request, zone_id: str):
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    zone, plants = zone_service.get_zone_plants(zone_id, plants_db)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    return api_response(
        code=200,
        message=f"获取到 {len(plants)} 株植物",
        data={
            "zone_id": zone_id,
            "zone_name": zone.name,
            "total_plants": len(plants),
            "plants": [p.model_dump(mode="json") for p in plants]
        }
    )


@router.get("/plant/{plant_id}", response_model=ApiResponse, summary="查询植物所属分区")
async def get_plant_zone(request: Request, plant_id: str):
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    if plant_id not in plants_db:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)

    zone = zone_service.get_plant_zone(plant_id)

    return api_response(
        code=200,
        message="查询成功",
        data={
            "plant_id": plant_id,
            "zone": zone.model_dump(mode="json") if zone else None
        }
    )


@router.get("/{zone_id}/patterns", response_model=ApiResponse, summary="分析分区浇水模式")
async def analyze_zone_watering_patterns(request: Request, zone_id: str):
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    zone = zone_service.get_zone(zone_id)
    if not zone:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    patterns = zone_service.analyze_zone_watering_patterns(zone_id, plants_db)

    return api_response(
        code=200,
        message="浇水模式分析完成",
        data=patterns
    )


@router.get("/{zone_id}/risks", response_model=ApiResponse, summary="评估分区风险")
async def assess_zone_risks(request: Request, zone_id: str):
    zone_service = request.app.state.zone_service
    plants_db = request.app.state.plants_db

    assessment = zone_service.assess_zone_risks(zone_id, plants_db)
    if not assessment:
        return api_response(code=404, message=f"分区ID {zone_id} 不存在", data=None)

    return api_response(
        code=200,
        message="风险评估完成",
        data=assessment.model_dump(mode="json")
    )


@router.get("/suggested-plants/{zone_type}", response_model=ApiResponse, summary="获取分区建议种植的植物")
async def get_suggested_plants(request: Request, zone_type: ZoneType):
    zone_service = request.app.state.zone_service
    suggested = zone_service.get_suggested_plants(zone_type)

    return api_response(
        code=200,
        message=f"获取到 {len(suggested)} 种建议植物",
        data={
            "zone_type": zone_type.value,
            "suggested_plants": suggested
        }
    )
