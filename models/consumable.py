from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum


class ConsumableCategory(str, Enum):
    FERTILIZER = "fertilizer"
    NUTRIENT_SOLUTION = "nutrient_solution"
    FUNGICIDE = "fungicide"
    INSECTICIDE = "insecticide"
    SOIL = "soil"
    CLAY_PELLETS = "clay_pellets"
    SPRAYER_FILTER = "sprayer_filter"
    PESTICIDE = "pesticide"
    OTHER = "other"


class StorageCondition(str, Enum):
    ROOM_TEMP = "room_temperature"
    COOL_DRY = "cool_dry"
    REFRIGERATED = "refrigerated"
    AVOID_SUNLIGHT = "avoid_sunlight"
    SEALED = "sealed"


class SupplierInfo(BaseModel):
    name: str = Field(..., description="供应商名称")
    contact: Optional[str] = Field(None, description="联系人")
    phone: Optional[str] = Field(None, description="联系电话")
    address: Optional[str] = Field(None, description="地址")
    website: Optional[str] = Field(None, description="网址")
    notes: Optional[str] = Field(None, description="供应商备注")


class ConsumableCreate(BaseModel):
    name: str = Field(..., description="耗材名称")
    category: ConsumableCategory = Field(..., description="耗材分类")
    specification: str = Field(..., description="规格描述，如500g/瓶、1L/袋")
    unit: str = Field(..., description="计量单位，如瓶、袋、升、公斤")
    current_stock: float = Field(..., description="当前库存数量", ge=0)
    min_safe_stock: float = Field(..., description="最低安全库存", ge=0)
    unit_price: Optional[float] = Field(None, description="单价", ge=0)
    applicable_species: Optional[List[str]] = Field(None, description="适用植物品类")
    applicable_zones: Optional[List[str]] = Field(None, description="适用分区ID列表")
    expiry_date: Optional[date] = Field(None, description="保质期到期日期")
    opened_at: Optional[datetime] = Field(None, description="开封时间")
    shelf_life_days_after_open: Optional[int] = Field(None, description="开封后保质期天数")
    storage_location: Optional[str] = Field(None, description="存放位置")
    storage_condition: Optional[StorageCondition] = Field(None, description="存储条件")
    supplier: Optional[SupplierInfo] = Field(None, description="供应商信息")
    is_critical: bool = Field(False, description="是否为关键耗材")
    alternatives: Optional[List[str]] = Field(None, description="可替代耗材ID列表")
    notes: Optional[str] = Field(None, description="备注")
    consumption_rate_per_plant: Optional[float] = Field(None, description="单株植物每次消耗量估算")
    typical_usage_interval_days: Optional[int] = Field(None, description="典型使用间隔天数")


class ConsumableUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[ConsumableCategory] = None
    specification: Optional[str] = None
    unit: Optional[str] = None
    current_stock: Optional[float] = None
    min_safe_stock: Optional[float] = None
    unit_price: Optional[float] = None
    applicable_species: Optional[List[str]] = None
    applicable_zones: Optional[List[str]] = None
    expiry_date: Optional[date] = None
    opened_at: Optional[datetime] = None
    shelf_life_days_after_open: Optional[int] = None
    storage_location: Optional[str] = None
    storage_condition: Optional[StorageCondition] = None
    supplier: Optional[SupplierInfo] = None
    is_critical: Optional[bool] = None
    alternatives: Optional[List[str]] = None
    notes: Optional[str] = None
    consumption_rate_per_plant: Optional[float] = None
    typical_usage_interval_days: Optional[int] = None


class Consumable(BaseModel):
    id: str
    name: str
    category: ConsumableCategory
    specification: str
    unit: str
    current_stock: float
    min_safe_stock: float
    unit_price: Optional[float] = None
    applicable_species: Optional[List[str]] = None
    applicable_zones: Optional[List[str]] = None
    expiry_date: Optional[date] = None
    opened_at: Optional[datetime] = None
    shelf_life_days_after_open: Optional[int] = None
    storage_location: Optional[str] = None
    storage_condition: Optional[StorageCondition] = None
    supplier: Optional[SupplierInfo] = None
    is_critical: bool = False
    alternatives: Optional[List[str]] = None
    notes: Optional[str] = None
    consumption_rate_per_plant: Optional[float] = None
    typical_usage_interval_days: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class StockAdjustment(BaseModel):
    consumable_id: str = Field(..., description="耗材ID")
    adjustment_type: str = Field(..., description="调整类型: restock, consume, discard, transfer")
    quantity: float = Field(..., description="调整数量，正数增加，负数减少")
    reason: str = Field(..., description="调整原因")
    related_operation_id: Optional[str] = Field(None, description="关联的养护操作ID")
    adjusted_at: datetime = Field(default_factory=datetime.now)
    operator: Optional[str] = Field(None, description="操作人")
    notes: Optional[str] = Field(None, description="备注")


