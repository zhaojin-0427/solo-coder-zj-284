from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class ZoneType(str, Enum):
    LIVING_ROOM = "living_room"
    BALCONY = "balcony"
    BEDROOM = "bedroom"
    OFFICE = "office"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    STUDY = "study"
    GARDEN = "garden"
    OTHER = "other"


class LightLevel(str, Enum):
    DIRECT_SUN = "direct_sun"
    BRIGHT_INDIRECT = "bright_indirect"
    MEDIUM = "medium"
    LOW = "low"
    SHADE = "shade"


class VentilationLevel(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"


class ZoneEnvironment(BaseModel):
    avg_temperature: Optional[float] = Field(None, description="分区平均温度 (°C)")
    avg_humidity: Optional[float] = Field(None, description="分区平均湿度 (%)")
    light_level: Optional[LightLevel] = Field(None, description="光照强度等级")
    ventilation: Optional[VentilationLevel] = Field(None, description="通风情况")
    has_air_conditioner: Optional[bool] = Field(False, description="是否有空调")
    has_heater: Optional[bool] = Field(False, description="是否有暖气")
    is_near_window: Optional[bool] = Field(False, description="是否靠近窗户")
    notes: Optional[str] = Field(None, description="环境备注")


class ZoneCreate(BaseModel):
    name: str = Field(..., description="分区名称，如客厅、阳台")
    zone_type: ZoneType = Field(..., description="分区类型")
    description: Optional[str] = Field(None, description="分区描述")
    environment: Optional[ZoneEnvironment] = Field(None, description="分区环境特征")


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    zone_type: Optional[ZoneType] = None
    description: Optional[str] = None
    environment: Optional[ZoneEnvironment] = None


class ZoneBindPlant(BaseModel):
    plant_ids: List[str] = Field(..., description="要绑定的植物ID列表")


class ZoneUnbindPlant(BaseModel):
    plant_ids: List[str] = Field(..., description="要解绑的植物ID列表")


class Zone(BaseModel):
    id: str
    name: str
    zone_type: ZoneType
    description: Optional[str] = None
    environment: Optional[ZoneEnvironment] = None
    plant_ids: List[str] = Field(default_factory=list, description="绑定的植物ID列表")
    created_at: datetime
    updated_at: datetime


class ZoneRiskAssessment(BaseModel):
    zone_id: str
    zone_name: str
    overall_risk_level: str
    rot_risk_count: int
    drought_risk_count: int
    conflict_count: int
    avg_adaptation_score: float
    risk_details: List[Dict[str, Any]]


class ZoneSummary(BaseModel):
    id: str
    name: str
    zone_type: ZoneType
    plant_count: int
    environment: Optional[ZoneEnvironment]
    last_updated: datetime
