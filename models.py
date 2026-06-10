from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class PlantCreate(BaseModel):
    name: str = Field(..., description="植物名称")
    species: str = Field(..., description="植物品种")
    pot_material: str = Field(..., description="花盆材质: ceramic, plastic, clay, metal, glass")
    soil_type: str = Field(..., description="盆土类型: peat, loam, sand, clay, coco")
    location: Optional[str] = Field(None, description="摆放位置")
    notes: Optional[str] = Field(None, description="备注")


class PlantUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    pot_material: Optional[str] = None
    soil_type: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class Plant(PlantCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class WateringReport(BaseModel):
    plant_id: str = Field(..., description="植物ID")
    temperature: float = Field(..., description="室内温度 (°C)")
    humidity: float = Field(..., description="室内湿度 (%)")
    last_watering_time: datetime = Field(..., description="上次浇水时间")
    soil_moisture: Optional[float] = Field(None, description="土壤湿度 (%)")
    light_intensity: Optional[float] = Field(None, description="光照强度 (lux)")
    report_time: Optional[datetime] = Field(default_factory=datetime.now)


class WateringPrediction(BaseModel):
    plant_id: str
    predicted_next_watering: datetime
    watering_window_start: datetime
    watering_window_end: datetime
    days_until_next_watering: float
    avg_watering_interval: float
    seasonal_adjustment_coefficient: float
    adaptation_score: float
    confidence: float
    evaporation_rate: float


class AnomalyAlert(BaseModel):
    plant_id: str
    alert_type: str
    severity: str
    message: str
    timestamp: datetime
    suggestions: List[str]


class MaintenanceSuggestion(BaseModel):
    plant_id: str
    category: str
    suggestion: str
    priority: str
    reason: str


class PlantStatistics(BaseModel):
    plant_id: str
    plant_name: str
    species: str
    avg_watering_interval: float
    seasonal_adjustment_coefficient: float
    adaptation_score: float
    total_watering_reports: int
    last_watering: datetime
    next_predicted_watering: datetime


class ApiResponse(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None
