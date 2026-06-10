from typing import Dict, List, Optional
from models.zone import ZoneType, LightLevel, VentilationLevel


ZONE_TYPE_DISPLAY: Dict[ZoneType, str] = {
    ZoneType.LIVING_ROOM: "客厅",
    ZoneType.BALCONY: "阳台",
    ZoneType.BEDROOM: "卧室",
    ZoneType.OFFICE: "办公室",
    ZoneType.KITCHEN: "厨房",
    ZoneType.BATHROOM: "浴室",
    ZoneType.STUDY: "书房",
    ZoneType.GARDEN: "花园",
    ZoneType.OTHER: "其他",
}


ZONE_TYPE_DEFAULT_ENVIRONMENT: Dict[ZoneType, Dict] = {
    ZoneType.LIVING_ROOM: {
        "avg_temperature": 22.0,
        "avg_humidity": 50.0,
        "light_level": LightLevel.BRIGHT_INDIRECT,
        "ventilation": VentilationLevel.MODERATE,
        "has_air_conditioner": True,
        "has_heater": True,
        "is_near_window": False,
    },
    ZoneType.BALCONY: {
        "avg_temperature": 20.0,
        "avg_humidity": 55.0,
        "light_level": LightLevel.DIRECT_SUN,
        "ventilation": VentilationLevel.EXCELLENT,
        "has_air_conditioner": False,
        "has_heater": False,
        "is_near_window": True,
    },
    ZoneType.BEDROOM: {
        "avg_temperature": 20.0,
        "avg_humidity": 45.0,
        "light_level": LightLevel.MEDIUM,
        "ventilation": VentilationLevel.MODERATE,
        "has_air_conditioner": True,
        "has_heater": True,
        "is_near_window": False,
    },
    ZoneType.OFFICE: {
        "avg_temperature": 24.0,
        "avg_humidity": 40.0,
        "light_level": LightLevel.MEDIUM,
        "ventilation": VentilationLevel.POOR,
        "has_air_conditioner": True,
        "has_heater": True,
        "is_near_window": False,
    },
    ZoneType.KITCHEN: {
        "avg_temperature": 25.0,
        "avg_humidity": 60.0,
        "light_level": LightLevel.BRIGHT_INDIRECT,
        "ventilation": VentilationLevel.GOOD,
        "has_air_conditioner": False,
        "has_heater": False,
        "is_near_window": True,
    },
    ZoneType.BATHROOM: {
        "avg_temperature": 22.0,
        "avg_humidity": 75.0,
        "light_level": LightLevel.LOW,
        "ventilation": VentilationLevel.POOR,
        "has_air_conditioner": False,
        "has_heater": True,
        "is_near_window": False,
    },
    ZoneType.STUDY: {
        "avg_temperature": 22.0,
        "avg_humidity": 45.0,
        "light_level": LightLevel.BRIGHT_INDIRECT,
        "ventilation": VentilationLevel.MODERATE,
        "has_air_conditioner": True,
        "has_heater": True,
        "is_near_window": False,
    },
    ZoneType.GARDEN: {
        "avg_temperature": 18.0,
        "avg_humidity": 65.0,
        "light_level": LightLevel.DIRECT_SUN,
        "ventilation": VentilationLevel.EXCELLENT,
        "has_air_conditioner": False,
        "has_heater": False,
        "is_near_window": False,
    },
    ZoneType.OTHER: {
        "avg_temperature": 22.0,
        "avg_humidity": 50.0,
        "light_level": LightLevel.MEDIUM,
        "ventilation": VentilationLevel.MODERATE,
        "has_air_conditioner": False,
        "has_heater": False,
        "is_near_window": False,
    },
}


LIGHT_LEVEL_SUGGESTED_PLANTS: Dict[LightLevel, List[str]] = {
    LightLevel.DIRECT_SUN: ["succulent", "cactus", "bonsai"],
    LightLevel.BRIGHT_INDIRECT: ["monstera", "fiddle_leaf_fig", "rubber_plant", "orchid"],
    LightLevel.MEDIUM: ["pothos", "snake_plant", "spider_plant", "rubber_plant"],
    LightLevel.LOW: ["peace_lily", "fern", "snake_plant", "pothos"],
    LightLevel.SHADE: ["snake_plant", "peace_lily"],
}


ZONE_TYPE_SUGGESTED_PLANTS: Dict[ZoneType, List[str]] = {
    ZoneType.LIVING_ROOM: ["monstera", "fiddle_leaf_fig", "snake_plant", "pothos", "spider_plant"],
    ZoneType.BALCONY: ["succulent", "cactus", "bonsai", "orchid", "fern"],
    ZoneType.BEDROOM: ["snake_plant", "peace_lily", "spider_plant", "pothos"],
    ZoneType.OFFICE: ["snake_plant", "pothos", "spider_plant", "peace_lily"],
    ZoneType.KITCHEN: ["spider_plant", "pothos", "herbs"],
    ZoneType.BATHROOM: ["fern", "peace_lily", "snake_plant"],
    ZoneType.STUDY: ["snake_plant", "pothos", "spider_plant", "rubber_plant"],
    ZoneType.GARDEN: ["bonsai", "succulent", "cactus", "orchid"],
    ZoneType.OTHER: ["snake_plant", "pothos", "spider_plant"],
}


