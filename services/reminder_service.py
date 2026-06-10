from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import uuid
import statistics

from models.zone import Zone
from models.schedule import (
    Reminder, ReminderChannel, ReminderStatus,
    ReminderConfig, ReminderGenerateRequest, ReminderListResponse,
    SchedulePriority, PlantWateringTask, WateringScheduleResponse
)
from models import Plant
from watering_engine import WateringEngine
from data.zone_rules import get_schedule_rule


class ReminderService:
    def __init__(self, watering_engine: WateringEngine):
        self.watering_engine = watering_engine
        self.reminders_db: Dict[str, Reminder] = {}
        self.daily_channel_counts: Dict[str, Dict[str, int]] = {}

    def _get_priority_advance_hours(self, priority: SchedulePriority) -> int:
        priority_map = {
            SchedulePriority.CRITICAL: get_schedule_rule("reminder_orchestration.critical_advance_hours", 48),
            SchedulePriority.HIGH: get_schedule_rule("reminder_orchestration.high_advance_hours", 24),
            SchedulePriority.MEDIUM: get_schedule_rule("reminder_orchestration.medium_advance_hours", 12),
            SchedulePriority.LOW: get_schedule_rule("reminder_orchestration.low_advance_hours", 6),
        }
        return priority_map.get(priority, 24)

    def _get_channel_priority_threshold(self, channel: ReminderChannel) -> str:
        channel_config = get_schedule_rule(f"reminder_orchestration.channels.{channel.value}", {})
        return channel_config.get("priority_threshold", "medium")

    def _is_channel_enabled(self, channel: ReminderChannel) -> bool:
        channel_config = get_schedule_rule(f"reminder_orchestration.channels.{channel.value}", {})
        return channel_config.get("enabled", False)

    def _get_channel_daily_limit(self, channel: ReminderChannel) -> int:
        channel_config = get_schedule_rule(f"reminder_orchestration.channels.{channel.value}", {})
        return channel_config.get("max_daily_limit", 10)

    def _get_reminder_template(self, priority: str) -> Dict:
        templates = get_schedule_rule("reminder_orchestration.reminder_templates", {})
        return templates.get(priority, {})

    def _check_priority_meets_threshold(self, task_priority: SchedulePriority, threshold: str) -> bool:
        priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        task_value = priority_order.get(task_priority.value, 0)
        threshold_value = priority_order.get(threshold, 0)
        return task_value >= threshold_value

    def _render_template(self, template: str, context: Dict) -> str:
        try:
            return template.format(**context)
        except Exception:
            return template

    def _calculate_optimal_reminder_time(
        self,
        task: PlantWateringTask,
        advance_hours: int
    ) -> datetime:
        smart_scheduling = get_schedule_rule("reminder_orchestration.smart_scheduling", {})
        preferred_start = smart_scheduling.get("preferred_time_start", 8)
        preferred_end = smart_scheduling.get("preferred_time_end", 10)
        avoid_meals = smart_scheduling.get("avoid_meal_times", True)
        meal_times = smart_scheduling.get("meal_times", [[7, 9], [12, 14], [18, 20]])

        base_time = task.scheduled_time_start or datetime.combine(task.scheduled_date, datetime.min.time())
        reminder_time = base_time - timedelta(hours=advance_hours)

        if smart_scheduling.get("enabled", True):
            reminder_hour = reminder_time.hour
            if reminder_hour < preferred_start:
                reminder_time = reminder_time.replace(hour=preferred_start, minute=0)
            elif reminder_hour > preferred_end:
                reminder_time = reminder_time.replace(hour=preferred_end, minute=0)

            if avoid_meals:
                for meal_start, meal_end in meal_times:
                    if meal_start <= reminder_time.hour < meal_end:
                        reminder_time = reminder_time.replace(hour=meal_end, minute=0)
                        break

        return reminder_time

    def _generate_task_reminder(
        self,
        zone: Zone,
        task: PlantWateringTask,
        config: ReminderConfig,
        now: datetime
    ) -> Optional[Reminder]:
        if config.include_critical_only and task.priority != SchedulePriority.CRITICAL:
            return None

        if not config.include_high_priority and task.priority in [SchedulePriority.HIGH, SchedulePriority.MEDIUM, SchedulePriority.LOW]:
            return None

        advance_hours = config.advance_hours
        reminder_time = self._calculate_optimal_reminder_time(task, advance_hours)

        time_until_reminder = (reminder_time - now).total_seconds() / 3600
        if time_until_reminder < 0 or time_until_reminder > config.advance_hours + 24:
            return None

        template = self._get_reminder_template(task.priority.value)
        context = {
            "plant_name": task.plant_name,
            "date": task.scheduled_date.strftime("%m月%d日"),
            "window_start": task.scheduled_time_start.strftime("%H:%M") if task.scheduled_time_start else "",
            "window_end": task.scheduled_time_end.strftime("%H:%M") if task.scheduled_time_end else "",
            "overdue_hours": max(0, (now - (task.scheduled_time_start or datetime.combine(task.scheduled_date, datetime.min.time()))).total_seconds() / 3600),
            "zone_name": zone.name,
            "risk_level": task.risk_level,
            "water_amount_ml": task.water_amount_ml,
        }

        title = self._render_template(template.get("title", "浇水提醒"), context)
        message = self._render_template(template.get("message_template", "{plant_name}需要浇水"), context)

        for channel in config.channels:
            if not self._is_channel_enabled(channel):
                continue

            threshold = self._get_channel_priority_threshold(channel)
            if not self._check_priority_meets_threshold(task.priority, threshold):
                continue

            today_key = f"{channel.value}_{now.date().isoformat()}"
            today_count = self.daily_channel_counts.get(today_key, 0)
            daily_limit = self._get_channel_daily_limit(channel)
            if today_count >= daily_limit:
                continue

            reminder = Reminder(
                reminder_id=str(uuid.uuid4()),
                zone_id=zone.id,
                zone_name=zone.name,
                plant_id=task.plant_id,
                plant_name=task.plant_name,
                reminder_type="task_reminder",
                title=title,
                message=message,
                priority=task.priority,
                scheduled_time=reminder_time,
                channel=channel,
                status=ReminderStatus.PENDING,
                created_at=now,
                metadata={
                    "task_scheduled_date": task.scheduled_date.isoformat(),
                    "risk_level": task.risk_level,
                    "water_amount_ml": task.water_amount_ml,
                    "window_start": task.scheduled_time_start.isoformat() if task.scheduled_time_start else None,
                    "window_end": task.scheduled_time_end.isoformat() if task.scheduled_time_end else None,
                }
            )

            self.reminders_db[reminder.reminder_id] = reminder
            self.daily_channel_counts[today_key] = today_count + 1
            return reminder

        return None

    def _generate_batch_summary_reminder(
        self,
        zone: Zone,
        schedule: WateringScheduleResponse,
        config: ReminderConfig,
        now: datetime
    ) -> Optional[Reminder]:
        if not config.send_batch_summary:
            return None

        today = now.date()
        today_schedule = None
        for day in schedule.schedule:
            if day.date == today:
                today_schedule = day
                break

        if not today_schedule or today_schedule.total_tasks == 0:
            return None

        batch_summary_advance = get_schedule_rule("reminder_orchestration.batch_summary_advance_hours", 2)
        reminder_time = now + timedelta(hours=batch_summary_advance)

        template = self._get_reminder_template("batch_summary")
        context = {
            "zone_name": zone.name,
            "task_count": today_schedule.total_tasks,
            "critical_count": today_schedule.critical_count,
            "high_count": today_schedule.high_count,
            "medium_count": today_schedule.medium_count,
            "low_count": today_schedule.low_count,
            "date": today.strftime("%m月%d日"),
            "suggested_time": "上午9:00-10:00",
        }

        title = self._render_template(template.get("title", "今日浇水计划"), context)
        message = self._render_template(template.get("message_template", "今天有{task_count}株植物需要浇水"), context)

        channel = config.channels[0] if config.channels else ReminderChannel.APP_PUSH
        reminder = Reminder(
            reminder_id=str(uuid.uuid4()),
            zone_id=zone.id,
            zone_name=zone.name,
            reminder_type="batch_summary",
            title=title,
            message=message,
            priority=SchedulePriority.MEDIUM,
            scheduled_time=reminder_time,
            channel=channel,
            status=ReminderStatus.PENDING,
            created_at=now,
            metadata={
                "total_tasks": today_schedule.total_tasks,
                "critical_count": today_schedule.critical_count,
                "high_count": today_schedule.high_count,
                "batch_groups_count": len(today_schedule.batch_groups),
            }
        )

        self.reminders_db[reminder.reminder_id] = reminder
        return reminder

    def _generate_conflict_alert_reminder(
        self,
        zone: Zone,
        conflict_count: int,
        config: ReminderConfig,
        now: datetime
    ) -> Optional[Reminder]:
        if conflict_count == 0:
            return None

        template = self._get_reminder_template("conflict_alert")
        context = {
            "zone_name": zone.name,
            "conflict_count": conflict_count,
            "date": now.strftime("%m月%d日"),
        }

        title = self._render_template(template.get("title", "养护冲突提醒"), context)
        message = self._render_template(template.get("message_template", "检测到{conflict_count}个养护冲突"), context)

        channel = config.channels[0] if config.channels else ReminderChannel.APP_PUSH
        reminder = Reminder(
            reminder_id=str(uuid.uuid4()),
            zone_id=zone.id,
            zone_name=zone.name,
            reminder_type="conflict_alert",
            title=title,
            message=message,
            priority=SchedulePriority.HIGH,
            scheduled_time=now + timedelta(minutes=5),
            channel=channel,
            status=ReminderStatus.PENDING,
            created_at=now,
            metadata={
                "conflict_count": conflict_count,
                "zone_type": zone.zone_type.value,
            }
        )

        self.reminders_db[reminder.reminder_id] = reminder
        return reminder

    def generate_reminders(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant],
        schedule_service,
        conflict_service,
        hours_ahead: int = 24,
        config: Optional[ReminderConfig] = None
    ) -> List[Reminder]:
        if config is None:
            config = ReminderConfig()

        now = datetime.now()
        generated_reminders: List[Reminder] = []
        max_reminders = get_schedule_rule("reminder_orchestration.max_reminders_per_zone", 50)

        try:
            schedule = schedule_service.generate_schedule(zone, plants_db, max(7, days_ahead_from_hours(hours_ahead)))
            if not schedule:
                return []

            conflict_analysis = conflict_service.analyze_conflicts(zone, plants_db)
            conflict_count = conflict_analysis.total_conflicts if conflict_analysis else 0

            tasks_for_period: List[PlantWateringTask] = []
            cutoff_time = now + timedelta(hours=hours_ahead)

            for day in schedule.schedule:
                for task in day.tasks:
                    task_time = task.scheduled_time_start or datetime.combine(task.scheduled_date, datetime.min.time())
                    if task_time <= cutoff_time:
                        tasks_for_period.append(task)

            tasks_for_period.sort(key=lambda t: t.priority.value, reverse=True)

            for task in tasks_for_period:
                if len(generated_reminders) >= max_reminders:
                    break
                reminder = self._generate_task_reminder(zone, task, config, now)
                if reminder:
                    generated_reminders.append(reminder)

            batch_reminder = self._generate_batch_summary_reminder(zone, schedule, config, now)
            if batch_reminder and len(generated_reminders) < max_reminders:
                generated_reminders.append(batch_reminder)

            conflict_reminder = self._generate_conflict_alert_reminder(zone, conflict_count, config, now)
            if conflict_reminder and len(generated_reminders) < max_reminders:
                generated_reminders.append(conflict_reminder)

            if get_schedule_rule("reminder_orchestration.escalation_rules.enabled", True):
                escalation_reminders = self._check_and_generate_escalations(zone, config, now)
                for er in escalation_reminders:
                    if len(generated_reminders) < max_reminders:
                        generated_reminders.append(er)

        except Exception as e:
            print(f"Error generating reminders: {e}")

        return generated_reminders

    def _check_and_generate_escalations(
        self,
        zone: Zone,
        config: ReminderConfig,
        now: datetime
    ) -> List[Reminder]:
        escalations: List[Reminder] = []

        overdue_thresholds = {
            SchedulePriority.CRITICAL: get_schedule_rule("reminder_orchestration.escalation_rules.overdue_hours_critical", 6),
            SchedulePriority.HIGH: get_schedule_rule("reminder_orchestration.escalation_rules.overdue_hours_high", 12),
            SchedulePriority.MEDIUM: get_schedule_rule("reminder_orchestration.escalation_rules.overdue_hours_medium", 24),
        }

        for reminder in self.reminders_db.values():
            if reminder.zone_id != zone.id:
                continue
            if reminder.status != ReminderStatus.PENDING:
                continue

            overdue_hours = (now - reminder.scheduled_time).total_seconds() / 3600
            threshold = overdue_thresholds.get(reminder.priority, 24)

            if overdue_hours > threshold:
                escalation_channels = get_schedule_rule(
                    "reminder_orchestration.escalation_rules.escalation_channels",
                    ["app_push"]
                )

                for channel_str in escalation_channels:
                    try:
                        channel = ReminderChannel(channel_str)
                    except ValueError:
                        continue

                    escalation_reminder = Reminder(
                        reminder_id=str(uuid.uuid4()),
                        zone_id=zone.id,
                        zone_name=zone.name,
                        plant_id=reminder.plant_id,
                        plant_name=reminder.plant_name,
                        reminder_type="escalation",
                        title=f"【升级提醒】{reminder.title}",
                        message=f"浇水任务已逾期{overdue_hours:.0f}小时，请立即处理！\n原提醒：{reminder.message}",
                        priority=SchedulePriority.CRITICAL,
                        scheduled_time=now,
                        channel=channel,
                        status=ReminderStatus.PENDING,
                        created_at=now,
                        metadata={
                            "original_reminder_id": reminder.reminder_id,
                            "overdue_hours": round(overdue_hours, 1),
                            "escalation_level": 1,
                            "original_priority": reminder.priority.value,
                        }
                    )
                    self.reminders_db[escalation_reminder.reminder_id] = escalation_reminder
                    escalations.append(escalation_reminder)

        return escalations

    def get_reminders(
        self,
        zone_id: Optional[str] = None,
        status: Optional[ReminderStatus] = None,
        priority: Optional[SchedulePriority] = None,
        limit: int = 100
    ) -> ReminderListResponse:
        reminders = list(self.reminders_db.values())

        if zone_id:
            reminders = [r for r in reminders if r.zone_id == zone_id]
        if status:
            reminders = [r for r in reminders if r.status == status]
        if priority:
            reminders = [r for r in reminders if r.priority == priority]

        reminders.sort(key=lambda r: (r.status.value, r.priority.value, r.scheduled_time), reverse=True)
        reminders = reminders[:limit]

        pending_count = sum(1 for r in reminders if r.status == ReminderStatus.PENDING)
        sent_count = sum(1 for r in reminders if r.status == ReminderStatus.SENT)
        critical_count = sum(1 for r in reminders if r.priority == SchedulePriority.CRITICAL)
        high_count = sum(1 for r in reminders if r.priority == SchedulePriority.HIGH)

        return ReminderListResponse(
            total_reminders=len(reminders),
            pending_count=pending_count,
            sent_count=sent_count,
            critical_count=critical_count,
            high_count=high_count,
            reminders=reminders
        )

    def update_reminder_status(
        self,
        reminder_id: str,
        status: ReminderStatus
    ) -> Optional[Reminder]:
        reminder = self.reminders_db.get(reminder_id)
        if not reminder:
            return None

        reminder.status = status
        if status == ReminderStatus.SENT:
            reminder.sent_at = datetime.now()

        return reminder

    def dismiss_reminder(self, reminder_id: str) -> bool:
        return self.update_reminder_status(reminder_id, ReminderStatus.DISMISSED) is not None

    def clear_reminders(self, zone_id: Optional[str] = None) -> int:
        if zone_id:
            keys_to_remove = [k for k, v in self.reminders_db.items() if v.zone_id == zone_id]
            for k in keys_to_remove:
                del self.reminders_db[k]
            return len(keys_to_remove)
        else:
            count = len(self.reminders_db)
            self.reminders_db.clear()
            return count

    def get_reminder_statistics(self, zone_id: Optional[str] = None) -> Dict:
        reminders = list(self.reminders_db.values())
        if zone_id:
            reminders = [r for r in reminders if r.zone_id == zone_id]

        stats = {
            "total": len(reminders),
            "by_status": {},
            "by_priority": {},
            "by_type": {},
            "by_channel": {},
        }

        for r in reminders:
            stats["by_status"][r.status.value] = stats["by_status"].get(r.status.value, 0) + 1
            stats["by_priority"][r.priority.value] = stats["by_priority"].get(r.priority.value, 0) + 1
            stats["by_type"][r.reminder_type] = stats["by_type"].get(r.reminder_type, 0) + 1
            stats["by_channel"][r.channel.value] = stats["by_channel"].get(r.channel.value, 0) + 1

        return stats


def days_ahead_from_hours(hours: int) -> int:
    return max(1, (hours + 23) // 24)
