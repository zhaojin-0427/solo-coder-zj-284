from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import uuid
from collections import Counter, defaultdict

from models.maintenance_log import (
    MaintenanceLogCreate, MaintenanceLogUpdate, MaintenanceLog,
    FollowUpObservation, OperationAnalysis, AdjustmentSuggestion,
    ZoneAnalysisSummary, MaintenanceOperationType, OperationEffectiveness,
    RecoveryTrend, AdjustmentType, RiskLevel, PlantStatus
)
from models import Plant, WateringReport, Zone
from watering_engine import WateringEngine
from plant_database import get_plant_info
from services.pest_disease_service import PestDiseaseService


class MaintenanceLogService:
    def __init__(self, watering_engine: WateringEngine, pest_disease_service: PestDiseaseService):
        self.logs_db: Dict[str, MaintenanceLog] = {}
        self.watering_engine = watering_engine
        self.pest_disease_service = pest_disease_service

    def create_log(self, data: MaintenanceLogCreate) -> MaintenanceLog:
        log_id = str(uuid.uuid4())
        now = datetime.now()

        log = MaintenanceLog(
            id=log_id,
            **data.model_dump(),
            created_at=now,
            updated_at=now
        )

        if data.status_after and data.status_after.health_score is not None:
            log.effectiveness = self._calculate_initial_effectiveness(
                data.status_before, data.status_after
            )

        self.logs_db[log_id] = log
        return log

    def get_log(self, log_id: str) -> Optional[MaintenanceLog]:
        return self.logs_db.get(log_id)

    def get_plant_logs(self, plant_id: str, limit: int = 100) -> List[MaintenanceLog]:
        logs = [
            log for log in self.logs_db.values()
            if log.target_type == "plant" and log.target_id == plant_id
        ]
        logs.sort(key=lambda l: l.execution_time, reverse=True)
        return logs[:limit]

    def get_zone_logs(self, zone_id: str, limit: int = 100) -> List[MaintenanceLog]:
        logs = [
            log for log in self.logs_db.values()
            if log.target_type == "zone" and log.target_id == zone_id
        ]
        logs.sort(key=lambda l: l.execution_time, reverse=True)
        return logs[:limit]

    def get_all_logs(
        self,
        target_type: Optional[str] = None,
        operation_type: Optional[MaintenanceOperationType] = None,
        effectiveness: Optional[OperationEffectiveness] = None,
        limit: int = 100
    ) -> List[MaintenanceLog]:
        logs = list(self.logs_db.values())

        if target_type:
            logs = [l for l in logs if l.target_type == target_type]
        if operation_type:
            logs = [l for l in logs if l.operation_type == operation_type]
        if effectiveness:
            logs = [l for l in logs if l.effectiveness == effectiveness]

        logs.sort(key=lambda l: l.execution_time, reverse=True)
        return logs[:limit]

    def update_log(self, log_id: str, update: MaintenanceLogUpdate) -> Optional[MaintenanceLog]:
        log = self.logs_db.get(log_id)
        if not log:
            return None

        update_data = update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(log, key, value)

        if update.status_after and update.status_after.health_score is not None:
            log.effectiveness = self._calculate_initial_effectiveness(
                log.status_before, update.status_after
            )

        log.updated_at = datetime.now()
        return log

    def add_follow_up_observation(self, observation: FollowUpObservation) -> Optional[MaintenanceLog]:
        log = self.logs_db.get(observation.log_id)
        if not log:
            return None

        log.follow_up_observations.append({
            "observation_time": observation.observation_time.isoformat(),
            "observer": observation.observer,
            "current_status": observation.current_status.model_dump(mode="json"),
            "observation_notes": observation.observation_notes
        })

        self._reassess_effectiveness(log)
        log.updated_at = datetime.now()
        return log

    def delete_log(self, log_id: str) -> bool:
        if log_id not in self.logs_db:
            return False
        del self.logs_db[log_id]
        return True

    def analyze_operation(
        self,
        log: MaintenanceLog,
        plant: Optional[Plant] = None,
        zone: Optional[Zone] = None,
        plants_db: Optional[Dict[str, Plant]] = None
    ) -> OperationAnalysis:
        plant_info = get_plant_info(plant.species) if plant else None
        watering_history = self.watering_engine.get_plant_history(log.target_id) if log.target_type == "plant" else []
        pest_records = self.pest_disease_service.get_plant_records(log.target_id) if log.target_type == "plant" else []

        environmental_factors = self._analyze_environmental_factors(zone, watering_history, plant_info)
        watering_factors = self._analyze_watering_factors(log, watering_history, plant_info)
        pest_disease_factors = self._analyze_pest_disease_factors(log, pest_records)
        anomaly_factors = self._analyze_anomaly_factors(log, watering_history, plant_info)

        similar_ops, duplicate_count = self._find_similar_operations(log)
        has_duplicates = duplicate_count >= 3

        effectiveness_score, effectiveness = self._calculate_effectiveness_score(
            log, environmental_factors, watering_factors, pest_disease_factors, anomaly_factors
        )

        is_effective = effectiveness in [OperationEffectiveness.VERY_EFFECTIVE, OperationEffectiveness.EFFECTIVE]

        recovery_trend, trend_confidence = self._determine_recovery_trend(
            log, similar_ops, watering_history
        )

        supporting_evidence = self._collect_supporting_evidence(
            log, environmental_factors, watering_factors, pest_disease_factors, anomaly_factors
        )

        contradicting_evidence = self._collect_contradicting_evidence(
            log, environmental_factors, watering_factors, pest_disease_factors, anomaly_factors
        )

        recommendation_type, recommendation = self._generate_recommendation(
            log, is_effective, has_duplicates, recovery_trend, effectiveness_score, plant_info
        )

        next_review_time = self._calculate_next_review_time(
            log, recovery_trend, effectiveness, zone
        )

        review_focus = self._generate_review_focus(
            log, recovery_trend, effectiveness
        )

        risk_warnings = self._generate_risk_warnings(
            log, has_duplicates, recovery_trend, environmental_factors, watering_factors
        )

        overall_confidence = self._calculate_overall_confidence(
            log, watering_history, pest_records, plant_info
        )

        explanation = self._generate_explanation(
            log, is_effective, effectiveness, recovery_trend, recommendation, plant
        )

        return OperationAnalysis(
            log_id=log.id,
            target_type=log.target_type,
            target_id=log.target_id,
            operation_type=log.operation_type,
            execution_time=log.execution_time,
            is_effective=is_effective,
            effectiveness_score=effectiveness_score,
            effectiveness=effectiveness,
            recovery_trend=recovery_trend,
            recovery_trend_confidence=trend_confidence,
            supporting_evidence=supporting_evidence,
            contradicting_evidence=contradicting_evidence,
            has_duplicate_operations=has_duplicates,
            duplicate_operation_count=duplicate_count,
            duplicate_operation_window_days=14,
            similar_operations=[
                {
                    "log_id": op["log"].id,
                    "operation_type": op["log"].operation_type.value,
                    "execution_time": op["log"].execution_time.isoformat(),
                    "days_since_current": op["days_diff"],
                    "effectiveness": op["log"].effectiveness.value
                }
                for op in similar_ops
            ],
            environmental_factors=environmental_factors,
            watering_history_factors=watering_factors,
            pest_disease_factors=pest_disease_factors,
            anomaly_alert_factors=anomaly_factors,
            recommendation=recommendation,
            recommendation_type=recommendation_type,
            next_review_time=next_review_time,
            review_focus=review_focus,
            risk_warnings=risk_warnings,
            overall_confidence=overall_confidence,
            explanation=explanation
        )

    def generate_adjustment_suggestions(
        self,
        target_type: str,
        target_id: str,
        plants_db: Dict[str, Plant],
        zones_db: Dict[str, Zone]
    ) -> List[AdjustmentSuggestion]:
        suggestions: List[AdjustmentSuggestion] = []

        if target_type == "plant":
            suggestions.extend(self._generate_plant_suggestions(target_id, plants_db, zones_db))
        elif target_type == "zone":
            suggestions.extend(self._generate_zone_suggestions(target_id, plants_db, zones_db))

        return suggestions

    def analyze_zone_operations(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> ZoneAnalysisSummary:
        zone_logs = self.get_zone_logs(zone.id)
        plant_ids = set(zone.plant_ids)

        plant_logs = [
            log for log in self.logs_db.values()
            if log.target_type == "plant" and log.target_id in plant_ids
        ]
        all_logs = zone_logs + plant_logs

        total_ops = len(all_logs)
        effective_ops = sum(
            1 for log in all_logs
            if log.effectiveness in [OperationEffectiveness.VERY_EFFECTIVE, OperationEffectiveness.EFFECTIVE]
        )
        ineffective_ops = sum(
            1 for log in all_logs
            if log.effectiveness in [OperationEffectiveness.INEFFECTIVE, OperationEffectiveness.HARMFUL]
        )

        plants_improving = 0
        plants_deteriorating = 0
        plants_stable = 0

        for plant_id in plant_ids:
            plant_logs = [
                log for log in self.logs_db.values()
                if log.target_type == "plant" and log.target_id == plant_id
                and log.status_after and log.status_after.health_score is not None
            ]
            if plant_logs:
                latest_log = max(plant_logs, key=lambda l: l.execution_time)
                if latest_log.effectiveness in [OperationEffectiveness.VERY_EFFECTIVE, OperationEffectiveness.EFFECTIVE]:
                    plants_improving += 1
                elif latest_log.effectiveness in [OperationEffectiveness.INEFFECTIVE, OperationEffectiveness.HARMFUL]:
                    plants_deteriorating += 1
                else:
                    plants_stable += 1

        operation_counter = Counter(log.operation_type.value for log in all_logs)
        common_ops = [
            {"operation_type": op, "count": count, "percentage": round(count / total_ops * 100, 1) if total_ops > 0 else 0}
            for op, count in operation_counter.most_common(5)
        ]

        problematic_patterns = self._identify_problematic_patterns(zone, plant_ids)

        zone_suggestions = self._generate_zone_suggestions(zone.id, plants_db, {zone.id: zone})

        return ZoneAnalysisSummary(
            zone_id=zone.id,
            zone_name=zone.name,
            total_operations=total_ops,
            effective_operations=effective_ops,
            ineffective_operations=ineffective_ops,
            plants_with_improvement=plants_improving,
            plants_with_deterioration=plants_deteriorating,
            plants_with_stable_status=plants_stable,
            common_operations=common_ops,
            problematic_patterns=problematic_patterns,
            zone_wide_adjustments=zone_suggestions,
            analysis_time=datetime.now()
        )

    def _calculate_initial_effectiveness(
        self,
        status_before: PlantStatus,
        status_after: PlantStatus
    ) -> OperationEffectiveness:
        if status_before.health_score is None or status_after.health_score is None:
            return OperationEffectiveness.PENDING

        score_diff = status_after.health_score - status_before.health_score

        if score_diff >= 20:
            return OperationEffectiveness.VERY_EFFECTIVE
        elif score_diff >= 10:
            return OperationEffectiveness.EFFECTIVE
        elif score_diff >= 0:
            return OperationEffectiveness.PARTIALLY_EFFECTIVE
        elif score_diff >= -10:
            return OperationEffectiveness.INEFFECTIVE
        else:
            return OperationEffectiveness.HARMFUL

    def _analyze_environmental_factors(
        self,
        zone: Optional[Zone],
        watering_history: List[WateringReport],
        plant_info: Optional[Dict]
    ) -> Dict[str, Any]:
        factors = {
            "temperature_optimal": None,
            "humidity_optimal": None,
            "current_temperature": None,
            "current_humidity": None,
            "ventilation_level": None,
            "light_level": None,
            "zone_type": None,
            "environmental_stress": False,
            "stress_factors": []
        }

        if watering_history:
            last_report = watering_history[-1]
            factors["current_temperature"] = last_report.temperature
            factors["current_humidity"] = last_report.humidity

            if plant_info:
                temp_optimal = (
                    plant_info["optimal_temp_min"] <= last_report.temperature <= plant_info["optimal_temp_max"]
                )
                humidity_optimal = (
                    plant_info["optimal_humidity_min"] <= last_report.humidity <= plant_info["optimal_humidity_max"]
                )
                factors["temperature_optimal"] = temp_optimal
                factors["humidity_optimal"] = humidity_optimal

                if not temp_optimal:
                    factors["environmental_stress"] = True
                    factors["stress_factors"].append("温度异常")
                if not humidity_optimal:
                    factors["environmental_stress"] = True
                    factors["stress_factors"].append("湿度异常")

        if zone and zone.environment:
            factors["ventilation_level"] = zone.environment.ventilation.value if zone.environment.ventilation else None
            factors["light_level"] = zone.environment.light_level.value if zone.environment.light_level else None
            factors["zone_type"] = zone.zone_type.value

            if zone.environment.ventilation and zone.environment.ventilation.value == "poor":
                factors["environmental_stress"] = True
                factors["stress_factors"].append("通风不良")

        return factors

    def _analyze_watering_factors(
        self,
        log: MaintenanceLog,
        watering_history: List[WateringReport],
        plant_info: Optional[Dict]
    ) -> Dict[str, Any]:
        factors = {
            "has_history": len(watering_history) > 0,
            "report_count": len(watering_history),
            "avg_interval_days": None,
            "soil_moisture_current": None,
            "overwatering_risk": False,
            "underwatering_risk": False,
            "watering_pattern_consistent": None,
            "operation_aligns_with_need": None
        }

        if watering_history:
            last_report = watering_history[-1]
            factors["soil_moisture_current"] = last_report.soil_moisture

            intervals = []
            for i in range(1, len(watering_history)):
                diff = (watering_history[i].last_watering_time - watering_history[i-1].last_watering_time).total_seconds() / 86400
                if 0.5 <= diff <= 60:
                    intervals.append(diff)

            if intervals:
                factors["avg_interval_days"] = round(sum(intervals) / len(intervals), 1)
                if len(intervals) >= 3:
                    interval_variance = max(intervals) - min(intervals)
                    factors["watering_pattern_consistent"] = interval_variance <= 3

            if plant_info and last_report.soil_moisture is not None:
                if last_report.soil_moisture > 80:
                    factors["overwatering_risk"] = True
                elif last_report.soil_moisture < 20:
                    factors["underwatering_risk"] = True

                if log.operation_type == MaintenanceOperationType.WATERING:
                    if factors["underwatering_risk"]:
                        factors["operation_aligns_with_need"] = True
                    elif factors["overwatering_risk"]:
                        factors["operation_aligns_with_need"] = False

        return factors

    def _analyze_pest_disease_factors(
        self,
        log: MaintenanceLog,
        pest_records: List
    ) -> Dict[str, Any]:
        factors = {
            "active_pest_disease": False,
            "active_records_count": 0,
            "resolved_records_count": 0,
            "related_pest_disease": None,
            "treatment_history": []
        }

        active_records = [r for r in pest_records if r.status in ["open", "in_treatment"]]
        resolved_records = [r for r in pest_records if r.status in ["resolved", "closed"]]

        factors["active_records_count"] = len(active_records)
        factors["resolved_records_count"] = len(resolved_records)

        if active_records:
            factors["active_pest_disease"] = True
            latest = max(active_records, key=lambda r: r.discovery_time)
            factors["related_pest_disease"] = {
                "record_id": latest.id,
                "severity": latest.severity.value,
                "symptoms": [s.value for s in latest.symptoms.symptom_types],
                "discovery_time": latest.discovery_time.isoformat()
            }

        if log.related_pest_disease_record_id:
            related = next(
                (r for r in pest_records if r.id == log.related_pest_disease_record_id),
                None
            )
            if related:
                factors["related_pest_disease"] = {
                    "record_id": related.id,
                    "severity": related.severity.value,
                    "status": related.status,
                    "treatment_count": len(related.treatment_history)
                }

        return factors

    def _analyze_anomaly_factors(
        self,
        log: MaintenanceLog,
        watering_history: List[WateringReport],
        plant_info: Optional[Dict]
    ) -> Dict[str, Any]:
        factors = {
            "has_anomalies": False,
            "anomaly_types": [],
            "anomaly_count": 0,
            "operation_addresses_anomaly": None
        }

        if watering_history and plant_info:
            last_report = watering_history[-1]

            temp_anomaly = (
                last_report.temperature > plant_info["optimal_temp_max"] + 5
                or last_report.temperature < plant_info["optimal_temp_min"] - 5
            )
            humidity_anomaly = (
                last_report.humidity > plant_info["optimal_humidity_max"] + 10
                or last_report.humidity < plant_info["optimal_humidity_min"] - 10
            )
            moisture_anomaly = (
                last_report.soil_moisture is not None
                and (last_report.soil_moisture > 85 or last_report.soil_moisture < 15)
            )

            if temp_anomaly:
                factors["anomaly_types"].append("温度异常")
                factors["anomaly_count"] += 1
            if humidity_anomaly:
                factors["anomaly_types"].append("湿度异常")
                factors["anomaly_count"] += 1
            if moisture_anomaly:
                factors["anomaly_types"].append("土壤湿度异常")
                factors["anomaly_count"] += 1

            factors["has_anomalies"] = factors["anomaly_count"] > 0

            if log.operation_type in [
                MaintenanceOperationType.TEMPERATURE_ADJUSTMENT,
                MaintenanceOperationType.HUMIDITY_ADJUSTMENT,
                MaintenanceOperationType.WATERING
            ]:
                op_type_map = {
                    MaintenanceOperationType.TEMPERATURE_ADJUSTMENT: "温度异常",
                    MaintenanceOperationType.HUMIDITY_ADJUSTMENT: "湿度异常",
                    MaintenanceOperationType.WATERING: "土壤湿度异常"
                }
                if op_type_map.get(log.operation_type) in factors["anomaly_types"]:
                    factors["operation_addresses_anomaly"] = True
                else:
                    factors["operation_addresses_anomaly"] = False

        return factors

    def _find_similar_operations(
        self,
        log: MaintenanceLog,
        window_days: int = 14
    ) -> Tuple[List[Dict[str, Any]], int]:
        similar_ops: List[Dict[str, Any]] = []

        target_ids = [log.target_id]
        if log.target_type == "zone":
            target_ids.extend([
                l.target_id for l in self.logs_db.values()
                if l.target_type == "plant" and l.execution_time >= log.execution_time - timedelta(days=window_days)
            ])

        for other_log in self.logs_db.values():
            if other_log.id == log.id:
                continue
            if other_log.target_id not in target_ids:
                continue
            if other_log.operation_type != log.operation_type:
                continue

            days_diff = abs((other_log.execution_time - log.execution_time).total_seconds() / 86400)
            if days_diff <= window_days:
                similar_ops.append({
                    "log": other_log,
                    "days_diff": round(days_diff, 1)
                })

        similar_ops.sort(key=lambda x: x["days_diff"])
        return similar_ops, len(similar_ops)

    def _calculate_effectiveness_score(
        self,
        log: MaintenanceLog,
        env_factors: Dict,
        water_factors: Dict,
        pest_factors: Dict,
        anomaly_factors: Dict
    ) -> Tuple[int, OperationEffectiveness]:
        score = 50

        if log.status_after and log.status_after.health_score is not None:
            if log.status_before.health_score is not None:
                health_change = log.status_after.health_score - log.status_before.health_score
                score += health_change * 0.8

        if water_factors.get("operation_aligns_with_need"):
            score += 10
        elif water_factors.get("operation_aligns_with_need") is False:
            score -= 15

        if anomaly_factors.get("operation_addresses_anomaly"):
            score += 10
        elif anomaly_factors.get("operation_addresses_anomaly") is False:
            score -= 10

        if env_factors.get("environmental_stress"):
            if log.operation_type in [
                MaintenanceOperationType.VENTILATION,
                MaintenanceOperationType.HUMIDITY_ADJUSTMENT,
                MaintenanceOperationType.TEMPERATURE_ADJUSTMENT,
                MaintenanceOperationType.LIGHT_ADJUSTMENT
            ]:
                score += 10

        if pest_factors.get("active_pest_disease"):
            if log.operation_type in [
                MaintenanceOperationType.SPRAYING,
                MaintenanceOperationType.PEST_CONTROL,
                MaintenanceOperationType.DISEASE_TREATMENT,
                MaintenanceOperationType.REMOVE_DISEASED_LEAVES,
                MaintenanceOperationType.ISOLATION
            ]:
                score += 10

        if log.observation_result:
            if "好转" in log.observation_result or "改善" in log.observation_result or "有效" in log.observation_result:
                score += 10
            elif "恶化" in log.observation_result or "无效" in log.observation_result or "加重" in log.observation_result:
                score -= 15

        score = max(0, min(100, score))

        if score >= 80:
            effectiveness = OperationEffectiveness.VERY_EFFECTIVE
        elif score >= 60:
            effectiveness = OperationEffectiveness.EFFECTIVE
        elif score >= 40:
            effectiveness = OperationEffectiveness.PARTIALLY_EFFECTIVE
        elif score >= 20:
            effectiveness = OperationEffectiveness.INEFFECTIVE
        else:
            effectiveness = OperationEffectiveness.HARMFUL

        return int(score), effectiveness

    def _determine_recovery_trend(
        self,
        log: MaintenanceLog,
        similar_ops: List[Dict],
        watering_history: List[WateringReport]
    ) -> Tuple[RecoveryTrend, float]:
        if not log.status_after or log.status_after.health_score is None:
            return RecoveryTrend.FLUCTUATING, 0.3

        recent_ops = sorted(similar_ops, key=lambda x: x["log"].execution_time)

        scores = []
        if log.status_before.health_score is not None:
            scores.append(log.status_before.health_score)
        if log.status_after.health_score is not None:
            scores.append(log.status_after.health_score)

        for obs in log.follow_up_observations:
            hs = obs.get("current_status", {}).get("health_score")
            if hs is not None:
                scores.append(hs)

        if len(scores) < 2:
            return RecoveryTrend.STABLE, 0.5

        recent_scores = scores[-3:]
        if len(recent_scores) >= 2:
            first_avg = sum(recent_scores[:len(recent_scores)//2]) / (len(recent_scores)//2)
            last_avg = sum(recent_scores[len(recent_scores)//2:]) / len(recent_scores[len(recent_scores)//2:])
            trend_diff = last_avg - first_avg

            confidence = min(0.9, 0.5 + len(recent_scores) * 0.1)

            if trend_diff >= 10:
                return RecoveryTrend.IMPROVING, confidence
            elif trend_diff <= -10:
                return RecoveryTrend.DETERIORATING, confidence
            elif abs(trend_diff) < 5:
                return RecoveryTrend.STABLE, confidence

        return RecoveryTrend.FLUCTUATING, 0.4

    def _collect_supporting_evidence(
        self,
        log: MaintenanceLog,
        env_factors: Dict,
        water_factors: Dict,
        pest_factors: Dict,
        anomaly_factors: Dict
    ) -> List[str]:
        evidence = []

        if log.status_after and log.status_before:
            if log.status_after.health_score and log.status_before.health_score:
                if log.status_after.health_score > log.status_before.health_score:
                    evidence.append(
                        f"健康评分从 {log.status_before.health_score} 提升至 {log.status_after.health_score}"
                    )
            if log.status_after.has_new_growth:
                evidence.append("出现新生长迹象")

        if water_factors.get("operation_aligns_with_need"):
            evidence.append("操作与植物水分需求匹配")

        if anomaly_factors.get("operation_addresses_anomaly"):
            evidence.append("操作针对性解决了已识别的异常问题")

        if log.observation_result:
            if "好转" in log.observation_result or "改善" in log.observation_result:
                evidence.append(f"观察结果: {log.observation_result}")

        if pest_factors.get("active_pest_disease") and log.operation_type in [
            MaintenanceOperationType.SPRAYING, MaintenanceOperationType.PEST_CONTROL
        ]:
            evidence.append("病虫害防治操作与当前病虫害问题匹配")

        if log.follow_up_observations:
            for obs in log.follow_up_observations[-2:]:
                hs = obs.get("current_status", {}).get("health_score")
                if hs and hs >= 60:
                    evidence.append(f"后续观察显示健康评分维持在 {hs}")

        return evidence

    def _collect_contradicting_evidence(
        self,
        log: MaintenanceLog,
        env_factors: Dict,
        water_factors: Dict,
        pest_factors: Dict,
        anomaly_factors: Dict
    ) -> List[str]:
        evidence = []

        if log.status_after and log.status_before:
            if log.status_after.health_score and log.status_before.health_score:
                if log.status_after.health_score < log.status_before.health_score:
                    evidence.append(
                        f"健康评分从 {log.status_before.health_score} 下降至 {log.status_after.health_score}"
                    )

        if water_factors.get("operation_aligns_with_need") is False:
            evidence.append("操作与植物水分需求不匹配，可能存在过度浇水")

        if log.observation_result:
            if "恶化" in log.observation_result or "无效" in log.observation_result:
                evidence.append(f"观察结果显示: {log.observation_result}")

        if env_factors.get("environmental_stress"):
            stress = "、".join(env_factors.get("stress_factors", []))
            if stress:
                evidence.append(f"存在环境胁迫因素: {stress}，可能影响操作效果")

        if pest_factors.get("active_pest_disease") and log.operation_type not in [
            MaintenanceOperationType.SPRAYING, MaintenanceOperationType.PEST_CONTROL,
            MaintenanceOperationType.DISEASE_TREATMENT, MaintenanceOperationType.ISOLATION
        ]:
            evidence.append("存在活跃的病虫害问题，但操作未包含病虫害防治措施")

        return evidence

    def _generate_recommendation(
        self,
        log: MaintenanceLog,
        is_effective: bool,
        has_duplicates: bool,
        recovery_trend: RecoveryTrend,
        effectiveness_score: int,
        plant_info: Optional[Dict]
    ) -> Tuple[AdjustmentType, str]:
        if recovery_trend == RecoveryTrend.DETERIORATING:
            if has_duplicates:
                return AdjustmentType.CHANGE_METHOD, "连续相似操作无效且状态持续恶化，建议立即更换养护方案"
            elif effectiveness_score < 30:
                return AdjustmentType.ROLLBACK_OPERATION, "操作可能造成负面影响，建议回退该操作并评估损害"
            else:
                return AdjustmentType.UPGRADE_TREATMENT, "状态持续恶化，建议升级处置强度或寻求专业帮助"

        if has_duplicates and not is_effective:
            return AdjustmentType.MODIFY_SCHEME, "多次重复相似操作未见明显效果，建议调整养护策略"

        if recovery_trend == RecoveryTrend.IMPROVING and is_effective:
            return AdjustmentType.CONTINUE_CURRENT, "操作有效且恢复趋势良好，建议继续当前方案"

        if recovery_trend == RecoveryTrend.STABLE:
            if is_effective:
                return AdjustmentType.CONTINUE_CURRENT, "状态稳定且操作有效，建议继续观察"
            else:
                return AdjustmentType.MODIFY_SCHEME, "状态未见明显改善，建议微调养护方案"

        if recovery_trend == RecoveryTrend.FLUCTUATING:
            return AdjustmentType.REQUEST_HUMAN_INSPECTION, "状态波动不定，建议进行人工检查以确定最佳方案"

        return AdjustmentType.CONTINUE_CURRENT, "继续观察，根据后续状态再做调整"

    def _calculate_next_review_time(
        self,
        log: MaintenanceLog,
        recovery_trend: RecoveryTrend,
        effectiveness: OperationEffectiveness,
        zone: Optional[Zone]
    ) -> datetime:
        now = datetime.now()

        if recovery_trend == RecoveryTrend.DETERIORATING:
            return now + timedelta(days=1)
        elif effectiveness == OperationEffectiveness.HARMFUL:
            return now + timedelta(days=1)
        elif effectiveness == OperationEffectiveness.INEFFECTIVE:
            return now + timedelta(days=2)
        elif recovery_trend == RecoveryTrend.IMPROVING:
            return now + timedelta(days=5)
        elif recovery_trend == RecoveryTrend.STABLE:
            return now + timedelta(days=7)
        else:
            return now + timedelta(days=3)

    def _generate_review_focus(
        self,
        log: MaintenanceLog,
        recovery_trend: RecoveryTrend,
        effectiveness: OperationEffectiveness
    ) -> List[str]:
        focus = ["整体健康状态变化", "叶片状态", "生长迹象"]

        if recovery_trend == RecoveryTrend.DETERIORATING:
            focus.extend([
                "症状是否加重",
                "是否出现新的异常",
                "操作是否造成额外损害"
            ])
        elif recovery_trend == RecoveryTrend.IMPROVING:
            focus.extend([
                "改善是否持续",
                "是否有新生长",
                "病虫害迹象是否消退"
            ])

        if log.operation_type in [
            MaintenanceOperationType.SPRAYING,
            MaintenanceOperationType.PEST_CONTROL,
            MaintenanceOperationType.DISEASE_TREATMENT
        ]:
            focus.extend([
                "病虫害迹象是否消失",
                "是否有药害迹象"
            ])

        if log.operation_type == MaintenanceOperationType.WATERING:
            focus.append("土壤湿度是否恢复正常")

        if log.operation_type == MaintenanceOperationType.FERTILIZING:
            focus.extend(["新叶生长情况", "是否有烧根迹象"])

        return list(set(focus))

    def _generate_risk_warnings(
        self,
        log: MaintenanceLog,
        has_duplicates: bool,
        recovery_trend: RecoveryTrend,
        env_factors: Dict,
        water_factors: Dict
    ) -> List[Dict[str, Any]]:
        warnings = []

        if has_duplicates:
            warnings.append({
                "risk_type": "repeated_ineffective_operations",
                "risk_level": RiskLevel.HIGH.value,
                "message": "短期内多次执行相似操作，可能导致植物胁迫或药物抗性",
                "suggestion": "暂停重复操作，评估当前方案有效性后再决定下一步"
            })

        if recovery_trend == RecoveryTrend.DETERIORATING:
            warnings.append({
                "risk_type": "condition_worsening",
                "risk_level": RiskLevel.HIGH.value,
                "message": "植物状态持续恶化，需立即干预",
                "suggestion": "建议更换养护方案或寻求专业人员检查"
            })

        if log.effectiveness == OperationEffectiveness.HARMFUL:
            warnings.append({
                "risk_type": "harmful_operation",
                "risk_level": RiskLevel.EXTREME.value,
                "message": "该操作可能对植物造成了损害",
                "suggestion": "立即停止该操作，评估损害程度并采取补救措施"
            })

        if water_factors.get("overwatering_risk") and log.operation_type == MaintenanceOperationType.WATERING:
            warnings.append({
                "risk_type": "overwatering_risk",
                "risk_level": RiskLevel.MEDIUM.value,
                "message": "土壤湿度过高，继续浇水可能导致烂根",
                "suggestion": "暂停浇水，待土壤干燥后再考虑补水"
            })

        if env_factors.get("environmental_stress"):
            stress = "、".join(env_factors.get("stress_factors", []))
            if stress:
                warnings.append({
                    "risk_type": "environmental_stress",
                    "risk_level": RiskLevel.MEDIUM.value,
                    "message": f"环境胁迫可能影响操作效果: {stress}",
                    "suggestion": "优先改善环境条件，再进行养护操作"
                })

        return warnings

    def _calculate_overall_confidence(
        self,
        log: MaintenanceLog,
        watering_history: List[WateringReport],
        pest_records: List,
        plant_info: Optional[Dict]
    ) -> float:
        confidence = 0.5

        if log.status_after and log.status_after.health_score is not None:
            confidence += 0.15
        if log.status_before and log.status_before.health_score is not None:
            confidence += 0.1
        if log.observation_result:
            confidence += 0.05
        if log.follow_up_observations:
            confidence += min(0.2, len(log.follow_up_observations) * 0.05)
        if watering_history:
            confidence += 0.1
        if plant_info:
            confidence += 0.05

        return min(0.98, confidence)

    def _generate_explanation(
        self,
        log: MaintenanceLog,
        is_effective: bool,
        effectiveness: OperationEffectiveness,
        recovery_trend: RecoveryTrend,
        recommendation: str,
        plant: Optional[Plant]
    ) -> str:
        target_name = plant.name if plant else f"目标 {log.target_id}"

        effect_desc = {
            OperationEffectiveness.VERY_EFFECTIVE: "非常有效",
            OperationEffectiveness.EFFECTIVE: "有效",
            OperationEffectiveness.PARTIALLY_EFFECTIVE: "部分有效",
            OperationEffectiveness.INEFFECTIVE: "无效",
            OperationEffectiveness.HARMFUL: "有害",
            OperationEffectiveness.PENDING: "待评估"
        }

        trend_desc = {
            RecoveryTrend.IMPROVING: "持续改善",
            RecoveryTrend.STABLE: "保持稳定",
            RecoveryTrend.DETERIORATING: "持续恶化",
            RecoveryTrend.FLUCTUATING: "波动不定"
        }

        parts = [
            f"【{target_name}】养护操作分析报告：",
            f"操作类型为{log.operation_type.value}，",
            f"评估结果为{effect_desc.get(effectiveness, '未知')}，",
            f"恢复趋势{trend_desc.get(recovery_trend, '未知')}。"
        ]

        if is_effective:
            parts.append("当前操作对植物有积极作用。")
        else:
            parts.append("当前操作效果不明显，需要关注。")

        parts.append(f"建议：{recommendation}")

        return "".join(parts)

    def _reassess_effectiveness(self, log: MaintenanceLog) -> None:
        if not log.follow_up_observations:
            return

        observations = log.follow_up_observations
        latest = observations[-1]
        latest_hs = latest.get("current_status", {}).get("health_score")

        if latest_hs is not None and log.status_before.health_score is not None:
            score_diff = latest_hs - log.status_before.health_score
            if score_diff >= 20:
                log.effectiveness = OperationEffectiveness.VERY_EFFECTIVE
            elif score_diff >= 10:
                log.effectiveness = OperationEffectiveness.EFFECTIVE
            elif score_diff >= 0:
                log.effectiveness = OperationEffectiveness.PARTIALLY_EFFECTIVE
            elif score_diff >= -10:
                log.effectiveness = OperationEffectiveness.INEFFECTIVE
            else:
                log.effectiveness = OperationEffectiveness.HARMFUL

    def _generate_plant_suggestions(
        self,
        plant_id: str,
        plants_db: Dict[str, Plant],
        zones_db: Dict[str, Zone]
    ) -> List[AdjustmentSuggestion]:
        suggestions: List[AdjustmentSuggestion] = []
        plant = plants_db.get(plant_id)
        if not plant:
            return suggestions

        plant_logs = self.get_plant_logs(plant_id, limit=20)
        if len(plant_logs) < 3:
            return suggestions

        recent_logs = [
            log for log in plant_logs
            if (datetime.now() - log.execution_time).days <= 30
        ]
        if len(recent_logs) < 3:
            return suggestions

        op_type_counter = Counter(log.operation_type for log in recent_logs)
        for op_type, count in op_type_counter.items():
            if count >= 3:
                ineffective_count = sum(
                    1 for log in recent_logs
                    if log.operation_type == op_type
                    and log.effectiveness in [OperationEffectiveness.INEFFECTIVE, OperationEffectiveness.HARMFUL]
                )
                if ineffective_count >= 2:
                    suggestion_id = str(uuid.uuid4())
                    suggestions.append(AdjustmentSuggestion(
                        suggestion_id=suggestion_id,
                        target_type="plant",
                        target_id=plant_id,
                        target_name=plant.name,
                        trigger_type="repeated_ineffective_operations",
                        trigger_description=f"30天内{count}次{op_type.value}操作，其中{ineffective_count}次无效",
                        current_scheme=f"持续使用{op_type.value}处理",
                        suggested_action=f"停止当前{op_type.value}方案，更换其他养护方法",
                        adjustment_type=AdjustmentType.CHANGE_METHOD,
                        reason=f"多次{op_type.value}未见效果，继续使用可能延误最佳治疗时机",
                        supporting_data={
                            "operation_type": op_type.value,
                            "total_operations": count,
                            "ineffective_count": ineffective_count,
                            "timeframe_days": 30
                        },
                        risk_level=RiskLevel.HIGH,
                        priority="high",
                        expected_outcome=f"更换方案后1-2周内可见改善",
                        alternative_options=[
                            {
                                "option": "升级处置强度",
                                "description": "增加药剂浓度或操作频率",
                                "risk": "可能造成药害或植物胁迫"
                            },
                            {
                                "option": "请求人工检查",
                                "description": "请专业人员诊断具体问题",
                                "risk": "需要额外时间和费用"
                            }
                        ],
                        generated_at=datetime.now()
                    ))

        status_series = []
        for log in sorted(recent_logs, key=lambda l: l.execution_time):
            if log.status_after and log.status_after.health_score is not None:
                status_series.append(log.status_after.health_score)
            elif log.status_before.health_score is not None:
                status_series.append(log.status_before.health_score)

        if len(status_series) >= 3:
            is_decreasing = all(
                status_series[i] >= status_series[i+1]
                for i in range(len(status_series) - 1)
            )
            total_decrease = status_series[0] - status_series[-1]

            if is_decreasing and total_decrease >= 15:
                suggestion_id = str(uuid.uuid4())
                suggestions.append(AdjustmentSuggestion(
                    suggestion_id=suggestion_id,
                    target_type="plant",
                    target_id=plant_id,
                    target_name=plant.name,
                    trigger_type="continuous_deterioration",
                    trigger_description=f"健康评分持续下降{total_decrease}分",
                    current_scheme="现有养护方案",
                    suggested_action="立即暂停所有非必要操作，进行全面诊断",
                    adjustment_type=AdjustmentType.REQUEST_HUMAN_INSPECTION,
                    reason=f"连续{len(status_series)}次记录显示健康状况持续恶化，现有方案未能控制",
                    supporting_data={
                        "health_score_series": status_series,
                        "total_decrease": total_decrease,
                        "records_analyzed": len(status_series)
                    },
                    risk_level=RiskLevel.EXTREME,
                    priority="critical",
                    expected_outcome="通过专业诊断找出根本原因，制定针对性方案",
                    alternative_options=[
                        {
                            "option": "回退最近操作",
                            "description": "撤销最近2次可能有害的操作",
                            "risk": "可能无法解决根本问题"
                        },
                        {
                            "option": "升级到更强效的方案",
                            "description": "使用更强力的处置措施",
                            "risk": "可能造成进一步伤害"
                        }
                    ],
                    generated_at=datetime.now()
                ))

        return suggestions

    def _generate_zone_suggestions(
        self,
        zone_id: str,
        plants_db: Dict[str, Plant],
        zones_db: Dict[str, Zone]
    ) -> List[AdjustmentSuggestion]:
        suggestions: List[AdjustmentSuggestion] = []
        zone = zones_db.get(zone_id)
        if not zone:
            return suggestions

        plant_ids = set(zone.plant_ids)
        if len(plant_ids) < 2:
            return suggestions

        zone_logs = self.get_zone_logs(zone_id, limit=50)
        plant_logs = [
            log for log in self.logs_db.values()
            if log.target_type == "plant" and log.target_id in plant_ids
        ]
        all_logs = zone_logs + plant_logs

        recent_logs = [
            log for log in all_logs
            if (datetime.now() - log.execution_time).days <= 21
        ]

        op_type_by_plant: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
        for log in recent_logs:
            if log.target_type == "plant":
                op_type_by_plant[log.target_id][log.operation_type.value].append(log)

        common_ineffective_ops: Dict[str, List[str]] = defaultdict(list)
        for plant_id, ops in op_type_by_plant.items():
            for op_type, logs in ops.items():
                ineffective = [
                    log for log in logs
                    if log.effectiveness in [OperationEffectiveness.INEFFECTIVE, OperationEffectiveness.HARMFUL]
                ]
                if len(ineffective) >= 1 and len(logs) >= 1:
                    common_ineffective_ops[op_type].append(plant_id)

        for op_type, affected_plants in common_ineffective_ops.items():
            if len(affected_plants) >= 2:
                affected_plant_names = [
                    plants_db[pid].name for pid in affected_plants
                    if pid in plants_db
                ]
                suggestion_id = str(uuid.uuid4())
                suggestions.append(AdjustmentSuggestion(
                    suggestion_id=suggestion_id,
                    target_type="zone",
                    target_id=zone_id,
                    target_name=zone.name,
                    trigger_type="zone_wide_ineffective_treatment",
                    trigger_description=f"分区内{len(affected_plants)}株植物{op_type}无效",
                    current_scheme=f"对多株植物执行{op_type}",
                    suggested_action=f"检查分区环境条件，重新评估{op_type}方案的适用性",
                    adjustment_type=AdjustmentType.MODIFY_SCHEME,
                    reason=f"多株植物对{op_type}反应不佳，可能存在共同的环境问题或方案不适用",
                    supporting_data={
                        "operation_type": op_type,
                        "affected_plant_count": len(affected_plants),
                        "affected_plants": affected_plant_names,
                        "timeframe_days": 21
                    },
                    risk_level=RiskLevel.HIGH,
                    priority="high",
                    expected_outcome="改善分区环境后，植物状态应在2周内改善",
                    alternative_options=[
                        {
                            "option": "分区环境整改",
                            "description": "检查并改善通风、温湿度等环境条件",
                            "risk": "可能需要设备投入"
                        },
                        {
                            "option": "分株差异化处理",
                            "description": "根据每株植物具体情况制定个性化方案",
                            "risk": "增加管理复杂度"
                        }
                    ],
                    generated_at=datetime.now()
                ))

        plant_statuses: Dict[str, List[int]] = defaultdict(list)
        for log in plant_logs:
            hs = None
            if log.status_after and log.status_after.health_score is not None:
                hs = log.status_after.health_score
            elif log.status_before.health_score is not None:
                hs = log.status_before.health_score
            if hs is not None:
                plant_statuses[log.target_id].append(hs)

        deteriorating_plants = []
        for plant_id, scores in plant_statuses.items():
            if len(scores) >= 2:
                if scores[-1] < scores[0] - 10:
                    plant = plants_db.get(plant_id)
                    if plant:
                        deteriorating_plants.append(plant.name)

        if len(deteriorating_plants) >= 2:
            suggestion_id = str(uuid.uuid4())
            suggestions.append(AdjustmentSuggestion(
                suggestion_id=suggestion_id,
                target_type="zone",
                target_id=zone_id,
                target_name=zone.name,
                trigger_type="zone_wide_deterioration",
                trigger_description=f"分区内{len(deteriorating_plants)}株植物状态持续恶化",
                current_scheme="现有分区养护方案",
                suggested_action="立即检查分区环境，考虑是否存在传染性病虫害或严重环境问题",
                adjustment_type=AdjustmentType.REQUEST_HUMAN_INSPECTION,
                reason=f"多株植物同时出现健康下降，可能存在分区级别的严重问题",
                supporting_data={
                    "deteriorating_plant_count": len(deteriorating_plants),
                    "deteriorating_plants": deteriorating_plants
                },
                risk_level=RiskLevel.EXTREME,
                priority="critical",
                expected_outcome="通过全面检查找出问题根源，防止扩散",
                alternative_options=[
                    {
                        "option": "紧急隔离",
                        "description": "将状态较差的植物移出分区隔离",
                        "risk": "可能中断现有生态平衡"
                    },
                    {
                        "option": "全分区消毒",
                        "description": "对分区环境和所有植物进行预防性消毒",
                        "risk": "可能对健康植物造成影响"
                    }
                ],
                generated_at=datetime.now()
            ))

        return suggestions

    def _identify_problematic_patterns(
        self,
        zone: Zone,
        plant_ids: set
    ) -> List[Dict[str, Any]]:
        patterns = []
        all_logs = [
            log for log in self.logs_db.values()
            if log.target_id in plant_ids or log.target_id == zone.id
        ]

        if not all_logs:
            return patterns

        recent_logs = [
            log for log in all_logs
            if (datetime.now() - log.execution_time).days <= 30
        ]

        if len(recent_logs) >= 5:
            ineffective_ratio = sum(
                1 for log in recent_logs
                if log.effectiveness in [OperationEffectiveness.INEFFECTIVE, OperationEffectiveness.HARMFUL]
            ) / len(recent_logs)

            if ineffective_ratio >= 0.5:
                patterns.append({
                    "pattern_type": "high_ineffective_rate",
                    "description": f"近30天操作无效率达{int(ineffective_ratio * 100)}%",
                    "severity": "high",
                    "suggestion": "全面审视当前养护方案，考虑系统性调整"
                })

        op_counter = Counter(log.operation_type.value for log in recent_logs)
        for op, count in op_counter.items():
            if count >= 5:
                patterns.append({
                    "pattern_type": "overuse_of_operation",
                    "description": f"操作「{op}」使用频率过高（{count}次/30天）",
                    "severity": "medium",
                    "suggestion": "评估是否存在过度养护，适当减少操作频率"
                })

        return patterns

    def get_statistics(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None
    ) -> Dict[str, Any]:
        logs = list(self.logs_db.values())

        if target_type and target_id:
            logs = [
                log for log in logs
                if log.target_type == target_type and log.target_id == target_id
            ]

        total = len(logs)
        effectiveness_dist = Counter(log.effectiveness.value for log in logs)
        operation_dist = Counter(log.operation_type.value for log in logs)

        last_7_days = [
            log for log in logs
            if (datetime.now() - log.execution_time).days <= 7
        ]
        last_30_days = [
            log for log in logs
            if (datetime.now() - log.execution_time).days <= 30
        ]

        return {
            "total_logs": total,
            "effectiveness_distribution": dict(effectiveness_dist),
            "operation_type_distribution": dict(operation_dist),
            "last_7_days_count": len(last_7_days),
            "last_30_days_count": len(last_30_days),
            "follow_up_observations_total": sum(
                len(log.follow_up_observations) for log in logs
            ),
            "last_updated": datetime.now().isoformat()
        }
