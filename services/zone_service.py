from datetime import datetime
from typing import Dict, List, Optional, Tuple
import uuid
import statistics

from models.zone import (
    Zone, ZoneCreate, ZoneUpdate, ZoneEnvironment,
    ZoneRiskAssessment, ZoneSummary, ZoneType
)
from models import Plant, WateringReport
from watering_engine import WateringEngine
from plant_database import get_plant_info
from data.zone_rules import get_default_environment, get_suggested_plants_for_zone


class ZoneService:
    def __init__(self, watering_engine: WateringEngine):
        self.zones_db: Dict[str, Zone] = {}
        self.watering_engine = watering_engine

    def create_zone(self, zone_create: ZoneCreate) -> Zone:
        zone_id = str(uuid.uuid4())
        now = datetime.now()

        environment = zone_create.environment
        if environment is None:
            default_env = get_default_environment(zone_create.zone_type)
            environment = ZoneEnvironment(**default_env)

        zone = Zone(
            id=zone_id,
            name=zone_create.name,
            zone_type=zone_create.zone_type,
            description=zone_create.description,
            environment=environment,
            plant_ids=[],
            created_at=now,
            updated_at=now
        )

        self.zones_db[zone_id] = zone
        return zone

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        return self.zones_db.get(zone_id)

    def get_all_zones(self) -> List[Zone]:
        return list(self.zones_db.values())

    def update_zone(self, zone_id: str, zone_update: ZoneUpdate) -> Optional[Zone]:
        zone = self.zones_db.get(zone_id)
        if not zone:
            return None

        update_data = zone_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(zone, key, value)

        zone.updated_at = datetime.now()
        return zone

    def delete_zone(self, zone_id: str) -> bool:
        if zone_id in self.zones_db:
            del self.zones_db[zone_id]
            return True
        return False

    def bind_plants(self, zone_id: str, plant_ids: List[str], plants_db: Dict[str, Plant]) -> Tuple[Optional[Zone], List[str], List[str]]:
        zone = self.zones_db.get(zone_id)
        if not zone:
            return None, [], plant_ids

        success_ids = []
        failed_ids = []

        for plant_id in plant_ids:
            if plant_id not in plants_db:
                failed_ids.append(plant_id)
                continue

            if plant_id in zone.plant_ids:
                failed_ids.append(plant_id)
                continue

            for existing_zone in self.zones_db.values():
                if plant_id in existing_zone.plant_ids and existing_zone.id != zone_id:
                    existing_zone.plant_ids.remove(plant_id)
                    existing_zone.updated_at = datetime.now()

            zone.plant_ids.append(plant_id)
            success_ids.append(plant_id)

        if success_ids:
            zone.updated_at = datetime.now()

        return zone, success_ids, failed_ids

    def unbind_plants(self, zone_id: str, plant_ids: List[str]) -> Tuple[Optional[Zone], List[str], List[str]]:
        zone = self.zones_db.get(zone_id)
        if not zone:
            return None, [], plant_ids

        success_ids = []
        failed_ids = []

        for plant_id in plant_ids:
            if plant_id not in zone.plant_ids:
                failed_ids.append(plant_id)
                continue

            zone.plant_ids.remove(plant_id)
            success_ids.append(plant_id)

        if success_ids:
            zone.updated_at = datetime.now()

        return zone, success_ids, failed_ids

    def get_zone_plants(self, zone_id: str, plants_db: Dict[str, Plant]) -> Tuple[Optional[Zone], List[Plant]]:
        zone = self.zones_db.get(zone_id)
        if not zone:
            return None, []

        plants = [plants_db[pid] for pid in zone.plant_ids if pid in plants_db]
        return zone, plants

    def get_plant_zone(self, plant_id: str) -> Optional[Zone]:
        for zone in self.zones_db.values():
            if plant_id in zone.plant_ids:
                return zone
        return None

    def get_zone_summaries(self, plants_db: Dict[str, Plant]) -> List[ZoneSummary]:
        summaries = []
        for zone in self.zones_db.values():
            summary = ZoneSummary(
                id=zone.id,
                name=zone.name,
                zone_type=zone.zone_type,
                plant_count=len([pid for pid in zone.plant_ids if pid in plants_db]),
                environment=zone.environment,
                last_updated=zone.updated_at
            )
            summaries.append(summary)
        return summaries

    def analyze_zone_watering_patterns(
        self,
        zone_id: str,
        plants_db: Dict[str, Plant]
    ) -> Optional[Dict]:
        zone = self.zones_db.get(zone_id)
        if not zone:
            return None

        plant_patterns = []
        intervals = []

        for plant_id in zone.plant_ids:
            plant = plants_db.get(plant_id)
            if not plant:
                continue

            history = self.watering_engine.get_plant_history(plant_id)
            if len(history) < 2:
                plant_patterns.append({
                    "plant_id": plant_id,
                    "plant_name": plant.name,
                    "avg_interval_days": 0,
                    "std_deviation_days": 0,
                    "consistency_score": 0,
                    "early_watering_count": 0,
                    "late_watering_count": 0,
                    "consecutive_early_count": 0,
                    "consecutive_late_count": 0,
                    "pattern_status": "insufficient_data"
                })
                continue

            reported_intervals = []
            for i in range(1, len(history)):
                interval = (history[i].last_watering_time - history[i-1].last_watering_time).total_seconds() / 86400
                if 0.5 <= interval <= 60:
                    reported_intervals.append(interval)

            if not reported_intervals:
                continue

            avg_interval = statistics.mean(reported_intervals)
            std_dev = statistics.stdev(reported_intervals) if len(reported_intervals) > 1 else 0
            consistency_score = max(0, 100 - std_dev * 10)

            base_interval = self.watering_engine.calculate_average_interval(plant_id, plant.species)
            early_count = sum(1 for x in reported_intervals if x < base_interval * 0.8)
            late_count = sum(1 for x in reported_intervals if x > base_interval * 1.2)

            consecutive_early = 0
            consecutive_late = 0
            max_early = 0
            max_late = 0

            for interval in reported_intervals:
                if interval < base_interval * 0.8:
                    consecutive_early += 1
                    consecutive_late = 0
                    max_early = max(max_early, consecutive_early)
                elif interval > base_interval * 1.2:
                    consecutive_late += 1
                    consecutive_early = 0
                    max_late = max(max_late, consecutive_late)
                else:
                    consecutive_early = 0
                    consecutive_late = 0

            pattern_status = "normal"
            if consistency_score < 50:
                pattern_status = "irregular"
            elif max_early >= 3:
                pattern_status = "consistently_early"
            elif max_late >= 3:
                pattern_status = "consistently_late"

            plant_patterns.append({
                "plant_id": plant_id,
                "plant_name": plant.name,
                "avg_interval_days": round(avg_interval, 2),
                "std_deviation_days": round(std_dev, 2),
                "consistency_score": round(consistency_score, 2),
                "early_watering_count": early_count,
                "late_watering_count": late_count,
                "consecutive_early_count": max_early,
                "consecutive_late_count": max_late,
                "pattern_status": pattern_status
            })

            intervals.append(avg_interval)

        if not intervals:
            return {
                "zone_id": zone_id,
                "zone_name": zone.name,
                "total_plants": len(zone.plant_ids),
                "avg_watering_interval": 0,
                "interval_variance": 0,
                "rhythm_diversity_score": 0,
                "min_interval": 0,
                "max_interval": 0,
                "plant_patterns": plant_patterns
            }

        avg_interval = statistics.mean(intervals)
        variance = statistics.variance(intervals) if len(intervals) > 1 else 0
        min_interval = min(intervals)
        max_interval = max(intervals)

        rhythm_range = max_interval - min_interval
        diversity_score = max(0, 100 - rhythm_range * 10)

        return {
            "zone_id": zone_id,
            "zone_name": zone.name,
            "total_plants": len(zone.plant_ids),
            "avg_watering_interval": round(avg_interval, 2),
            "interval_variance": round(variance, 2),
            "rhythm_diversity_score": round(diversity_score, 2),
            "min_interval": round(min_interval, 2),
            "max_interval": round(max_interval, 2),
            "plant_patterns": plant_patterns
        }

    def assess_zone_risks(
        self,
        zone_id: str,
        plants_db: Dict[str, Plant]
    ) -> Optional[ZoneRiskAssessment]:
        zone = self.zones_db.get(zone_id)
        if not zone:
            return None

        rot_risk_count = 0
        drought_risk_count = 0
        conflict_count = 0
        adaptation_scores = []
        risk_details = []

        for plant_id in zone.plant_ids:
            plant = plants_db.get(plant_id)
            if not plant:
                continue

            history = self.watering_engine.get_plant_history(plant_id)
            if not history:
                continue

            last_report = history[-1]
            plant_info = get_plant_info(plant.species)

            try:
                prediction = self.watering_engine.predict_watering(
                    plant_id=plant_id,
                    plant_species=plant.species,
                    pot_material=plant.pot_material,
                    soil_type=plant.soil_type,
                    last_report=last_report
                )
                adaptation_scores.append(prediction.adaptation_score)
            except ValueError:
                continue

            days_since_watering = (last_report.report_time - last_report.last_watering_time).total_seconds() / 86400

            if plant_info and last_report.soil_moisture is not None:
                if last_report.soil_moisture > 80 and days_since_watering < 2:
                    rot_risk = 1.0 - plant_info["rot_resistance"]
                    if rot_risk > 0.5:
                        rot_risk_count += 1
                        risk_details.append({
                            "plant_id": plant_id,
                            "plant_name": plant.name,
                            "risk_type": "root_rot",
                            "severity": "high" if rot_risk > 0.7 else "medium",
                            "soil_moisture": last_report.soil_moisture,
                            "days_since_watering": round(days_since_watering, 1)
                        })

                if last_report.soil_moisture < 15:
                    drought_risk = 1.0 - plant_info["drought_tolerance"]
                    if drought_risk > 0.3 or days_since_watering > plant_info["base_watering_interval_days"] * 1.5:
                        drought_risk_count += 1
                        risk_details.append({
                            "plant_id": plant_id,
                            "plant_name": plant.name,
                            "risk_type": "drought",
                            "severity": "high" if drought_risk > 0.6 else "medium",
                            "soil_moisture": last_report.soil_moisture,
                            "days_since_watering": round(days_since_watering, 1)
                        })

        overall_risk = "low"
        if rot_risk_count + drought_risk_count > len(zone.plant_ids) * 0.5:
            overall_risk = "high"
        elif rot_risk_count + drought_risk_count > 0:
            overall_risk = "medium"

        avg_adaptation = statistics.mean(adaptation_scores) if adaptation_scores else 0.0

        return ZoneRiskAssessment(
            zone_id=zone_id,
            zone_name=zone.name,
            overall_risk_level=overall_risk,
            rot_risk_count=rot_risk_count,
            drought_risk_count=drought_risk_count,
            conflict_count=conflict_count,
            avg_adaptation_score=round(avg_adaptation, 2),
            risk_details=risk_details
        )

    def get_suggested_plants(self, zone_type: ZoneType) -> List[str]:
        return get_suggested_plants_for_zone(zone_type)