SCHEDULE_RULES: Dict = {
    "batch_watering": {
        "max_time_window_hours": 4,
        "max_plants_per_group": 10,
        "priority_merge_threshold": "medium",
    },
    "conflict_detection": {
        "rhythm_mismatch_threshold_days": 3.0,
        "rhythm_mismatch_ratio": 0.5,
        "consecutive_deviation_threshold": 3,
        "humidity_deviation_percent": 20,
        "prediction_window_overlap_hours": 6,
    },
    "priority_rules": {
        "critical_risk_threshold": 80,
        "high_risk_threshold": 50,
        "medium_risk_threshold": 20,
        "days_until_watering_critical": 0.5,
        "days_until_watering_high": 1.0,
        "days_until_watering_medium": 2.0,
    },
    "risk_assessment": {
        "rot_risk_moisture_threshold": 80,
        "rot_risk_days_after_watering": 2,
        "drought_risk_moisture_threshold": 15,
        "drought_risk_interval_multiplier": 1.5,
    },
    "adaptation_suggestions": {
        "min_conflict_severity": "medium",
        "max_suggestions_per_conflict": 3,
    },
    "reminder_orchestration": {
        "default_advance_hours": 24,
        "critical_advance_hours": 48,
        "high_advance_hours": 24,
        "medium_advance_hours": 12,
        "low_advance_hours": 6,
        "max_reminders_per_zone": 50,
        "send_batch_summary": True,
        "batch_summary_advance_hours": 2,
        "channels": {
            "app_push": {
                "enabled": True,
                "max_daily_limit": 10,
                "priority_threshold": "medium",
            },
            "email": {
                "enabled": True,
                "max_daily_limit": 5,
                "priority_threshold": "high",
            },
            "sms": {
                "enabled": False,
                "max_daily_limit": 3,
                "priority_threshold": "critical",
            },
            "wechat": {
                "enabled": False,
                "max_daily_limit": 10,
                "priority_threshold": "medium",
            },
        },
        "reminder_templates": {
            "critical": {
                "title": "紧急浇水提醒",
                "message_template": "{plant_name}需要立即浇水！已逾期{overdue_hours:.0f}小时",
                "urgency": "urgent",
            },
            "high": {
                "title": "重要浇水提醒",
                "message_template": "{plant_name}明天需要浇水，请在{window_start}至{window_end}之间完成",
                "urgency": "high",
            },
            "medium": {
                "title": "浇水提醒",
                "message_template": "{plant_name}近期需要浇水，建议在{date}前后完成",
                "urgency": "normal",
            },
            "low": {
                "title": "浇水计划",
                "message_template": "{plant_name}预计{date}需要浇水",
                "urgency": "low",
            },
            "batch_summary": {
                "title": "{zone_name}今日浇水计划",
                "message_template": "今天共有{task_count}株植物需要浇水，其中紧急{critical_count}株，重要{high_count}株。建议{suggested_time}开始浇水。",
                "urgency": "normal",
            },
            "conflict_alert": {
                "title": "{zone_name}养护冲突提醒",
                "message_template": "检测到{conflict_count}个养护冲突，建议尽快处理以保障植物健康。",
                "urgency": "high",
            },
        },
        "smart_scheduling": {
            "enabled": True,
            "preferred_time_start": 8,
            "preferred_time_end": 10,
            "avoid_meal_times": True,
            "meal_times": [[7, 9], [12, 14], [18, 20]],
            "weather_aware": True,
            "rain_delay_hours": 24,
        },
        "escalation_rules": {
            "enabled": True,
            "overdue_hours_critical": 6,
            "overdue_hours_high": 12,
            "overdue_hours_medium": 24,
            "escalation_channels": ["app_push", "email"],
            "max_escalation_levels": 3,
        },
    },
}


def get_zone_type_display(zone_type: ZoneType) -> str:
    return ZONE_TYPE_DISPLAY.get(zone_type, "未知区域")


def get_default_environment(zone_type: ZoneType) -> Dict:
    return ZONE_TYPE_DEFAULT_ENVIRONMENT.get(zone_type, ZONE_TYPE_DEFAULT_ENVIRONMENT[ZoneType.OTHER])


def get_suggested_plants_for_zone(zone_type: ZoneType, light_level: Optional[LightLevel] = None) -> List[str]:
    zone_plants = set(ZONE_TYPE_SUGGESTED_PLANTS.get(zone_type, []))
    if light_level:
        light_plants = set(LIGHT_LEVEL_SUGGESTED_PLANTS.get(light_level, []))
        return list(zone_plants.intersection(light_plants)) or list(zone_plants)
    return list(zone_plants)


def get_schedule_rule(rule_path: str, default=None):
    keys = rule_path.split(".")
    value = SCHEDULE_RULES
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value
