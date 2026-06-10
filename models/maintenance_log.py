from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class MaintenanceOperationType(str, Enum):
    WATERING = "watering"
    FERTILIZING = "fertilizing"
    REPOTTING = "repotting"
    PRUNING = "pruning"
    VENTILATION = "ventilation"
    ISOLATION = "isolation"
    SPRAYING = "spraying"
    REMOVE_DISEASED_LEAVES = "remove_diseased_leaves"
    ADJUST_POSITION = "adjust_position"
    SOIL_REPLACEMENT = "soil_replacement"
    PEST_CONTROL = "pest_control"
    DISEASE_TREATMENT = "disease_treatment"
    LIGHT_ADJUSTMENT = "light_adjustment"
    HUMIDITY_ADJUSTMENT = "humidity_adjustment"
    TEMPERATURE_ADJUSTMENT = "temperature_adjustment"
    OTHER = "other"


class OperationEffectiveness(str, Enum):
    VERY_EFFECTIVE = "very_effective"
    EFFECTIVE = "effective"
    PARTIALLY_EFFECTIVE = "partially_effective"
    INEFFECTIVE = "ineffective"
    HARMFUL = "harmful"
    PENDING = "pending"


class RecoveryTrend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"
    FLUCTUATING = "fluctuating"


class AdjustmentType(str, Enum):
    CONTINUE_CURRENT = "continue_current"
    MODIFY_SCHEME = "modify_scheme"
    UPGRADE_TREATMENT = "upgrade_treatment"
    ROLLBACK_OPERATION = "rollback_operation"
    REQUEST_HUMAN_INSPECTION = "request_human_inspection"
    CHANGE_METHOD = "change_method"
    SUSPEND_OPERATION = "suspend_operation"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class PlantStatus(BaseModel):
    health_score: Optional[int] = Field(None, ge=0, le=100, description="健康评分 0-100")
    leaf_condition: Optional[str] = Field(None, description="叶片状态描述")
    growth_status: Optional[str] = Field(None, description="生长状态")
    has_new_growth: Optional[bool] = Field(None, description="是否有新生长")
    pest_signs: Optional[str] = Field(None, description="虫害迹象")
    disease_signs: Optional[str] = Field(None, description="病害迹象")
    soil_moisture: Optional[float] = Field(None, description="土壤湿度 (%)")
    notes: Optional[str] = Field(None, description="状态备注")


class MaintenanceLogCreate(BaseModel):
    target_type: str = Field(..., description="目标类型: plant 或 zone")
    target_id: str = Field(..., description="目标ID：植物ID或分区ID")
    operation_type: MaintenanceOperationType = Field(..., description="操作类型")
    operation_subtype: Optional[str] = Field(None, description="操作子类型，如具体肥料名称、药剂名称等")
    execution_time: datetime = Field(default_factory=datetime.now, description="执行时间")
    executor: str = Field(..., description="执行人")
    operation_reason: str = Field(..., description="操作原因")
    status_before: PlantStatus = Field(..., description="操作前状态")
    status_after: Optional[PlantStatus] = Field(None, description="操作后状态")
    observation_result: Optional[str] = Field(None, description="观察结果")
    operation_details: Optional[Dict[str, Any]] = Field(None, description="操作细节，如浇水量、施肥量、药剂浓度等")
    related_pest_disease_record_id: Optional[str] = Field(None, description="关联的病虫害记录ID")
    notes: Optional[str] = Field(None, description="备注")


class MaintenanceLogUpdate(BaseModel):
    status_after: Optional[PlantStatus] = None
    observation_result: Optional[str] = None
    operation_details: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    effectiveness: Optional[OperationEffectiveness] = None


class MaintenanceLog(BaseModel):
    id: str
    target_type: str
    target_id: str
    operation_type: MaintenanceOperationType
    operation_subtype: Optional[str]
    execution_time: datetime
    executor: str
    operation_reason: str
    status_before: PlantStatus
    status_after: Optional[PlantStatus]
    observation_result: Optional[str]
    operation_details: Optional[Dict[str, Any]]
    related_pest_disease_record_id: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    effectiveness: OperationEffectiveness = Field(OperationEffectiveness.PENDING, description="操作有效性评估")
    follow_up_observations: List[Dict[str, Any]] = Field(default_factory=list, description="后续观察记录")


class FollowUpObservation(BaseModel):
    log_id: str = Field(..., description="养护日志ID")
    observation_time: datetime = Field(default_factory=datetime.now, description="观察时间")
    observer: str = Field(..., description="观察人")
    current_status: PlantStatus = Field(..., description="当前状态")
    observation_notes: str = Field(..., description="观察记录")


class OperationAnalysis(BaseModel):
    log_id: str
    target_type: str
    target_id: str
    operation_type: MaintenanceOperationType
    execution_time: datetime
    is_effective: bool
    effectiveness_score: int
    effectiveness: OperationEffectiveness
    recovery_trend: RecoveryTrend
    recovery_trend_confidence: float
    supporting_evidence: List[str]
    contradicting_evidence: List[str]
    has_duplicate_operations: bool
    duplicate_operation_count: int
    duplicate_operation_window_days: int
    similar_operations: List[Dict[str, Any]]
    environmental_factors: Dict[str, Any]
    watering_history_factors: Dict[str, Any]
    pest_disease_factors: Dict[str, Any]
    anomaly_alert_factors: Dict[str, Any]
    recommendation: str
    recommendation_type: AdjustmentType
    next_review_time: datetime
    review_focus: List[str]
    risk_warnings: List[Dict[str, Any]]
    overall_confidence: float
    explanation: str


class AdjustmentSuggestion(BaseModel):
    suggestion_id: str
    target_type: str
    target_id: str
    target_name: str
    trigger_type: str
    trigger_description: str
    current_scheme: str
    suggested_action: str
    adjustment_type: AdjustmentType
    reason: str
    supporting_data: Dict[str, Any]
    risk_level: RiskLevel
    priority: str
    expected_outcome: str
    alternative_options: List[Dict[str, Any]]
    generated_at: datetime


class ZoneAnalysisSummary(BaseModel):
    zone_id: str
    zone_name: str
    total_operations: int
    effective_operations: int
    ineffective_operations: int
    plants_with_improvement: int
    plants_with_deterioration: int
    plants_with_stable_status: int
    common_operations: List[Dict[str, Any]]
    problematic_patterns: List[Dict[str, Any]]
    zone_wide_adjustments: List[AdjustmentSuggestion]
    analysis_time: datetime
