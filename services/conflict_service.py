from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import uuid
import statistics

from models.zone import Zone
from models.schedule import (
    ConflictDetail, AdjustmentSuggestion, ConflictAnalysisResponse,
    ConflictType, AdjustmentAction, SchedulePriority
)
from models import Plant
from watering_engine import WateringEngine
from plant_database import get_plant_info
from data.zone_rules import get_schedule_rule, get_zone_type_display


class ConflictService:
    def __init__(self, watering_engine: WateringEngine):
        self.watering_engine = watering_engine

    def _detect_watering_rhythm_mismatch(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> List[ConflictDetail]:
        conflicts: List[ConflictDetail] = []
        threshold_days = get_schedule_rule("conflict_detection.rhythm_mismatch_threshold_days", 3.0)

        plant_intervals = []
        for plant_id in zone.plant_ids:
            plant = plants_db.get(plant_id)
            if not plant:
                continue

            history = self.watering_engine.get_plant_history(plant_id)
            if len(history) < 2:
                continue

            avg_interval = self.watering_engine.calculate_average_interval(plant_id, plant.species)
            plant_intervals.append((plant_id, plant.name, avg_interval))

        if len(plant_intervals) < 2:
            return conflicts

        intervals = [x[2] for x in plant_intervals]
        min_interval = min(intervals)
        max_interval = max(intervals)

        if max_interval - min_interval > threshold_days:
            fast_plants = [(pid, pname, iv) for pid, pname, iv in plant_intervals if iv <= min_interval * 1.3]
            slow_plants = [(pid, pname, iv) for pid, pname, iv in plant_intervals if iv >= max_interval * 0.7]

            plant_ids = [x[0] for x in plant_intervals]
            plant_names = [x[1] for x in plant_intervals]

            severity = "high" if (max_interval - min_interval) > threshold_days * 2 else "medium"

            conflict = ConflictDetail(
                conflict_id=str(uuid.uuid4()),
                conflict_type=ConflictType.WATERING_RHYTHM_MISMATCH,
                severity=severity,
                plant_ids=plant_ids,
                plant_names=plant_names,
                description=f"分区内植物浇水节奏差异过大，最快{min_interval:.1f}天/次，最慢{max_interval:.1f}天/次",
                impact="统一浇水可能导致部分植物过干或过湿，增加养护难度和植物风险",
                data_evidence={
                    "min_interval_days": round(min_interval, 2),
                    "max_interval_days": round(max_interval, 2),
                    "difference_days": round(max_interval - min_interval, 2),
                    "threshold_days": threshold_days,
                    "fast_watering_plants": [
                        {"plant_id": pid, "plant_name": pname, "avg_interval_days": round(iv, 2)}
                        for pid, pname, iv in fast_plants
                    ],
                    "slow_watering_plants": [
                        {"plant_id": pid, "plant_name": pname, "avg_interval_days": round(iv, 2)}
                        for pid, pname, iv in slow_plants
                    ]
                }
            )
            conflicts.append(conflict)

        return conflicts

    def _detect_humidity_abnormal(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> List[ConflictDetail]:
        conflicts: List[ConflictDetail] = []
        humidity_deviation = get_schedule_rule("conflict_detection.humidity_deviation_percent", 20)

        if not zone.environment or zone.environment.avg_humidity is None:
            return conflicts

        zone_humidity = zone.environment.avg_humidity
        affected_plants = []

        for plant_id in zone.plant_ids:
            plant = plants_db.get(plant_id)
            if not plant:
                continue

            plant_info = get_plant_info(plant.species)
            if not plant_info:
                continue

            opt_min = plant_info["optimal_humidity_min"]
            opt_max = plant_info["optimal_humidity_max"]

            if zone_humidity < opt_min - humidity_deviation or zone_humidity > opt_max + humidity_deviation:
                affected_plants.append({
                    "plant_id": plant_id,
                    "plant_name": plant.name,
                    "optimal_range": [opt_min, opt_max],
                    "current_humidity": zone_humidity,
                    "deviation_percent": round(abs(zone_humidity - (opt_min + opt_max) / 2), 1)
                })

        if affected_plants:
            severity = "high" if len(affected_plants) > len(zone.plant_ids) * 0.5 else "medium"
            plant_ids = [p["plant_id"] for p in affected_plants]
            plant_names = [p["plant_name"] for p in affected_plants]

            direction = "偏低" if zone_humidity < 50 else "偏高"

            conflict = ConflictDetail(
                conflict_id=str(uuid.uuid4()),
                conflict_type=ConflictType.HUMIDITY_ABNORMAL,
                severity=severity,
                plant_ids=plant_ids,
                plant_names=plant_names,
                description=f"分区环境湿度{direction}，当前{zone_humidity}%，影响{len(affected_plants)}株植物",
                impact="湿度异常会导致植物生长不良，增加病害和应激风险",
                data_evidence={
                    "zone_humidity": zone_humidity,
                    "deviation_threshold_percent": humidity_deviation,
                    "affected_count": len(affected_plants),
                    "total_plants": len(zone.plant_ids),
                    "plants_detail": affected_plants
                }
            )
            conflicts.append(conflict)

        return conflicts

    def _detect_consistent_deviation(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> List[ConflictDetail]:
        conflicts: List[ConflictDetail] = []
        consecutive_threshold = get_schedule_rule("conflict_detection.consecutive_deviation_threshold", 3)

        for plant_id in zone.plant_ids:
            plant = plants_db.get(plant_id)
            if not plant:
                continue

            history = self.watering_engine.get_plant_history(plant_id)
            if len(history) < 4:
                continue

            base_interval = self.watering_engine.calculate_average_interval(plant_id, plant.species)

            reported_intervals = []
            for i in range(1, len(history)):
                interval = (history[i].last_watering_time - history[i-1].last_watering_time).total_seconds() / 86400
                if 0.5 <= interval <= 60:
                    reported_intervals.append(interval)

            if len(reported_intervals) < consecutive_threshold:
                continue

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

            if max_early >= consecutive_threshold or max_late >= consecutive_threshold:
                deviation_type = "提前" if max_early >= consecutive_threshold else "延后"
                severity = "high" if max(max_early, max_late) >= consecutive_threshold + 2 else "medium"

                conflict = ConflictDetail(
                    conflict_id=str(uuid.uuid4()),
                    conflict_type=ConflictType.CONSISTENT_DEVIATION,
                    severity=severity,
                    plant_ids=[plant_id],
                    plant_names=[plant.name],
                    description=f"{plant.name} 连续{max(max_early, max_late)}次{deviation_type}浇水，基准周期{base_interval:.1f}天",
                    impact="持续偏离正常浇水节奏会影响植物健康，可能导致根系问题",
                    data_evidence={
                        "plant_id": plant_id,
                        "plant_name": plant.name,
                        "base_interval_days": round(base_interval, 2),
                        "consecutive_early_count": max_early,
                        "consecutive_late_count": max_late,
                        "deviation_type": deviation_type,
                        "threshold": consecutive_threshold,
                        "recent_intervals": [round(x, 2) for x in reported_intervals[-5:]]
                    }
                )
                conflicts.append(conflict)

        return conflicts

    def _detect_prediction_window_conflict(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> List[ConflictDetail]:
        conflicts: List[ConflictDetail] = []
        overlap_threshold = get_schedule_rule("conflict_detection.prediction_window_overlap_hours", 6)

        plant_predictions = []
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
                plant_predictions.append((plant_id, plant.name, prediction))
            except ValueError:
                continue

        if len(plant_predictions) < 2:
            return conflicts

        zone_avg = statistics.mean([p[2].avg_watering_interval for p in plant_predictions])

        for plant_id, plant_name, prediction in plant_predictions:
            interval_diff = abs(prediction.avg_watering_interval - zone_avg)
            if interval_diff > zone_avg * 0.3:
                window_start = prediction.watering_window_start
                window_end = prediction.watering_window_end

                zone_window_start = datetime.now() + timedelta(days=max(0, zone_avg - 1))
                zone_window_end = datetime.now() + timedelta(days=zone_avg + 1)

                overlap = min(window_end, zone_window_end) - max(window_start, zone_window_start)
                overlap_hours = overlap.total_seconds() / 3600

                if overlap_hours < overlap_threshold:
                    severity = "high" if interval_diff > zone_avg * 0.5 else "medium"

                    conflict = ConflictDetail(
                        conflict_id=str(uuid.uuid4()),
                        conflict_type=ConflictType.PREDICTION_WINDOW_CONFLICT,
                        severity=severity,
                        plant_ids=[plant_id],
                        plant_names=[plant_name],
                        description=f"{plant_name} 预测浇水窗口与分区统一计划冲突，差异{interval_diff:.1f}天",
                        impact="该植物无法参与分区批量浇水，需要单独养护，增加管理复杂度",
                        data_evidence={
                            "plant_id": plant_id,
                            "plant_name": plant_name,
                            "plant_interval_days": round(prediction.avg_watering_interval, 2),
                            "zone_avg_interval_days": round(zone_avg, 2),
                            "difference_days": round(interval_diff, 2),
                            "plant_window": [window_start.isoformat(), window_end.isoformat()],
                            "zone_window": [zone_window_start.isoformat(), zone_window_end.isoformat()],
                            "overlap_hours": round(max(0, overlap_hours), 2),
                            "threshold_hours": overlap_threshold
                        }
                    )
                    conflicts.append(conflict)

        return conflicts

    def _detect_environment_mismatch(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> List[ConflictDetail]:
        conflicts: List[ConflictDetail] = []

        if not zone.environment:
            return conflicts

        env = zone.environment
        mismatched_plants = []

        for plant_id in zone.plant_ids:
            plant = plants_db.get(plant_id)
            if not plant:
                continue

            plant_info = get_plant_info(plant.species)
            if not plant_info:
                continue

            issues = []
            score = 100

            if env.avg_temperature is not None:
                if env.avg_temperature < plant_info["optimal_temp_min"] - 5:
                    issues.append(f"温度偏低{plant_info['optimal_temp_min'] - env.avg_temperature:.1f}°C")
                    score -= 25
                elif env.avg_temperature > plant_info["optimal_temp_max"] + 5:
                    issues.append(f"温度偏高{env.avg_temperature - plant_info['optimal_temp_max']:.1f}°C")
                    score -= 25

            if env.light_level:
                light_pref = plant_info.get("light_preference", "medium")
                light_map = {
                    "direct_sun": ["high"],
                    "bright_indirect": ["bright", "high", "medium"],
                    "medium": ["medium", "bright"],
                    "low": ["low", "medium"],
                    "shade": ["low"]
                }
                if light_pref not in light_map.get(env.light_level.value, []):
                    issues.append(f"光照不匹配（需要{light_pref}）")
                    score -= 20

            if issues:
                mismatched_plants.append({
                    "plant_id": plant_id,
                    "plant_name": plant.name,
                    "compatibility_score": score,
                    "issues": issues
                })

        if mismatched_plants:
            low_score_plants = [p for p in mismatched_plants if p["compatibility_score"] < 70]
            if low_score_plants:
                severity = "high" if len(low_score_plants) > len(zone.plant_ids) * 0.3 else "medium"
                plant_ids = [p["plant_id"] for p in low_score_plants]
                plant_names = [p["plant_name"] for p in low_score_plants]

                conflict = ConflictDetail(
                    conflict_id=str(uuid.uuid4()),
                    conflict_type=ConflictType.ENVIRONMENT_MISMATCH,
                    severity=severity,
                    plant_ids=plant_ids,
                    plant_names=plant_names,
                    description=f"{len(low_score_plants)}株植物与分区环境特征匹配度低于70%",
                    impact="环境不匹配会导致植物生长不良、适配度评分低下，长期可能死亡",
                    data_evidence={
                        "zone_type": zone.zone_type.value,
                        "zone_name": zone.name,
                        "environment": env.model_dump(mode="json") if env else None,
                        "affected_plants": low_score_plants
                    }
                )
                conflicts.append(conflict)

        return conflicts

    def _generate_adjustment_suggestions(
        self,
        conflicts: List[ConflictDetail],
        zone: Zone
    ) -> List[AdjustmentSuggestion]:
        suggestions: List[AdjustmentSuggestion] = []

        for conflict in conflicts:
            if conflict.conflict_type == ConflictType.WATERING_RHYTHM_MISMATCH:
                fast_plants = conflict.data_evidence.get("fast_watering_plants", [])
                slow_plants = conflict.data_evidence.get("slow_watering_plants", [])
                min_interval = conflict.data_evidence.get("min_interval_days", 0)
                max_interval = conflict.data_evidence.get("max_interval_days", 0)
                diff_days = conflict.data_evidence.get("difference_days", 0)

                implementation_steps = [
                    f"1. 按浇水节奏分组：快节奏组({min_interval:.1f}天/次，{len(fast_plants)}株)、慢节奏组({max_interval:.1f}天/次，{len(slow_plants)}株)",
                    "2. 为每个分组创建独立的养护分区",
                    "3. 设置不同的浇水提醒频率",
                    "4. 观察2周后评估分区效果"
                ]

                suggestion1 = AdjustmentSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    conflict_id=conflict.conflict_id,
                    action=AdjustmentAction.SPLIT_ZONE,
                    title="拆分为多个养护分区",
                    description=f"按浇水节奏将植物分为2-3个小组，快节奏({min_interval:.1f}天)与慢节奏({max_interval:.1f}天)差异达{diff_days:.1f}天，每组内植物浇水周期接近，便于统一管理。\n实施步骤：\n" + "\n".join(implementation_steps),
                    priority=SchedulePriority.HIGH,
                    expected_benefit=f"消除浇水节奏冲突，每个分区可执行统一浇水计划，养护效率提升约{min(90, int(diff_days * 15))}%，烂根和干旱风险预计降低60%",
                    implementation_difficulty="medium",
                    affected_plants=conflict.plant_ids,
                    alternative_solutions=[
                        "放弃批量浇水，改为个体单独养护（适合植物少于5株）",
                        "按优先级排序浇水，高风险植物优先（临时方案）",
                        "通过调整盆土/花盆材质缩小节奏差异（物理调节）"
                    ]
                )
                suggestions.append(suggestion1)

                if len(conflict.plant_ids) >= 2 and fast_plants and slow_plants:
                    relocate_ids = [p["plant_id"] for p in slow_plants]
                    relocate_names = [p["plant_name"] for p in slow_plants]
                    suggestion2 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.RELOCATE_PLANT,
                        title=f"将 {len(slow_plants)} 株慢节奏植物移至其他分区",
                        description=f"把浇水周期较长的植物（{', '.join(relocate_names)}）移至阳台或花园等适合少浇水的区域。这些植物平均{max_interval:.1f}天浇水一次，与当前分区节奏差异较大。",
                        priority=SchedulePriority.MEDIUM,
                        expected_benefit=f"保留当前分区的浇水节奏一致性，快节奏植物可继续批量管理，慢节奏植物在新区域获得更适合的养护，整体适配度预计提升30%",
                        implementation_difficulty="easy",
                        affected_plants=relocate_ids,
                        alternative_solutions=[
                            "将快节奏植物移至高湿度区域（如浴室）",
                            "为慢节奏植物更换保水性更好的盆土（泥炭+椰糠）",
                            "为慢节奏植物使用更大的花盆减少浇水频率"
                        ]
                    )
                    suggestions.append(suggestion2)

                    if len(slow_plants) >= 1:
                        target_species = slow_plants[0].get("plant_name", "")
                        suggestion3 = AdjustmentSuggestion(
                            suggestion_id=str(uuid.uuid4()),
                            conflict_id=conflict.conflict_id,
                            action=AdjustmentAction.CHANGE_SOIL,
                            title=f"为 {target_species} 更换盆土调节浇水节奏",
                            description=f"通过更换保水性更好的盆土（泥炭土+珍珠岩比例7:3），可将浇水周期延长约20-30%，缩小与分区平均节奏的差异。",
                            priority=SchedulePriority.LOW,
                            expected_benefit="物理调节浇水节奏，无需移动植物，预计可缩小20-30%的节奏差异",
                            implementation_difficulty="medium",
                            affected_plants=relocate_ids,
                            alternative_solutions=[
                                "更换为塑料盆减少蒸发（延长周期15%）",
                                "添加保水剂（延长周期25%）",
                                "减少光照强度（降低蒸发速率）"
                            ]
                        )
                        suggestions.append(suggestion3)

            elif conflict.conflict_type == ConflictType.HUMIDITY_ABNORMAL:
                zone_humidity = conflict.data_evidence.get("zone_humidity", 0)
                affected_count = conflict.data_evidence.get("affected_count", 0)
                plants_detail = conflict.data_evidence.get("plants_detail", [])
                is_low_humidity = zone_humidity < 50

                if is_low_humidity:
                    humidity_deficit = 50 - zone_humidity
                    steps = [
                        f"1. 购置加湿器（推荐加湿量{max(200, int(humidity_deficit * 50))}ml/h）",
                        "2. 每天上午9-10点对叶面喷雾一次",
                        "3. 将植物集中放置，下方放置加湿托盘（装水+鹅卵石）",
                        f"4. 目标湿度提升至{min(70, int(zone_humidity + 20))}%"
                    ]
                    suggestion1 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.ADD_HUMIDIFIER,
                        title="增加空气加湿设备",
                        description=f"当前湿度{zone_humidity}%，低于植物需求约{humidity_deficit:.0f}%，影响{affected_count}株植物。\n实施步骤：\n" + "\n".join(steps),
                        priority=SchedulePriority.HIGH,
                        expected_benefit=f"预计7-10天内湿度提升{humidity_deficit:.0f}%，植物适配度评分可提升15-30分，叶片干枯风险降低80%",
                        implementation_difficulty="easy",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "每天对叶面喷雾1-2次（短期应急）",
                            "将植物移至浴室等高湿度区域（适合小型植物）",
                            "组盆种植提高局部湿度（景观效果好）"
                        ]
                    )
                else:
                    humidity_excess = zone_humidity - 60
                    steps = [
                        "1. 每天开窗通风2-3次，每次30分钟",
                        "2. 使用电风扇加强空气流通（避免直吹植物）",
                        f"3. 检查是否存在漏水或积水来源",
                        f"4. 目标湿度降低至{max(40, int(zone_humidity - 15))}%"
                    ]
                    suggestion1 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.IMPROVE_VENTILATION,
                        title="改善通风降低湿度",
                        description=f"当前湿度{zone_humidity}%，偏高约{humidity_excess:.0f}%，影响{affected_count}株植物。高湿环境易引发烂根和病害。\n实施步骤：\n" + "\n".join(steps),
                        priority=SchedulePriority.HIGH,
                        expected_benefit=f"预计3-5天内湿度降低{humidity_excess:.0f}%，烂根风险降低70%，真菌病害风险降低90%",
                        implementation_difficulty="easy",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "减少浇水频率20-30%",
                            "将敏感植物移至干燥区域",
                            "更换为透气性更好的盆土"
                        ]
                    )
                suggestions.append(suggestion1)

                if plants_detail:
                    sensitive_plants = sorted(plants_detail, key=lambda x: x.get("deviation_percent", 0), reverse=True)[:3]
                    relocate_ids = [p["plant_id"] for p in sensitive_plants]
                    relocate_names = [p["plant_name"] for p in sensitive_plants]
                    suggestion2 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.RELOCATE_PLANT,
                        title=f"将 {len(relocate_ids)} 株最敏感植物调整摆放位置",
                        description=f"以下植物对湿度最敏感：{', '.join(relocate_names)}。建议移至更适合的环境区域。",
                        priority=SchedulePriority.MEDIUM,
                        expected_benefit="快速解决敏感植物的湿度问题，不影响其他植物，预计这些植物的适配度可立即提升20分以上",
                        implementation_difficulty="easy",
                        affected_plants=relocate_ids,
                        alternative_solutions=[
                            "为敏感植物单独使用微气候调节方案（如小型加湿器）",
                            "创建湿度缓冲区域（植物组盆）"
                        ]
                    )
                    suggestions.append(suggestion2)

            elif conflict.conflict_type == ConflictType.CONSISTENT_DEVIATION:
                deviation_type = conflict.data_evidence.get("deviation_type", "提前")
                base_interval = conflict.data_evidence.get("base_interval_days", 0)
                consecutive_count = max(
                    conflict.data_evidence.get("consecutive_early_count", 0),
                    conflict.data_evidence.get("consecutive_late_count", 0)
                )
                recent_intervals = conflict.data_evidence.get("recent_intervals", [])
                plant_name = conflict.plant_names[0] if conflict.plant_names else "该植物"

                actual_avg = statistics.mean(recent_intervals) if recent_intervals else base_interval
                deviation_percent = abs(actual_avg - base_interval) / base_interval * 100

                if deviation_type == "延后":
                    steps = [
                        f"1. 将浇水周期从基准{base_interval:.1f}天调整为实际{actual_avg:.1f}天",
                        "2. 更新浇水提醒时间设置",
                        "3. 观察土壤湿度变化，确认新周期是否合适",
                        "4. 2周后重新评估是否需要进一步调整"
                    ]
                    suggestion1 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.ADJUST_WATERING_FREQUENCY,
                        title=f"调整{plant_name}的浇水计划",
                        description=f"{plant_name}已连续{consecutive_count}次延后浇水，实际周期{actual_avg:.1f}天，比基准{base_interval:.1f}天偏长{deviation_percent:.0f}%。\n实施步骤：\n" + "\n".join(steps),
                        priority=SchedulePriority.HIGH,
                        expected_benefit=f"消除持续偏差，使浇水预测准确率提升至90%以上，植物应激反应减少70%",
                        implementation_difficulty="easy",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "设置更精准的浇水提醒（提前1天+当天提醒）",
                            "检查是否存在环境因素导致需水量减少（温度降低、光照减弱）",
                            "考虑植物是否进入休眠期"
                        ]
                    )

                    suggestion2 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.CHANGE_SOIL,
                        title=f"为{plant_name}更换为保水性更好的盆土",
                        description=f"使用泥炭土+珍珠岩（7:3比例）或椰糠等保水性好的介质，可将浇水周期再延长20-30%，更符合实际养护习惯。",
                        priority=SchedulePriority.MEDIUM,
                        expected_benefit=f"从物理层面延长浇水周期约20%，减少养护频率，避免因忘记浇水导致的干旱风险",
                        implementation_difficulty="medium",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "更换为更大的花盆（增加2-3cm直径）",
                            "在盆土中添加保水剂（每升土加5g）",
                            "组盆种植减少蒸发"
                        ]
                    )
                else:
                    steps = [
                        f"1. 将浇水周期从基准{base_interval:.1f}天调整为实际{actual_avg:.1f}天",
                        "2. 缩短浇水提醒间隔",
                        "3. 每次浇水前检查土壤湿度，避免积水",
                        "4. 2周后评估植物状态"
                    ]
                    suggestion1 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.ADJUST_WATERING_FREQUENCY,
                        title=f"调整{plant_name}的浇水计划",
                        description=f"{plant_name}已连续{consecutive_count}次提前浇水，实际周期{actual_avg:.1f}天，比基准{base_interval:.1f}天偏短{deviation_percent:.0f}%。\n实施步骤：\n" + "\n".join(steps),
                        priority=SchedulePriority.HIGH,
                        expected_benefit=f"消除持续偏差，使浇水预测准确率提升至90%以上，烂根风险降低60%",
                        implementation_difficulty="easy",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "设置更精准的浇水提醒（基于土壤湿度而非固定周期）",
                            "检查是否存在环境因素导致需水量增加（温度升高、光照增强）",
                            "检查植物是否处于生长旺盛期"
                        ]
                    )

                    suggestion2 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.CHANGE_SOIL,
                        title=f"为{plant_name}更换为透水性更好的盆土",
                        description=f"使用沙质土+珍珠岩（1:1比例）或增加颗粒比例（赤玉土、鹿沼土），加快土壤干燥速度20-30%，避免频繁浇水导致的烂根风险。",
                        priority=SchedulePriority.MEDIUM,
                        expected_benefit="从物理层面缩短浇水周期约20%，减少积水风险，根系健康度显著提升",
                        implementation_difficulty="medium",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "更换为透气的陶土盆（蒸发提升30%）",
                            "检查排水孔是否通畅，必要时扩大排水孔",
                            "在盆底添加疏水层（陶粒、碎砖块）"
                        ]
                    )

                suggestions.append(suggestion1)
                suggestions.append(suggestion2)

                if consecutive_count >= 5:
                    suggestion3 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.RELOCATE_PLANT,
                        title=f"评估{plant_name}的摆放位置是否合适",
                        description=f"连续{consecutive_count}次偏差可能表明当前位置的微气候不适合该植物。建议评估光照、温度、通风条件是否匹配植物需求。",
                        priority=SchedulePriority.LOW,
                        expected_benefit="从根本上解决浇水周期持续偏差问题，植物适配度预计提升25分以上",
                        implementation_difficulty="medium",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "安装小型环境监测设备追踪微气候",
                            "咨询园艺专家确认植物习性"
                        ]
                    )
                    suggestions.append(suggestion3)

            elif conflict.conflict_type == ConflictType.PREDICTION_WINDOW_CONFLICT:
                plant_name = conflict.plant_names[0] if conflict.plant_names else "该植物"
                plant_interval = conflict.data_evidence.get("plant_interval_days", 0)
                zone_avg_interval = conflict.data_evidence.get("zone_avg_interval_days", 0)
                difference_days = conflict.data_evidence.get("difference_days", 0)
                overlap_hours = conflict.data_evidence.get("overlap_hours", 0)
                threshold_hours = conflict.data_evidence.get("threshold_hours", 6)

                is_faster = plant_interval < zone_avg_interval
                direction = "快" if is_faster else "慢"
                pot_type = "陶土盆（增加蒸发）" if is_faster else "塑料盆（减少蒸发）"
                soil_type = "沙质土（加快干燥）" if is_faster else "泥炭土（增强保水）"

                steps = [
                    f"1. 分析现有分区的浇水节奏（{zone_avg_interval:.1f}天/次）",
                    f"2. 找到与{plant_name}节奏（{plant_interval:.1f}天/次）接近的分区",
                    "3. 检查目标分区的环境条件是否匹配该植物需求",
                    "4. 逐步迁移并观察2周"
                ]

                suggestion1 = AdjustmentSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    conflict_id=conflict.conflict_id,
                    action=AdjustmentAction.RELOCATE_PLANT,
                    title=f"将{plant_name}移至匹配的养护分区",
                    description=f"{plant_name}的浇水节奏（{plant_interval:.1f}天）与当前分区（{zone_avg_interval:.1f}天）差异{direction}{difference_days:.1f}天，预测窗口仅重叠{overlap_hours:.1f}小时（要求>={threshold_hours}小时），无法参与批量浇水。\n实施步骤：\n" + "\n".join(steps),
                    priority=SchedulePriority.MEDIUM,
                    expected_benefit=f"{plant_name}可加入新分区的批量浇水计划，整体养护效率提升约25%，管理复杂度降低",
                    implementation_difficulty="easy",
                    affected_plants=conflict.plant_ids,
                    alternative_solutions=[
                        "保留在当前分区但设置单独提醒（适合差异<2天）",
                        "调整养护条件使其适应分区节奏（物理调节）",
                        "为该植物设置个性化浇水计划"
                    ]
                )
                suggestions.append(suggestion1)

                steps2 = [
                    f"1. 将当前花盆更换为{pot_type}",
                    f"2. 配合更换为{soil_type}",
                    "3. 观察2-4周，记录新的浇水周期",
                    "4. 评估是否缩小了与分区节奏的差异"
                ]

                suggestion2 = AdjustmentSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    conflict_id=conflict.conflict_id,
                    action=AdjustmentAction.CHANGE_POT,
                    title=f"调整{plant_name}的花盆材质微调浇水节奏",
                    description=f"通过更换{pot_type}来调整水分蒸发速度，配合{soil_type}，预计可将浇水周期调整约20-30%，缩小与分区节奏的差异。\n实施步骤：\n" + "\n".join(steps2),
                    priority=SchedulePriority.LOW,
                    expected_benefit=f"物理微调浇水节奏，可能缩小20-30%的差异，无需移动植物，适合不想调整布局的场景",
                    implementation_difficulty="medium",
                    affected_plants=conflict.plant_ids,
                    alternative_solutions=[
                        "单独调整盆土类型",
                        "调整摆放位置的光照通风条件",
                        "使用加湿器/除湿机调节微气候"
                    ]
                )
                suggestions.append(suggestion2)

                suggestion3 = AdjustmentSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    conflict_id=conflict.conflict_id,
                    action=AdjustmentAction.SPLIT_ZONE,
                    title=f"为{plant_name}创建专项养护小组",
                    description=f"在当前分区内创建一个子分组，将节奏相近的植物集中管理，设置独立的浇水提醒，实现差异化养护。",
                    priority=SchedulePriority.LOW,
                    expected_benefit="无需移动植物，在现有分区内实现精细化管理，适合空间有限的场景",
                    implementation_difficulty="medium",
                    affected_plants=conflict.plant_ids,
                    alternative_solutions=[
                        "使用智能浇水设备实现自动化精准浇水",
                        "设置分层级的提醒机制"
                    ]
                )
                suggestions.append(suggestion3)

            elif conflict.conflict_type == ConflictType.ENVIRONMENT_MISMATCH:
                affected = conflict.data_evidence.get("affected_plants", [])
                zone_name_display = get_zone_type_display(zone.zone_type)
                if affected:
                    relocate_ids = [p["plant_id"] for p in affected]
                    relocate_details = []
                    for p in affected:
                        issues = ", ".join(p.get("issues", []))
                        relocate_details.append(f"{p['plant_name']}(匹配度{p['compatibility_score']}分：{issues})")

                    steps = [
                        "1. 评估每个植物的具体环境需求（光照、温度、湿度）",
                        "2. 查找现有分区中环境条件匹配的区域",
                        "3. 制定迁移计划，优先移动高价值或高风险植物",
                        "4. 迁移后观察2周，确认植物状态"
                    ]

                    suggestion1 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.RELOCATE_PLANT,
                        title=f"调整 {len(relocate_ids)} 株植物的摆放位置",
                        description=f"当前分区为{zone_name_display}，以下植物与环境匹配度低于70分：\n" + "\n".join(relocate_details) + "\n\n建议移至更适合的分区，如喜阳植物移至阳台，喜阴植物移至室内。\n实施步骤：\n" + "\n".join(steps),
                        priority=SchedulePriority.HIGH,
                        expected_benefit="从根本上解决环境不匹配问题，这些植物的适配度预计可提升30-50分，长期健康状况显著改善",
                        implementation_difficulty="easy",
                        affected_plants=relocate_ids,
                        alternative_solutions=[
                            "使用补光灯（30-50W LED）补充光照",
                            "使用遮阳网（50-70%遮光率）减少光照",
                            "使用加温/降温设备调节温度",
                            "使用加湿器/除湿机调节湿度"
                        ]
                    )
                    suggestions.append(suggestion1)

                    steps2 = [
                        "1. 盘点所有植物的环境需求",
                        "2. 按光照需求（强光/中等/弱光）分组",
                        "3. 按温度适应性分组",
                        "4. 重新规划分区布局，将需求相近的植物集中",
                        "5. 迁移后1个月进行整体评估"
                    ]

                    suggestion2 = AdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        conflict_id=conflict.conflict_id,
                        action=AdjustmentAction.SPLIT_ZONE,
                        title="按环境需求重新划分养护分区",
                        description=f"当前有{len(relocate_ids)}株植物环境不匹配，建议系统性地重新规划所有分区。根据植物的光照、温度、湿度需求，将现有植物重新分配到更合适的分区。\n实施步骤：\n" + "\n".join(steps2),
                        priority=SchedulePriority.MEDIUM,
                        expected_benefit="系统性优化所有植物的养护环境，整体适配度预计提升30%以上，长期养护成本降低，植物存活率提高",
                        implementation_difficulty="medium",
                        affected_plants=conflict.plant_ids,
                        alternative_solutions=[
                            "在当前分区内创建微气候区域（如组盆、使用挡风板）",
                            "为特殊需求植物设置单独的养护方案（如单独的光照时间表）",
                            "淘汰不适合当前环境的植物，更换为适应性更强的品种"
                        ]
                    )
                    suggestions.append(suggestion2)

        return suggestions

    def analyze_conflicts(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> Optional[ConflictAnalysisResponse]:
        all_conflicts: List[ConflictDetail] = []

        all_conflicts.extend(self._detect_watering_rhythm_mismatch(zone, plants_db))
        all_conflicts.extend(self._detect_humidity_abnormal(zone, plants_db))
        all_conflicts.extend(self._detect_consistent_deviation(zone, plants_db))
        all_conflicts.extend(self._detect_prediction_window_conflict(zone, plants_db))
        all_conflicts.extend(self._detect_environment_mismatch(zone, plants_db))

        suggestions = self._generate_adjustment_suggestions(all_conflicts, zone)

        adaptation_scores = []
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
                adaptation_scores.append(prediction.adaptation_score)
            except ValueError:
                continue

        overall_health = statistics.mean(adaptation_scores) if adaptation_scores else 0.0

        recommendations = []
        if not all_conflicts:
            recommendations.append("当前分区养护状态良好，建议继续保持现有养护方案")
        else:
            high_severity = [c for c in all_conflicts if c.severity == "high"]
            if high_severity:
                recommendations.append(f"优先处理 {len(high_severity)} 个高优先级冲突")
            if any(c.conflict_type == ConflictType.WATERING_RHYTHM_MISMATCH for c in all_conflicts):
                recommendations.append("建议评估分区拆分或植物重新布局的可行性")
            if any(c.conflict_type == ConflictType.HUMIDITY_ABNORMAL for c in all_conflicts):
                recommendations.append("考虑投资环境调节设备（加湿器/除湿机）")

        response = ConflictAnalysisResponse(
            zone_id=zone.id,
            zone_name=zone.name,
            analyzed_at=datetime.now(),
            total_conflicts=len(all_conflicts),
            conflicts=all_conflicts,
            adjustment_suggestions=suggestions,
            overall_health_score=round(overall_health, 2),
            recommendations=recommendations
        )

        return response
