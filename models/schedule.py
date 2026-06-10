from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum


class SchedulePriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WateringStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    OVERDUE = "overdue"


class ConflictType(str, Enum):
    WATERING_RHYTHM_MISMATCH = "watering_rhythm_mismatch"
    HUMIDITY_ABNORMAL = "humidity_abnormal"
    CONSISTENT_DEVIATION = "consistent_deviation"
    PREDICTION_WINDOW_CONFLICT = "prediction_window_conflict"
    ENVIRONMENT_MISMATCH = "environment_mismatch"


class AdjustmentAction(str, Enum):
    RELOCATE_PLANT = "relocate_plant"
    CHANGE_SOIL = "change_soil"
    CHANGE_POT = "change_pot"
    SPLIT_ZONE = "split_zone"
    ADJUST_WATERING_FREQUENCY = "adjust_watering_frequency"
    ADD_HUMIDIFIER = "add_humidifier"
    IMPROVE_VENTILATION = "improve_ventilation"


class PlantWateringTask(BaseModel):
    plant_id: str
    plant_name: str
    species: str
    scheduled_date: date
    scheduled_time_start: Optional[datetime] = None
    scheduled_time_end: Optional[datetime] = None
    priority: SchedulePriority
    water_amount_ml: Optional[float] = None
    status: WateringStatus
    predicted_next_watering: datetime
    days_until_watering: float
    risk_level: str
    notes: Optional[str] = None


class BatchWateringGroup(BaseModel):
    group_id: str
    scheduled_date: date
    plant_ids: List[str]
    plant_names: List[str]
    total_plants: int
    priority: SchedulePriority
    suggested_time: str
    water_amount_total_ml: Optional[float] = None
    notes: Optional[str] = None


class ScheduleDay(BaseModel):
    date: date
    day_of_week: str
    is_today: bool
    total_tasks: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    tasks: List[PlantWateringTask]
    batch_groups: List[BatchWateringGroup]


class ConflictDetail(BaseModel):
    conflict_id: str
    conflict_type: ConflictType
    severity: str
    plant_ids: List[str]
    plant_names: List[str]
    description: str
    impact: str
    data_evidence: Dict[str, Any]


class AdjustmentSuggestion(BaseModel):
    suggestion_id: str
    conflict_id: str
    action: AdjustmentAction
    title: str
    description: str
    priority: SchedulePriority
    expected_benefit: str
    implementation_difficulty: str
    affected_plants: List[str]
    alternative_solutions: List[str]


class WateringScheduleResponse(BaseModel):
    zone_id: str
    zone_name: str
    schedule_days: int
    start_date: date
    end_date: date
    generated_at: datetime
    total_tasks: int
    batch_groups_count: int
    conflicts_count: int
    schedule: List[ScheduleDay]
    priority_summary: Dict[str, int]


class ConflictAnalysisResponse(BaseModel):
    zone_id: str
    zone_name: str
    analyzed_at: datetime
    total_conflicts: int
    conflicts: List[ConflictDetail]
    adjustment_suggestions: List[AdjustmentSuggestion]
    overall_health_score: float
    recommendations: List[str]


class WateringPatternAnalysis(BaseModel):
    plant_id: str
    plant_name: str
    avg_interval_days: float
    std_deviation_days: float
    consistency_score: float
    early_watering_count: int
    late_watering_count: int
    consecutive_early_count: int
    consecutive_late_count: int
    pattern_status: str


class ZoneWateringStats(BaseModel):
    zone_id: str
    zone_name: str
    total_plants: int
    avg_watering_interval: float
    interval_variance: float
    rhythm_diversity_score: float
    min_interval: float
    max_interval: float
    plant_patterns: List[WateringPatternAnalysis]


class ScheduleGenerateRequest(BaseModel):
    zone_id: str
    days_ahead: int = Field(7, ge=1, le=90, description="生成未来多少天的排程，支持7/14/30天")


class ConflictDetectRequest(BaseModel):
    zone_id: str


class ReminderChannel(str, Enum):
    APP_PUSH = "app_push"
    EMAIL = "email"
    SMS = "sms"
    WECHAT = "wechat"


class ReminderFrequency(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    HOURLY = "hourly"
    CUSTOM = "custom"


class ReminderStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    READ = "read"
    DISMISSED = "dismissed"
    FAILED = "failed"


class ReminderConfig(BaseModel):
    enabled: bool = Field(True, description="是否启用提醒")
    channels: List[ReminderChannel] = Field(default_factory=lambda: [ReminderChannel.APP_PUSH], description="提醒渠道")
    frequency: ReminderFrequency = Field(ReminderFrequency.ONCE, description="提醒频率")
    advance_hours: int = Field(24, ge=1, le=168, description="提前多少小时提醒")
    include_high_priority: bool = Field(True, description="是否包含高优先级任务")
    include_critical_only: bool = Field(False, description="只包含紧急任务")
    send_batch_summary: bool = Field(True, description="是否发送批量浇水汇总")


class Reminder(BaseModel):
    reminder_id: str
    zone_id: str
    zone_name: str
    plant_id: Optional[str] = None
    plant_name: Optional[str] = None
    task_id: Optional[str] = None
    reminder_type: str
    title: str
    message: str
    priority: SchedulePriority
    scheduled_time: datetime
    channel: ReminderChannel
    status: ReminderStatus
    created_at: datetime
    sent_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReminderGenerateRequest(BaseModel):
    zone_id: Optional[str] = Field(None, description="分区ID，为空则生成全部分区")
    hours_ahead: int = Field(24, ge=1, le=168, description="未来多少小时内的任务需要提醒")
    config: Optional[ReminderConfig] = None


class ReminderListResponse(BaseModel):
    total_reminders: int
    pending_count: int
    sent_count: int
    critical_count: int
    high_count: int
    reminders: List[Reminder]
