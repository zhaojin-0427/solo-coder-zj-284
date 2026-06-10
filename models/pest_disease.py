from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class SymptomType(str, Enum):
    LEAF_SPOT = "leaf_spot"
    YELLOW_LEAF = "yellow_leaf"
    BLACK_SPOT = "black_spot"
    LEAF_CURL = "leaf_curl"
    MOLD = "mold"
    PEST = "pest"
    WILT = "wilt"
    ROT = "rot"
    OTHER = "other"


class PestType(str, Enum):
    APHID = "aphid"
    MEALYBUG = "mealybug"
    SPIDER_MITE = "spider_mite"
    SCALE = "scale"
    WHITEFLY = "whitefly"
    FUNGUS_GNAT = "fungus_gnat"
    CATERPILLAR = "caterpillar"
    OTHER = "other"
    UNKNOWN = "unknown"


class DiseaseType(str, Enum):
    FUNGAL = "fungal"
    BACTERIAL = "bacterial"
    VIRAL = "viral"
    NUTRITIONAL = "nutritional"
    ENVIRONMENTAL = "environmental"
    OTHER = "other"
    UNKNOWN = "unknown"


class SeverityLevel(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class LeafCondition(str, Enum):
    HEALTHY = "healthy"
    SPOTTED = "spotted"
    YELLOWED = "yellowed"
    WILTED = "wilted"
    CURLED = "curled"
    MOLDED = "molded"
    BROWNED = "browned"
    DROPPED = "dropped"


class PestSignReport(BaseModel):
    has_pest: bool = Field(False, description="是否发现虫害迹象")
    pest_type: Optional[PestType] = Field(None, description="疑似虫害类型")
    pest_count: Optional[str] = Field(None, description="虫害数量描述: few, many, swarm")
    pest_location: Optional[str] = Field(None, description="虫害位置: leaf_back, stem, soil, new_growth")


class SymptomReport(BaseModel):
    symptom_types: List[SymptomType] = Field(default_factory=list, description="症状类型列表")
    affected_area: Optional[str] = Field(None, description="受影响区域: leaves, stem, roots, whole_plant")
    affected_percentage: Optional[int] = Field(None, ge=0, le=100, description="受影响面积百分比")
    has_necrotic_tissue: Optional[bool] = Field(None, description="是否有坏死组织")
    has_odor: Optional[bool] = Field(None, description="是否有异味")
    color_change: Optional[str] = Field(None, description="颜色变化描述")
    texture_change: Optional[str] = Field(None, description="质地变化描述")


class PestDiseaseCreate(BaseModel):
    plant_id: str = Field(..., description="植物ID")
    leaf_condition: LeafCondition = Field(..., description="叶片状态")
    pest_signs: PestSignReport = Field(..., description="虫害迹象报告")
    symptoms: SymptomReport = Field(..., description="症状报告")
    suspected_disease_type: Optional[DiseaseType] = Field(None, description="疑似病害类型")
    suspected_pest_type: Optional[PestType] = Field(None, description="疑似虫害类型")
    discovery_time: datetime = Field(default_factory=datetime.now, description="发现时间")
    severity: SeverityLevel = Field(..., description="严重程度")
    image_description: Optional[str] = Field(None, description="图片描述信息")
    notes: Optional[str] = Field(None, description="备注信息")


class PestDiseaseRecord(BaseModel):
    id: str
    plant_id: str
    leaf_condition: LeafCondition
    pest_signs: PestSignReport
    symptoms: SymptomReport
    suspected_disease_type: Optional[DiseaseType]
    suspected_pest_type: Optional[PestType]
    discovery_time: datetime
    severity: SeverityLevel
    image_description: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    status: str = Field("open", description="记录状态: open, in_treatment, resolved, closed")
    treatment_history: List[Dict[str, Any]] = Field(default_factory=list)


class TreatmentStep(BaseModel):
    step: int = Field(..., description="步骤序号")
    action: str = Field(..., description="处置动作")
    description: str = Field(..., description="详细说明")
    urgency: str = Field(..., description="紧急程度: immediate, soon, scheduled")
    estimated_duration: Optional[str] = Field(None, description="预计耗时")


class QuarantineAdvice(BaseModel):
    needs_quarantine: bool = Field(..., description="是否需要隔离")
    reason: str = Field(..., description="隔离原因")
    recommended_location: str = Field(..., description="建议隔离位置")
    duration_days: int = Field(..., description="建议隔离天数")
    precautions: List[str] = Field(default_factory=list, description="隔离注意事项")


class ReviewReminder(BaseModel):
    needs_review: bool = Field(..., description="是否需要复查")
    review_time: datetime = Field(..., description="建议复查时间")
    review_focus: List[str] = Field(default_factory=list, description="复查重点")
    follow_up_actions: List[str] = Field(default_factory=list, description="后续行动建议")


class ZoneSpreadRisk(BaseModel):
    risk_level: RiskLevel = Field(..., description="同分区传播风险等级")
    affected_plants_count: int = Field(..., description="已受影响植物数量")
    similar_symptoms_count: int = Field(..., description="出现相似症状植物数量")
    vulnerable_plants: List[Dict[str, Any]] = Field(default_factory=list, description="易受影响植物列表")
    spread_vector: str = Field(..., description="可能传播途径")
    preventive_measures: List[str] = Field(default_factory=list, description="预防措施")


class ActionableAdvice(BaseModel):
    suspend_watering: bool = Field(False, description="是否建议暂停浇水")
    watering_suspend_days: Optional[int] = Field(None, description="暂停浇水天数")
    improve_ventilation: bool = Field(False, description="是否建议改善通风")
    ventilation_advice: Optional[str] = Field(None, description="通风改善建议")
    move_out_of_zone: bool = Field(False, description="是否建议移出分区")
    remove_infected_leaves: bool = Field(False, description="是否建议清理病叶")
    leaf_removal_advice: Optional[str] = Field(None, description="病叶清理建议")
    adjust_soil: bool = Field(False, description="是否建议调整盆土")
    soil_adjustment_advice: Optional[str] = Field(None, description="盆土调整建议")
    needs_review_plan: bool = Field(False, description="是否需要设置复查计划")


class PestDiseaseAnalysis(BaseModel):
    record_id: str
    plant_id: str
    plant_name: str
    species: str
    zone_id: Optional[str]
    zone_name: Optional[str]
    risk_level: RiskLevel
    overall_risk_score: int
    possible_causes: List[Dict[str, Any]]
    quarantine_advice: QuarantineAdvice
    treatment_steps: List[TreatmentStep]
    review_reminder: ReviewReminder
    zone_spread_risk: ZoneSpreadRisk
    actionable_advice: ActionableAdvice
    environmental_factors: Dict[str, Any]
    watering_factors: Dict[str, Any]
    explanation: str
    confidence: float


class TreatmentUpdate(BaseModel):
    record_id: str
    action_taken: str = Field(..., description="已采取的处置措施")
    treatment_time: datetime = Field(default_factory=datetime.now)
    effectiveness: Optional[str] = Field(None, description="效果评估: improved, unchanged, worsened")
    notes: Optional[str] = Field(None, description="备注")


class RecordStatusUpdate(BaseModel):
    status: str = Field(..., description="新状态: open, in_treatment, resolved, closed")
    notes: Optional[str] = Field(None, description="状态变更说明")
