from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
import uuid
import statistics

from models.zone import Zone
from models.schedule import (
    PlantWateringTask, BatchWateringGroup, ScheduleDay,
    SchedulePriority, WateringStatus, WateringScheduleResponse
)
from models import Plant
from watering_engine import WateringEngine
from plant_database import get_plant_info
from data.zone_rules import get_schedule_rule


class ScheduleService:
    def __init__(self, watering_engine: WateringEngine, conflict_service=None):
        self.watering_engine = watering_engine
        self.conflict_service = conflict_service
        self.cached_schedules: Dict[str, Tuple[WateringScheduleResponse, datetime]] = {}

    def _get_priority(self, days_until: float, risk_level: str) -> SchedulePriority:
        if days_until <= 0.5 or risk_level == "high":
            return SchedulePriority.CRITICAL
        elif days_until <= 1.0 or risk_level == "medium":
            return SchedulePriority.HIGH
        elif days_until <= 2.0:
            return SchedulePriority.MEDIUM
        else:
            return SchedulePriority.LOW

    def _get_risk_level(
        self,
        plant: Plant,
        last_report,
        prediction
    ) -> str:
        return self._assess_plant_risks(plant, last_report, prediction)["level"]

    def _assess_plant_risks(
        self,
        plant: Plant,
        last_report,
        prediction
    ) -> Dict[str, Any]:
        plant_info = get_plant_info(plant.species)
        if not plant_info:
            return {
                "level": "low",
                "score": 0,
                "rot_risk": 0.0,
                "drought_risk": 0.0,
                "rot_risk_details": None,
                "drought_risk_details": None
            }

        days_since = (last_report.report_time - last_report.last_watering_time).total_seconds() / 86400
        risk_score = 0
        rot_risk_value = 0.0
        drought_risk_value = 0.0
        rot_risk_details = None
        drought_risk_details = None

        rot_threshold = get_schedule_rule("risk_assessment.rot_risk_moisture_threshold", 80)
        rot_days_threshold = get_schedule_rule("risk_assessment.rot_risk_days_after_watering", 2)
        drought_threshold = get_schedule_rule("risk_assessment.drought_risk_moisture_threshold", 15)
        drought_interval_multiplier = get_schedule_rule("risk_assessment.drought_risk_interval_multiplier", 1.5)

        if last_report.soil_moisture is not None:
            if last_report.soil_moisture > rot_threshold and days_since < rot_days_threshold:
                rot_risk_value = 1.0 - plant_info["rot_resistance"]
                rot_risk_details = {
                    "soil_moisture": last_report.soil_moisture,
                    "days_since_watering": round(days_since, 1),
                    "rot_resistance": plant_info["rot_resistance"],
                    "risk_value": round(rot_risk_value, 2),
                    "threshold_moisture": rot_threshold,
                    "threshold_days": rot_days_threshold
                }
                if rot_risk_value > 0.7:
                    risk_score += 50
                elif rot_risk_value > 0.5:
                    risk_score += 30

            if last_report.soil_moisture < drought_threshold:
                drought_risk_value = 1.0 - plant_info["drought_tolerance"]
                base_interval = plant_info["base_watering_interval_days"]
                drought_risk_details = {
                    "soil_moisture": last_report.soil_moisture,
                    "days_since_watering": round(days_since, 1),
                    "drought_tolerance": plant_info["drought_tolerance"],
                    "risk_value": round(drought_risk_value, 2),
                    "base_watering_interval": base_interval,
                    "threshold_moisture": drought_threshold,
                    "is_overdue": days_since > base_interval * drought_interval_multiplier
                }
                if drought_risk_value > 0.6 or days_since > base_interval * drought_interval_multiplier:
                    risk_score += 50
                elif drought_risk_value > 0.3:
                    risk_score += 25

        if days_since > prediction.avg_watering_interval * 2:
            risk_score += 30
        elif days_since > prediction.avg_watering_interval * 1.3:
            risk_score += 15

        if prediction.adaptation_score < 60:
            risk_score += 20

        if risk_score >= 80:
            level = "high"
        elif risk_score >= 50:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "score": risk_score,
            "rot_risk": round(rot_risk_value, 2),
            "drought_risk": round(drought_risk_value, 2),
            "rot_risk_details": rot_risk_details,
            "drought_risk_details": drought_risk_details,
            "adaptation_score": prediction.adaptation_score,
            "days_since_watering": round(days_since, 2)
        }

    def _generate_plant_tasks(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant],
        days_ahead: int,
        start_date: date
    ) -> List[PlantWateringTask]:
        tasks: List[PlantWateringTask] = []

        for plant_id in zone.plant_ids:
            plant = plants_db.get(plant_id)
            if not plant:
                continue

            history = self.watering_engine.get_plant_history(plant_id)
            if not history:
                continue

            last_report = history[-1]

            try:
                prediction = self.watering_engine.predict_watering(
                    plant_id=plant_id,
                    plant_species=plant.species,
                    pot_material=plant.pot_material,
                    soil_type=plant.soil_type,
                    last_report=last_report
                )
            except ValueError:
                continue

            risk_assessment = self._assess_plant_risks(plant, last_report, prediction)
            avg_interval = prediction.avg_watering_interval
            base_watering_date = last_report.last_watering_time.date()
            days_since_last = (start_date - base_watering_date).days

            next_watering_day = max(0, int(avg_interval - days_since_last))
            current_date = start_date + timedelta(days=next_watering_day)

            watering_count = 0
            max_waterings = days_ahead // max(1, int(avg_interval)) + 1

            while watering_count < max_waterings and current_date < start_date + timedelta(days=days_ahead):
                days_until = (current_date - date.today()).total_seconds() / 86400
                risk_level = risk_assessment["level"]
                priority = self._get_priority(days_until, risk_level)

                predicted_datetime = datetime.combine(current_date, datetime.min.time()) + timedelta(hours=9)
                window_hours = max(6, int(avg_interval * 24 * 0.1))

                plant_info = get_plant_info(plant.species)
                water_amount = None
                if plant_info:
                    base_interval = plant_info["base_watering_interval_days"]
                    water_amount = round(200 * (base_interval / avg_interval), 0)

                status = WateringStatus.PENDING
                if current_date < date.today():
                    status = WateringStatus.OVERDUE
                elif current_date == date.today() and datetime.now().hour > 12:
                    status = WateringStatus.OVERDUE

                notes_parts = []
                if risk_assessment["rot_risk"] > 0.5:
                    notes_parts.append(f"烂根风险高({risk_assessment['rot_risk']:.0%})，注意控制浇水量")
                if risk_assessment["drought_risk"] > 0.5:
                    notes_parts.append(f"干旱风险高({risk_assessment['drought_risk']:.0%})，需及时浇水")
                if risk_assessment["adaptation_score"] < 60:
                    notes_parts.append(f"环境适配度低({risk_assessment['adaptation_score']:.0f}分)，建议改善养护条件")

                task = PlantWateringTask(
                    plant_id=plant_id,
                    plant_name=plant.name,
                    species=plant.species,
                    scheduled_date=current_date,
                    scheduled_time_start=predicted_datetime - timedelta(hours=window_hours),
                    scheduled_time_end=predicted_datetime + timedelta(hours=window_hours),
                    priority=priority,
                    water_amount_ml=water_amount,
                    status=status,
                    predicted_next_watering=prediction.predicted_next_watering,
                    days_until_watering=round(days_until, 2),
                    risk_level=risk_level,
                    notes="; ".join(notes_parts) if notes_parts else None
                )
                tasks.append(task)

                current_date += timedelta(days=int(avg_interval))
                watering_count += 1

        tasks.sort(key=lambda t: (t.scheduled_date, t.priority.value))
        return tasks

    def _generate_batch_groups(
        self,
        tasks_by_date: Dict[date, List[PlantWateringTask]],
        zone_name: str
    ) -> Dict[date, List[BatchWateringGroup]]:
        groups_by_date: Dict[date, List[BatchWateringGroup]] = {}
        max_plants_per_group = get_schedule_rule("batch_watering.max_plants_per_group", 10)
        max_window_hours = get_schedule_rule("batch_watering.max_time_window_hours", 4)

        priority_order = ["critical", "high", "medium", "low"]

        for schedule_date, tasks in tasks_by_date.items():
            groups: List[BatchWateringGroup] = []

            for priority in priority_order:
                priority_tasks = [t for t in tasks if t.priority.value == priority]
                if not priority_tasks:
                    continue

                for i in range(0, len(priority_tasks), max_plants_per_group):
                    group_tasks = priority_tasks[i:i + max_plants_per_group]
                    plant_ids = [t.plant_id for t in group_tasks]
                    plant_names = [t.plant_name for t in group_tasks]
                    total_water = sum(t.water_amount_ml or 0 for t in group_tasks)

                    group = BatchWateringGroup(
                        group_id=str(uuid.uuid4()),
                        scheduled_date=schedule_date,
                        plant_ids=plant_ids,
                        plant_names=plant_names,
                        total_plants=len(group_tasks),
                        priority=SchedulePriority(priority),
                        suggested_time=f"09:00-{(9 + max_window_hours) % 24:02d}:00",
                        water_amount_total_ml=total_water if total_water > 0 else None,
                        notes=f"{zone_name} - {len(group_tasks)}株植物批量浇水"
                    )
                    groups.append(group)

            groups_by_date[schedule_date] = groups

        return groups_by_date

    def generate_schedule(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant],
        days_ahead: int = 7,
        include_conflicts: bool = True
    ) -> Optional[WateringScheduleResponse]:
        cache_key = f"{zone.id}_{days_ahead}_{include_conflicts}"
        if cache_key in self.cached_schedules:
            cached_response, cached_time = self.cached_schedules[cache_key]
            if (datetime.now() - cached_time).total_seconds() < 3600:
                return cached_response

        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead - 1)

        all_tasks = self._generate_plant_tasks(zone, plants_db, days_ahead, start_date)

        tasks_by_date: Dict[date, List[PlantWateringTask]] = {}
        for d in range(days_ahead):
            current_date = start_date + timedelta(days=d)
            tasks_by_date[current_date] = []

        for task in all_tasks:
            if task.scheduled_date in tasks_by_date:
                tasks_by_date[task.scheduled_date].append(task)

        batch_groups_by_date = self._generate_batch_groups(tasks_by_date, zone.name)

        schedule_days: List[ScheduleDay] = []
        priority_summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        total_tasks = 0
        total_batches = 0

        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for d in range(days_ahead):
            current_date = start_date + timedelta(days=d)
            day_tasks = tasks_by_date[current_date]
            day_groups = batch_groups_by_date.get(current_date, [])

            critical_count = sum(1 for t in day_tasks if t.priority == SchedulePriority.CRITICAL)
            high_count = sum(1 for t in day_tasks if t.priority == SchedulePriority.HIGH)
            medium_count = sum(1 for t in day_tasks if t.priority == SchedulePriority.MEDIUM)
            low_count = sum(1 for t in day_tasks if t.priority == SchedulePriority.LOW)

            priority_summary["critical"] += critical_count
            priority_summary["high"] += high_count
            priority_summary["medium"] += medium_count
            priority_summary["low"] += low_count
            total_tasks += len(day_tasks)
            total_batches += len(day_groups)

            schedule_day = ScheduleDay(
                date=current_date,
                day_of_week=weekday_names[current_date.weekday()],
                is_today=(current_date == date.today()),
                total_tasks=len(day_tasks),
                critical_count=critical_count,
                high_count=high_count,
                medium_count=medium_count,
                low_count=low_count,
                tasks=day_tasks,
                batch_groups=day_groups
            )
            schedule_days.append(schedule_day)

        conflicts_count = 0
        if include_conflicts and self.conflict_service:
            try:
                conflict_analysis = self.conflict_service.analyze_conflicts(zone, plants_db)
                if conflict_analysis:
                    conflicts_count = conflict_analysis.total_conflicts
            except Exception:
                pass

        response = WateringScheduleResponse(
            zone_id=zone.id,
            zone_name=zone.name,
            schedule_days=days_ahead,
            start_date=start_date,
            end_date=end_date,
            generated_at=datetime.now(),
            total_tasks=total_tasks,
            batch_groups_count=total_batches,
            conflicts_count=conflicts_count,
            schedule=schedule_days,
            priority_summary=priority_summary
        )

        self.cached_schedules[cache_key] = (response, datetime.now())
        return response

    def get_plant_tasks_for_date(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant],
        target_date: date
    ) -> List[PlantWateringTask]:
        schedule = self.generate_schedule(zone, plants_db, 30)
        if not schedule:
            return []

        for day in schedule.schedule:
            if day.date == target_date:
                return day.tasks
        return []

    def get_upcoming_tasks(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant],
        hours_ahead: int = 48
    ) -> List[PlantWateringTask]:
        schedule = self.generate_schedule(zone, plants_db, 7)
        if not schedule:
            return []

        now = datetime.now()
        cutoff = now + timedelta(hours=hours_ahead)
        upcoming = []

        for day in schedule.schedule:
            for task in day.tasks:
                if task.scheduled_time_start:
                    task_start = task.scheduled_time_start
                    if now <= task_start <= cutoff:
                        upcoming.append(task)

        upcoming.sort(key=lambda t: t.scheduled_time_start or datetime.max)
        return upcoming

    def invalidate_cache(self, zone_id: Optional[str] = None):
        if zone_id:
            keys_to_remove = [k for k in self.cached_schedules if k.startswith(f"{zone_id}_")]
            for k in keys_to_remove:
                del self.cached_schedules[k]
        else:
            self.cached_schedules.clear()
