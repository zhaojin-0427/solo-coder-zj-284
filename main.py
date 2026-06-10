from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from datetime import datetime, timedelta
import uuid
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from models import (
    Plant, PlantCreate, PlantUpdate,
    WateringReport, WateringPrediction,
    AnomalyAlert, MaintenanceSuggestion,
    PlantStatistics, ApiResponse
)
from watering_engine import WateringEngine
from plant_database import PLANT_DATABASE, get_plant_info
from services import (
    ZoneService, ScheduleService, ConflictService, PestDiseaseService,
    MaintenanceLogService
)
from services.reminder_service import ReminderService
from zone_routes.zones import router as zones_router
from zone_routes.schedules import router as schedules_router
from zone_routes.pest_disease import router as pest_disease_router
from zone_routes.maintenance_log import router as maintenance_log_router


plants_db: Dict[str, Plant] = {}
watering_engine = WateringEngine()


def api_response(code: int, message: str, data=None) -> JSONResponse:
    return JSONResponse(
        content={
            "code": code,
            "message": message,
            "data": data
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    zone_service = ZoneService(watering_engine)
    conflict_service = ConflictService(watering_engine)
    schedule_service = ScheduleService(watering_engine, conflict_service)
    reminder_service = ReminderService(watering_engine)
    pest_disease_service = PestDiseaseService(watering_engine)
    maintenance_log_service = MaintenanceLogService(watering_engine, pest_disease_service)

    app.state.zone_service = zone_service
    app.state.schedule_service = schedule_service
    app.state.conflict_service = conflict_service
    app.state.reminder_service = reminder_service
    app.state.pest_disease_service = pest_disease_service
    app.state.maintenance_log_service = maintenance_log_service
    app.state.plants_db = plants_db
    app.state.watering_engine = watering_engine

    yield


app = FastAPI(
    title="植物分区养护计划与智能提醒编排 API",
    description="基于植物特性、环境数据和蒸发模型的智能浇水预测、分区养护、排程编排与智能提醒服务",
    version="2.0.0",
    lifespan=lifespan
)

app.include_router(zones_router)
app.include_router(schedules_router)
app.include_router(pest_disease_router)
app.include_router(maintenance_log_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    errors = exc.errors()
    error_messages = []
    for error in errors:
        loc = " -> ".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_messages.append(f"[{loc}] {msg}")
    
    message = "参数校验失败: " + "; ".join(error_messages)
    return JSONResponse(
        status_code=400,
        content={
            "code": 400,
            "message": message,
            "data": {"errors": errors}
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.detail,
            "data": None
        }
    )


@app.post("/api/plants", response_model=ApiResponse, summary="创建植物档案")
async def create_plant(plant_create: PlantCreate):
    plant_id = str(uuid.uuid4())
    now = datetime.now()
    
    plant = Plant(
        id=plant_id,
        **plant_create.model_dump(),
        created_at=now,
        updated_at=now
    )
    
    plants_db[plant_id] = plant
    
    return api_response(
        code=200,
        message="植物档案创建成功",
        data=plant.model_dump(mode="json")
    )


@app.get("/api/plants", response_model=ApiResponse, summary="获取所有植物档案列表")
async def get_all_plants():
    plants_list = [plant.model_dump(mode="json") for plant in plants_db.values()]
    
    return api_response(
        code=200,
        message="获取植物列表成功",
        data={
            "total": len(plants_list),
            "plants": plants_list
        }
    )


@app.get("/api/plants/{plant_id}", response_model=ApiResponse, summary="获取单个植物档案")
async def get_plant(plant_id: str):
    plant = plants_db.get(plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)
    
    return api_response(
        code=200,
        message="获取植物信息成功",
        data=plant.model_dump(mode="json")
    )


@app.put("/api/plants/{plant_id}", response_model=ApiResponse, summary="更新植物档案")
async def update_plant(plant_id: str, plant_update: PlantUpdate):
    plant = plants_db.get(plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)
    
    update_data = plant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plant, key, value)
    
    plant.updated_at = datetime.now()
    
    return api_response(
        code=200,
        message="植物档案更新成功",
        data=plant.model_dump(mode="json")
    )


@app.delete("/api/plants/{plant_id}", response_model=ApiResponse, summary="删除植物档案")
async def delete_plant(plant_id: str):
    if plant_id not in plants_db:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)
    
    del plants_db[plant_id]
    
    return api_response(
        code=200,
        message="植物档案删除成功",
        data={"plant_id": plant_id}
    )


@app.post("/api/watering/report", response_model=ApiResponse, summary="上报浇水记录和环境数据")
async def report_watering(report: WateringReport):
    plant = plants_db.get(report.plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {report.plant_id} 不存在", data=None)
    
    if report.report_time is None:
        report.report_time = datetime.now()
    
    watering_engine.add_report(report)
    
    try:
        prediction = watering_engine.predict_watering(
            plant_id=report.plant_id,
            plant_species=plant.species,
            pot_material=plant.pot_material,
            soil_type=plant.soil_type,
            last_report=report
        )
        
        alerts = watering_engine.detect_anomalies(
            plant_id=report.plant_id,
            plant_species=plant.species,
            last_report=report,
            prediction=prediction
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"数据分析失败: {str(e)}",
            data=None
        )
    
    return api_response(
        code=200,
        message="数据上报成功",
        data={
            "report": report.model_dump(mode="json"),
            "prediction": prediction.model_dump(mode="json"),
            "alerts": [alert.model_dump(mode="json") for alert in alerts]
        }
    )


@app.get("/api/watering/predict/{plant_id}", response_model=ApiResponse, summary="获取浇水预测")
async def get_watering_prediction(plant_id: str):
    plant = plants_db.get(plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)
    
    history = watering_engine.get_plant_history(plant_id)
    if not history:
        return api_response(
            code=400,
            message="没有浇水记录，请先上报浇水数据",
            data={"plant_id": plant_id}
        )
    
    last_report = history[-1]
    
    try:
        prediction = watering_engine.predict_watering(
            plant_id=plant_id,
            plant_species=plant.species,
            pot_material=plant.pot_material,
            soil_type=plant.soil_type,
            last_report=last_report
        )
    except Exception as e:
        return api_response(
            code=500,
            message=f"预测失败: {str(e)}",
            data=None
        )
    
    return api_response(
        code=200,
        message="浇水预测成功",
        data=prediction.model_dump(mode="json")
    )


@app.get("/api/watering/alerts/{plant_id}", response_model=ApiResponse, summary="获取异常提醒")
async def get_anomaly_alerts(plant_id: str):
    plant = plants_db.get(plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)
    
    history = watering_engine.get_plant_history(plant_id)
    if not history:
        return api_response(
            code=200,
            message="暂无浇水记录",
            data={"alerts": []}
        )
    
    last_report = history[-1]
    
    prediction = watering_engine.predict_watering(
        plant_id=plant_id,
        plant_species=plant.species,
        pot_material=plant.pot_material,
        soil_type=plant.soil_type,
        last_report=last_report
    )
    
    alerts = watering_engine.detect_anomalies(
        plant_id=plant_id,
        plant_species=plant.species,
        last_report=last_report,
        prediction=prediction
    )
    
    return api_response(
        code=200,
        message=f"获取到 {len(alerts)} 条提醒",
        data={
            "total_alerts": len(alerts),
            "alerts": [alert.model_dump(mode="json") for alert in alerts]
        }
    )


@app.get("/api/maintenance/suggestions/{plant_id}", response_model=ApiResponse, summary="获取养护建议")
async def get_maintenance_suggestions(plant_id: str):
    plant = plants_db.get(plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)
    
    history = watering_engine.get_plant_history(plant_id)
    if not history:
        return api_response(
            code=200,
            message="暂无浇水记录，基础建议",
            data={
                "suggestions": [
                    {
                        "plant_id": plant_id,
                        "category": "general",
                        "suggestion": "请先上报浇水记录和环境数据以获取个性化建议",
                        "priority": "low",
                        "reason": "缺乏历史数据，无法生成精准建议"
                    }
                ]
            }
        )
    
    last_report = history[-1]
    
    prediction = watering_engine.predict_watering(
        plant_id=plant_id,
        plant_species=plant.species,
        pot_material=plant.pot_material,
        soil_type=plant.soil_type,
        last_report=last_report
    )
    
    suggestions = watering_engine.generate_maintenance_suggestions(
        plant_id=plant_id,
        plant_species=plant.species,
        last_report=last_report,
        prediction=prediction
    )
    
    return api_response(
        code=200,
        message=f"获取到 {len(suggestions)} 条养护建议",
        data={
            "total_suggestions": len(suggestions),
            "suggestions": [s.model_dump(mode="json") for s in suggestions]
        }
    )


@app.get("/api/plants/{plant_id}/statistics", response_model=ApiResponse, summary="获取植物统计信息")
async def get_plant_statistics(plant_id: str):
    plant = plants_db.get(plant_id)
    if not plant:
        return api_response(code=404, message=f"植物ID {plant_id} 不存在", data=None)
    
    history = watering_engine.get_plant_history(plant_id)
    if not history:
        return api_response(
            code=400,
            message="没有浇水记录",
            data={"plant_id": plant_id}
        )
    
    stats = watering_engine.get_plant_statistics(
        plant_id=plant_id,
        plant_name=plant.name,
        plant_species=plant.species
    )
    
    if not stats:
        return api_response(
            code=500,
            message="统计数据生成失败",
            data=None
        )
    
    stats["last_watering"] = stats["last_watering"].isoformat()
    stats["next_predicted_watering"] = stats["next_predicted_watering"].isoformat()
    
    return api_response(
        code=200,
        message="获取统计信息成功",
        data=stats
    )


@app.get("/api/plants/statistics/all", response_model=ApiResponse, summary="获取所有植物统计信息")
async def get_all_plants_statistics():
    all_stats = []
    
    for plant_id, plant in plants_db.items():
        history = watering_engine.get_plant_history(plant_id)
        if not history:
            continue
        
        stats = watering_engine.get_plant_statistics(
            plant_id=plant_id,
            plant_name=plant.name,
            plant_species=plant.species
        )
        
        if stats:
            stats["last_watering"] = stats["last_watering"].isoformat()
            stats["next_predicted_watering"] = stats["next_predicted_watering"].isoformat()
            all_stats.append(stats)
    
    return api_response(
        code=200,
        message=f"获取到 {len(all_stats)} 个植物的统计信息",
        data={
            "total": len(all_stats),
            "statistics": all_stats
        }
    )


@app.get("/api/plants/info/species", response_model=ApiResponse, summary="获取支持的植物品种列表")
async def get_supported_species():
    species_list = []
    for key, info in PLANT_DATABASE.items():
        species_list.append({
            "species_key": key,
            "name": info["name"],
            "base_watering_interval_days": info["base_watering_interval_days"],
            "optimal_temp_range": f"{info['optimal_temp_min']}-{info['optimal_temp_max']}°C",
            "optimal_humidity_range": f"{info['optimal_humidity_min']}-{info['optimal_humidity_max']}%",
            "light_preference": info["light_preference"]
        })
    
    return api_response(
        code=200,
        message=f"共支持 {len(species_list)} 种植物",
        data={"species": species_list}
    )


@app.get("/api/health", response_model=ApiResponse, summary="健康检查")
async def health_check():
    return api_response(
        code=200,
        message="服务运行正常",
        data={
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "total_plants": len(plants_db),
            "version": "1.0.0"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9201)
