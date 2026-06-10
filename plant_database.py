from typing import Dict, Optional
from datetime import datetime


PLANT_DATABASE: Dict[str, Dict] = {
    "succulent": {
        "name": "多肉植物",
        "base_watering_interval_days": 10,
        "optimal_temp_min": 15,
        "optimal_temp_max": 28,
        "optimal_humidity_min": 30,
        "optimal_humidity_max": 50,
        "water_sensitivity": 0.3,
        "drought_tolerance": 0.9,
        "rot_resistance": 0.2,
        "light_preference": "high",
        "seasonal_adjustment": {
            "spring": 0.9,
            "summer": 0.6,
            "autumn": 0.9,
            "winter": 1.4
        }
    },
    "cactus": {
        "name": "仙人掌",
        "base_watering_interval_days": 14,
        "optimal_temp_min": 18,
        "optimal_temp_max": 35,
        "optimal_humidity_min": 20,
        "optimal_humidity_max": 40,
        "water_sensitivity": 0.2,
        "drought_tolerance": 0.95,
        "rot_resistance": 0.15,
        "light_preference": "high",
        "seasonal_adjustment": {
            "spring": 0.9,
            "summer": 0.5,
            "autumn": 0.9,
            "winter": 1.5
        }
    },
    "monstera": {
        "name": "龟背竹",
        "base_watering_interval_days": 5,
        "optimal_temp_min": 20,
        "optimal_temp_max": 30,
        "optimal_humidity_min": 60,
        "optimal_humidity_max": 80,
        "water_sensitivity": 0.7,
        "drought_tolerance": 0.4,
        "rot_resistance": 0.5,
        "light_preference": "medium",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.7,
            "autumn": 1.0,
            "winter": 1.3
        }
    },
    "pothos": {
        "name": "绿萝",
        "base_watering_interval_days": 4,
        "optimal_temp_min": 18,
        "optimal_temp_max": 28,
        "optimal_humidity_min": 50,
        "optimal_humidity_max": 70,
        "water_sensitivity": 0.6,
        "drought_tolerance": 0.5,
        "rot_resistance": 0.6,
        "light_preference": "low",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.75,
            "autumn": 1.0,
            "winter": 1.25
        }
    },
    "snake_plant": {
        "name": "虎皮兰",
        "base_watering_interval_days": 7,
        "optimal_temp_min": 15,
        "optimal_temp_max": 30,
        "optimal_humidity_min": 40,
        "optimal_humidity_max": 60,
        "water_sensitivity": 0.4,
        "drought_tolerance": 0.85,
        "rot_resistance": 0.3,
        "light_preference": "medium",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.8,
            "autumn": 1.0,
            "winter": 1.3
        }
    },
    "peace_lily": {
        "name": "白掌",
        "base_watering_interval_days": 3,
        "optimal_temp_min": 18,
        "optimal_temp_max": 28,
        "optimal_humidity_min": 60,
        "optimal_humidity_max": 85,
        "water_sensitivity": 0.8,
        "drought_tolerance": 0.3,
        "rot_resistance": 0.4,
        "light_preference": "low",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.7,
            "autumn": 1.0,
            "winter": 1.2
        }
    },
    "fern": {
        "name": "蕨类植物",
        "base_watering_interval_days": 2,
        "optimal_temp_min": 16,
        "optimal_temp_max": 25,
        "optimal_humidity_min": 70,
        "optimal_humidity_max": 90,
        "water_sensitivity": 0.9,
        "drought_tolerance": 0.2,
        "rot_resistance": 0.6,
        "light_preference": "low",
        "seasonal_adjustment": {
            "spring": 0.9,
            "summer": 0.6,
            "autumn": 0.9,
            "winter": 1.2
        }
    },
    "orchid": {
        "name": "兰花",
        "base_watering_interval_days": 5,
        "optimal_temp_min": 18,
        "optimal_temp_max": 28,
        "optimal_humidity_min": 50,
        "optimal_humidity_max": 75,
        "water_sensitivity": 0.7,
        "drought_tolerance": 0.4,
        "rot_resistance": 0.3,
        "light_preference": "medium",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.7,
            "autumn": 1.0,
            "winter": 1.3
        }
    },
    "spider_plant": {
        "name": "吊兰",
        "base_watering_interval_days": 4,
        "optimal_temp_min": 15,
        "optimal_temp_max": 25,
        "optimal_humidity_min": 50,
        "optimal_humidity_max": 70,
        "water_sensitivity": 0.6,
        "drought_tolerance": 0.5,
        "rot_resistance": 0.5,
        "light_preference": "medium",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.75,
            "autumn": 1.0,
            "winter": 1.2
        }
    },
    "rubber_plant": {
        "name": "橡皮树",
        "base_watering_interval_days": 6,
        "optimal_temp_min": 16,
        "optimal_temp_max": 28,
        "optimal_humidity_min": 40,
        "optimal_humidity_max": 60,
        "water_sensitivity": 0.5,
        "drought_tolerance": 0.7,
        "rot_resistance": 0.4,
        "light_preference": "medium",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.8,
            "autumn": 1.0,
            "winter": 1.25
        }
    },
    "fiddle_leaf_fig": {
        "name": "琴叶榕",
        "base_watering_interval_days": 5,
        "optimal_temp_min": 18,
        "optimal_temp_max": 28,
        "optimal_humidity_min": 50,
        "optimal_humidity_max": 70,
        "water_sensitivity": 0.7,
        "drought_tolerance": 0.4,
        "rot_resistance": 0.4,
        "light_preference": "bright",
        "seasonal_adjustment": {
            "spring": 1.0,
            "summer": 0.75,
            "autumn": 1.0,
            "winter": 1.3
        }
    },
    "bonsai": {
        "name": "盆景",
        "base_watering_interval_days": 3,
        "optimal_temp_min": 15,
        "optimal_temp_max": 25,
        "optimal_humidity_min": 50,
        "optimal_humidity_max": 70,
        "water_sensitivity": 0.8,
        "drought_tolerance": 0.3,
        "rot_resistance": 0.4,
        "light_preference": "medium",
        "seasonal_adjustment": {
            "spring": 0.9,
            "summer": 0.65,
            "autumn": 0.9,
            "winter": 1.25
        }
    }
}