class StockTransaction(BaseModel):
    id: str
    consumable_id: str
    adjustment_type: str
    quantity: float
    reason: str
    related_operation_id: Optional[str] = None
    adjusted_at: datetime
    operator: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class ConsumptionEstimate(BaseModel):
    consumable_id: str
    consumable_name: str
    category: ConsumableCategory
    days_horizon: int
    estimated_consumption: float
    unit: str
    current_stock: float
    projected_end_stock: float
    consumption_breakdown: List[Dict[str, Any]]
    confidence: float


class StockRiskLevel(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


class ExpiryRiskLevel(str, Enum):
    FRESH = "fresh"
    NEAR_EXPIRY = "near_expiry"
    EXPIRED = "expired"


class StockRiskAssessment(BaseModel):
    consumable_id: str
    consumable_name: str
    category: ConsumableCategory
    current_stock: float
    min_safe_stock: float
    stock_to_min_ratio: float
    stock_risk_level: StockRiskLevel
    stock_risk_score: int
    expiry_risk_level: ExpiryRiskLevel
    expiry_risk_score: int
    days_to_expiry: Optional[int] = None
    days_remaining_after_open: Optional[int] = None
    overall_risk_score: int
    overall_risk_level: str
    affected_tasks_count: Optional[int] = None
    affected_zones_count: Optional[int] = None
    affected_plants_count: Optional[int] = None
    risk_factors: List[str]


class SubstituteFeasibility(BaseModel):
    consumable_id: str
    consumable_name: str
    has_alternatives: bool
    alternative_count: int
    alternatives_available: List[Dict[str, Any]]
    overall_feasibility: str
    feasibility_score: int
    notes: Optional[str] = None


class ProcurementPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProcurementItem(BaseModel):
    consumable_id: str
    consumable_name: str
    category: ConsumableCategory
    specification: str
    unit: str
    current_stock: float
    min_safe_stock: float
    recommended_quantity: float
    unit_price: Optional[float] = None
    estimated_total_cost: Optional[float] = None
    supplier: Optional[SupplierInfo] = None
    priority: ProcurementPriority
    priority_score: int
    reason: List[str]
    urgency_days: Optional[int] = None


class RestockSuggestion(BaseModel):
    suggestion_id: str
    consumable_id: str
    consumable_name: str
    category: ConsumableCategory
    action: str
    recommended_quantity: float
    unit: str
    priority: ProcurementPriority
    estimated_cost: Optional[float] = None
    reason: List[str]
    evidence: Dict[str, Any]
    supplier: Optional[SupplierInfo] = None
    suggested_purchase_date: Optional[date] = None
    deadline_date: Optional[date] = None


class ExpiryAlert(BaseModel):
    alert_id: str
    consumable_id: str
    consumable_name: str
    category: ConsumableCategory
    specification: str
    alert_type: str
    severity: str
    expiry_date: Optional[date] = None
    opened_at: Optional[datetime] = None
    days_to_expiry: Optional[int] = None
    days_after_opened: Optional[int] = None
    days_remaining_after_open: Optional[int] = None
    remaining_stock: float
    unit: str
    estimated_waste_cost: Optional[float] = None
    recent_usage_frequency: str
    can_be_used_up: bool
    suggestions: List[str]


class CostOverview(BaseModel):
    total_inventory_value: float
    total_estimated_purchase_cost: float
    estimated_waste_value: float
    monthly_consumption_value: Optional[float] = None
    category_breakdown: List[Dict[str, Any]]
    top_cost_items: List[Dict[str, Any]]
    cost_efficiency_score: float
    saving_opportunities: List[Dict[str, Any]]


class AdjustmentType(str, Enum):
    ADVANCE_PURCHASE = "advance_purchase"
    DELAY_NON_URGENT = "delay_non_urgent"
    SWITCH_ALTERNATIVE = "switch_alternative"
    MERGE_BATCH = "merge_batch"
    REDUCE_USAGE = "reduce_usage"
    EMERGENCY_PURCHASE = "emergency_purchase"


class AdjustmentSuggestion(BaseModel):
    suggestion_id: str
    suggestion_type: AdjustmentType
    title: str
    description: str
    priority: str
    trigger_condition: str
    affected_consumables: List[Dict[str, Any]]
    affected_zones: List[Dict[str, Any]]
    affected_tasks: List[Dict[str, Any]]
    recommended_action: str
    alternative_actions: List[Dict[str, Any]]
    expected_outcome: str
    potential_risks: List[str]
    supporting_data: Dict[str, Any]
    explanation: str
    confidence: float
    generated_at: datetime


class ConsumableAssessmentResponse(BaseModel):
    assessment_time: datetime
    horizon_days: int
    total_consumables: int
    consumption_estimates: List[ConsumptionEstimate]
    risk_assessments: List[StockRiskAssessment]
    substitute_feasibility: List[SubstituteFeasibility]
    procurement_items: List[ProcurementItem]
    restock_suggestions: List[RestockSuggestion]
    expiry_alerts: List[ExpiryAlert]
    cost_overview: CostOverview
    adjustment_suggestions: List[AdjustmentSuggestion]
    summary: Dict[str, Any]