POT_MATERIAL_EVAPORATION: Dict[str, float] = {
    "clay": 1.3,
    "ceramic": 0.8,
    "plastic": 0.6,
    "metal": 0.7,
    "glass": 0.5,
    "terracotta": 1.4
}


SOIL_TYPE_WATER_RETENTION: Dict[str, float] = {
    "peat": 0.9,
    "loam": 0.7,
    "coco": 0.8,
    "clay": 0.85,
    "sand": 0.4,
    "sandy_loam": 0.5
}


def get_plant_info(species: str) -> Optional[Dict]:
    species_lower = species.lower()
    if species_lower in PLANT_DATABASE:
        return PLANT_DATABASE[species_lower]
    
    for key, info in PLANT_DATABASE.items():
        if key in species_lower or info["name"] in species:
            return info
    
    return None


def get_pot_evaporation_coefficient(material: str) -> float:
    return POT_MATERIAL_EVAPORATION.get(material.lower(), 0.8)


def get_soil_retention_coefficient(soil_type: str) -> float:
    return SOIL_TYPE_WATER_RETENTION.get(soil_type.lower(), 0.7)


def get_season(date: Optional[datetime] = None) -> str:
    if date is None:
        date = datetime.now()
    month = date.month
    
    if month in [3, 4, 5]:
        return "spring"
    elif month in [6, 7, 8]:
        return "summer"
    elif month in [9, 10, 11]:
        return "autumn"
    else:
        return "winter"
