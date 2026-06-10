from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import uuid
from collections import Counter

from models.pest_disease import (
    PestDiseaseCreate, PestDiseaseRecord, PestDiseaseAnalysis,
    RiskLevel, SeverityLevel, SymptomType, DiseaseType, PestType,
    TreatmentStep, QuarantineAdvice, ReviewReminder, ZoneSpreadRisk,
    ActionableAdvice, TreatmentUpdate
)
from models import Plant, WateringReport
from models.zone import Zone
from watering_engine import WateringEngine
from plant_database import get_plant_info


class PestDiseaseService:
    def __init__(self, watering_engine: WateringEngine):
        self.records_db: Dict[str, PestDiseaseRecord] = {}
        self.watering_engine = watering_engine

    def create_record(self, data: PestDiseaseCreate) -> PestDiseaseRecord:
        record_id = str(uuid.uuid4())
        now = datetime.now()

        record = PestDiseaseRecord(
            id=record_id,
            **data.model_dump(),
            created_at=now,
            updated_at=now
        )

        self.records_db[record_id] = record
        return record

    def get_record(self, record_id: str) -> Optional[PestDiseaseRecord]:
        return self.records_db.get(record_id)

    def get_plant_records(self, plant_id: str) -> List[PestDiseaseRecord]:
        return [r for r in self.records_db.values() if r.plant_id == plant_id]

    def get_zone_records(self, zone_id: str, zones_db: Dict[str, Zone]) -> List[PestDiseaseRecord]:
        zone = zones_db.get(zone_id)
        if not zone:
            return []
        
        zone_plant_ids = set(zone.plant_ids)
        return [r for r in self.records_db.values() if r.plant_id in zone_plant_ids]

    def get_all_records(self, status: Optional[str] = None, limit: int = 100) -> List[PestDiseaseRecord]:
        records = list(self.records_db.values())
        if status:
            records = [r for r in records if r.status == status]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def update_record_status(self, record_id: str, status: str, notes: Optional[str] = None) -> Optional[PestDiseaseRecord]:
        record = self.records_db.get(record_id)
        if not record:
            return None

        record.status = status
        record.updated_at = datetime.now()
        
        if notes:
            record.treatment_history.append({
                "action": f"状态变更为: {status}",
                "notes": notes,
                "time": datetime.now().isoformat()
            })

        return record

    def add_treatment(self, update: TreatmentUpdate) -> Optional[PestDiseaseRecord]:
        record = self.records_db.get(update.record_id)
        if not record:
            return None

        record.treatment_history.append({
            "action": update.action_taken,
            "effectiveness": update.effectiveness,
            "notes": update.notes,
            "time": update.treatment_time.isoformat()
        })
        
        if update.effectiveness == "improved":
            record.status = "in_treatment"
        elif update.effectiveness == "worsened":
            record.severity = SeverityLevel.SEVERE
        
        record.updated_at = datetime.now()
        return record

    def analyze_pest_disease(
        self,
        record: PestDiseaseRecord,
        plant: Plant,
        zone: Optional[Zone],
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant]
    ) -> PestDiseaseAnalysis:
        plant_info = get_plant_info(plant.species)
        history = self.watering_engine.get_plant_history(plant.id)
        last_report = history[-1] if history else None

        environmental_factors = self._analyze_environmental_factors(
            plant, zone, last_report, plant_info
        )
        watering_factors = self._analyze_watering_factors(
            plant, history, plant_info
        )

        risk_score, risk_level = self._calculate_risk_level(
            record, environmental_factors, watering_factors, plant_info
        )

        possible_causes = self._identify_possible_causes(
            record, environmental_factors, watering_factors, plant_info
        )

        quarantine_advice = self._generate_quarantine_advice(
            record, zone, risk_level, plants_db, zones_db
        )

        treatment_steps = self._generate_treatment_steps(
            record, risk_level, possible_causes, environmental_factors
        )

        review_reminder = self._generate_review_reminder(
            record, risk_level, treatment_steps
        )

        zone_spread_risk = self._analyze_zone_spread_risk(
            record, zone, zones_db, plants_db
        )

        actionable_advice = self._generate_actionable_advice(
            record, risk_level, environmental_factors, watering_factors,
            quarantine_advice, zone_spread_risk
        )

        explanation = self._generate_explanation(
            record, plant, risk_level, possible_causes, environmental_factors
        )

        confidence = self._calculate_confidence(record, history, plant_info)

        return PestDiseaseAnalysis(
            record_id=record.id,
            plant_id=plant.id,
            plant_name=plant.name,
            species=plant.species,
            zone_id=zone.id if zone else None,
            zone_name=zone.name if zone else None,
            risk_level=risk_level,
            overall_risk_score=risk_score,
            possible_causes=possible_causes,
            quarantine_advice=quarantine_advice,
            treatment_steps=treatment_steps,
            review_reminder=review_reminder,
            zone_spread_risk=zone_spread_risk,
            actionable_advice=actionable_advice,
            environmental_factors=environmental_factors,
            watering_factors=watering_factors,
            explanation=explanation,
            confidence=confidence
        )

    def _analyze_environmental_factors(
        self,
        plant: Plant,
        zone: Optional[Zone],
        last_report: Optional[WateringReport],
        plant_info: Optional[Dict]
    ) -> Dict[str, Any]:
        factors = {
            "current_humidity": None,
            "current_temperature": None,
            "humidity_optimal": True,
            "temperature_optimal": True,
            "ventilation_level": None,
            "light_level": None,
            "high_fungus_risk": False,
            "is_near_window": False,
            "zone_type": None
        }

        if last_report:
            factors["current_humidity"] = last_report.humidity
            factors["current_temperature"] = last_report.temperature

        if zone and zone.environment:
            factors["ventilation_level"] = zone.environment.ventilation.value if zone.environment.ventilation else None
            factors["light_level"] = zone.environment.light_level.value if zone.environment.light_level else None
            factors["is_near_window"] = zone.environment.is_near_window
            factors["zone_type"] = zone.zone_type.value

        if plant_info and last_report:
            if last_report.humidity > plant_info["optimal_humidity_max"] + 10:
                factors["humidity_optimal"] = False
                if last_report.humidity > 80:
                    factors["high_fungus_risk"] = True
            elif last_report.humidity < plant_info["optimal_humidity_min"] - 10:
                factors["humidity_optimal"] = False

            if last_report.temperature > plant_info["optimal_temp_max"] + 5:
                factors["temperature_optimal"] = False
            elif last_report.temperature < plant_info["optimal_temp_min"] - 5:
                factors["temperature_optimal"] = False

        if zone and zone.environment and zone.environment.ventilation:
            from models.zone import VentilationLevel
            if zone.environment.ventilation in [VentilationLevel.POOR, VentilationLevel.MODERATE]:
                if last_report and last_report.humidity > 70:
                    factors["high_fungus_risk"] = True

        return factors

    def _analyze_watering_factors(
        self,
        plant: Plant,
        history: List[WateringReport],
        plant_info: Optional[Dict]
    ) -> Dict[str, Any]:
        factors = {
            "has_history": len(history) > 0,
            "recent_watering_count": len(history),
            "avg_watering_interval": None,
            "root_rot_risk": "low",
            "soil_moisture": None,
            "days_since_last_watering": None,
            "overwatering_risk": False,
            "underwatering_risk": False
        }

        if history:
            last_report = history[-1]
            factors["soil_moisture"] = last_report.soil_moisture

            days_since = (datetime.now() - last_report.last_watering_time).total_seconds() / 86400
            factors["days_since_last_watering"] = round(days_since, 1)

            intervals = []
            for i in range(1, len(history)):
                interval = (history[i].last_watering_time - history[i-1].last_watering_time).total_seconds() / 86400
                if 0.5 <= interval <= 60:
                    intervals.append(interval)
            
            if intervals:
                factors["avg_watering_interval"] = round(sum(intervals) / len(intervals), 1)

            if plant_info and last_report.soil_moisture is not None:
                if last_report.soil_moisture > 80 and days_since < 3:
                    factors["overwatering_risk"] = True
                    rot_resistance = plant_info.get("rot_resistance", 0.5)
                    if rot_resistance < 0.4:
                        factors["root_rot_risk"] = "high"
                    elif rot_resistance < 0.6:
                        factors["root_rot_risk"] = "medium"

                if last_report.soil_moisture < 20 and days_since > plant_info["base_watering_interval_days"]:
                    factors["underwatering_risk"] = True

        return factors

    def _calculate_risk_level(
        self,
        record: PestDiseaseRecord,
        env_factors: Dict,
        water_factors: Dict,
        plant_info: Optional[Dict]
    ) -> Tuple[int, RiskLevel]:
        score = 0

        severity_scores = {
            SeverityLevel.MILD: 20,
            SeverityLevel.MODERATE: 40,
            SeverityLevel.SEVERE: 70,
            SeverityLevel.CRITICAL: 90
        }
        score += severity_scores.get(record.severity, 30)

        if record.symptoms.affected_percentage:
            score += record.symptoms.affected_percentage * 0.3

        if record.symptoms.has_necrotic_tissue:
            score += 15

        if record.symptoms.has_odor:
            score += 10

        if env_factors.get("high_fungus_risk"):
            score += 15

        if not env_factors.get("humidity_optimal"):
            score += 10

        if not env_factors.get("temperature_optimal"):
            score += 5

        if water_factors.get("root_rot_risk") == "high":
            score += 20
        elif water_factors.get("root_rot_risk") == "medium":
            score += 10

        if water_factors.get("overwatering_risk"):
            score += 10

        if record.pest_signs.has_pest:
            if record.pest_signs.pest_count == "swarm":
                score += 25
            elif record.pest_signs.pest_count == "many":
                score += 15
            else:
                score += 5

        if record.suspected_disease_type == DiseaseType.FUNGAL:
            if env_factors.get("high_fungus_risk"):
                score += 10

        score = min(100, score)

        if score >= 80:
            risk_level = RiskLevel.EXTREME
        elif score >= 60:
            risk_level = RiskLevel.HIGH
        elif score >= 35:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        return int(score), risk_level

    def _identify_possible_causes(
        self,
        record: PestDiseaseRecord,
        env_factors: Dict,
        water_factors: Dict,
        plant_info: Optional[Dict]
    ) -> List[Dict[str, Any]]:
        causes = []

        symptom_cause_map = {
            SymptomType.MOLD: [
                {"cause": "高湿度环境", "probability": 0.8, "related_factor": "humidity"},
                {"cause": "通风不良", "probability": 0.7, "related_factor": "ventilation"},
                {"cause": "真菌感染", "probability": 0.6, "related_factor": "disease"}
            ],
            SymptomType.YELLOW_LEAF: [
                {"cause": "浇水过多", "probability": 0.5, "related_factor": "watering"},
                {"cause": "营养缺乏", "probability": 0.4, "related_factor": "nutrition"},
                {"cause": "光照不足", "probability": 0.3, "related_factor": "light"}
            ],
            SymptomType.BLACK_SPOT: [
                {"cause": "真菌病害", "probability": 0.8, "related_factor": "disease"},
                {"cause": "高湿环境", "probability": 0.6, "related_factor": "humidity"},
                {"cause": "叶片积水", "probability": 0.5, "related_factor": "watering"}
            ],
            SymptomType.LEAF_CURL: [
                {"cause": "虫害侵袭", "probability": 0.6, "related_factor": "pest"},
                {"cause": "病毒感染", "probability": 0.4, "related_factor": "disease"},
                {"cause": "水分不足", "probability": 0.3, "related_factor": "watering"}
            ],
            SymptomType.WILT: [
                {"cause": "水分不足", "probability": 0.6, "related_factor": "watering"},
                {"cause": "根系腐烂", "probability": 0.5, "related_factor": "root_rot"},
                {"cause": "温度胁迫", "probability": 0.3, "related_factor": "temperature"}
            ],
            SymptomType.ROT: [
                {"cause": "根系腐烂", "probability": 0.9, "related_factor": "root_rot"},
                {"cause": "浇水过多", "probability": 0.8, "related_factor": "watering"},
                {"cause": "细菌感染", "probability": 0.5, "related_factor": "disease"}
            ]
        }

        seen_causes = set()
        for symptom in record.symptoms.symptom_types:
            if symptom in symptom_cause_map:
                for cause_info in symptom_cause_map[symptom]:
                    if cause_info["cause"] not in seen_causes:
                        probability = cause_info["probability"]

                        if cause_info["related_factor"] == "humidity" and env_factors.get("current_humidity"):
                            humidity = env_factors["current_humidity"]
                            if humidity > 75:
                                probability = min(0.95, probability + 0.15)
                            elif humidity < 50:
                                probability = max(0.1, probability - 0.3)

                        if cause_info["related_factor"] == "watering":
                            if water_factors.get("overwatering_risk"):
                                probability = min(0.95, probability + 0.2)
                            if water_factors.get("underwatering_risk"):
                                probability = min(0.95, probability + 0.15)

                        if cause_info["related_factor"] == "root_rot" and water_factors.get("root_rot_risk") == "high":
                            probability = min(0.95, probability + 0.2)

                        if cause_info["related_factor"] == "ventilation":
                            ventilation = env_factors.get("ventilation_level")
                            if ventilation == "poor":
                                probability = min(0.95, probability + 0.2)
                            elif ventilation == "excellent":
                                probability = max(0.1, probability - 0.3)

                        causes.append({
                            "cause": cause_info["cause"],
                            "probability": round(probability, 2),
                            "related_factor": cause_info["related_factor"],
                            "evidence": self._get_cause_evidence(cause_info, env_factors, water_factors)
                        })
                        seen_causes.add(cause_info["cause"])

        if record.pest_signs.has_pest:
            pest_cause = f"{record.pest_signs.pest_type.value if record.pest_signs.pest_type else '未知'}虫害"
            if pest_cause not in seen_causes:
                causes.append({
                    "cause": pest_cause,
                    "probability": 0.85,
                    "related_factor": "pest",
                    "evidence": f"发现虫害迹象，位置: {record.pest_signs.pest_location or '未指定'}"
                })

        if not causes:
            causes.append({
                "cause": "需要进一步诊断",
                "probability": 0.5,
                "related_factor": "unknown",
                "evidence": "症状不典型，建议专业诊断"
            })

        causes.sort(key=lambda x: x["probability"], reverse=True)
        return causes[:5]

    def _get_cause_evidence(
        self,
        cause_info: Dict,
        env_factors: Dict,
        water_factors: Dict
    ) -> str:
        factor = cause_info["related_factor"]
        
        if factor == "humidity":
            humidity = env_factors.get("current_humidity", "未知")
            return f"当前湿度: {humidity}%" if humidity is not None else "湿度数据不足"
        
        if factor == "watering":
            if water_factors.get("overwatering_risk"):
                return f"土壤湿度高({water_factors.get('soil_moisture', '未知')}%)，浇水频繁"
            if water_factors.get("underwatering_risk"):
                return f"土壤湿度低({water_factors.get('soil_moisture', '未知')}%)，缺水"
            return f"上次浇水: {water_factors.get('days_since_last_watering', '未知')}天前"
        
        if factor == "root_rot":
            return f"烂根风险: {water_factors.get('root_rot_risk', '未知')}"
        
        if factor == "ventilation":
            return f"通风状况: {env_factors.get('ventilation_level', '未知')}"
        
        return "基于症状模式识别"

    def _generate_quarantine_advice(
        self,
        record: PestDiseaseRecord,
        zone: Optional[Zone],
        risk_level: RiskLevel,
        plants_db: Dict[str, Plant],
        zones_db: Dict[str, Zone]
    ) -> QuarantineAdvice:
        needs_quarantine = False
        reason = ""
        duration = 7

        if risk_level in [RiskLevel.EXTREME, RiskLevel.HIGH]:
            needs_quarantine = True

        if record.pest_signs.has_pest and record.pest_signs.pest_count in ["many", "swarm"]:
            needs_quarantine = True

        if record.suspected_disease_type in [DiseaseType.FUNGAL, DiseaseType.BACTERIAL, DiseaseType.VIRAL]:
            if record.severity in [SeverityLevel.SEVERE, SeverityLevel.CRITICAL]:
                needs_quarantine = True

        if zone and len(zone.plant_ids) > 1:
            similar_cases = self._count_similar_symptoms_in_zone(record, zone, plants_db)
            if similar_cases >= 2:
                needs_quarantine = True
                reason = f"同分区已发现{similar_cases}例相似症状，存在传播风险"

        if needs_quarantine:
            if not reason:
                if record.pest_signs.has_pest:
                    reason = "存在虫害，可能传染其他植物"
                elif record.suspected_disease_type in [DiseaseType.FUNGAL, DiseaseType.BACTERIAL]:
                    reason = "存在传染性病害，需要隔离观察"
                else:
                    reason = "症状严重，需要隔离观察防止扩散"

            duration_map = {
                RiskLevel.EXTREME: 21,
                RiskLevel.HIGH: 14,
                RiskLevel.MEDIUM: 7,
                RiskLevel.LOW: 3
            }
            duration = duration_map.get(risk_level, 7)

            precautions = [
                "隔离期间避免与其他植物接触",
                "处理后及时洗手，避免交叉污染",
                "工具单独使用并消毒",
                "每日观察症状变化"
            ]

            if record.pest_signs.has_pest:
                precautions.append("检查叶背和茎部是否有虫卵")
                precautions.append("隔离区周围放置粘虫板")

            if record.suspected_disease_type == DiseaseType.FUNGAL:
                precautions.append("保持隔离区干燥通风")
                precautions.append("避免叶片积水")

            return QuarantineAdvice(
                needs_quarantine=True,
                reason=reason,
                recommended_location="通风良好、光照充足的独立区域",
                duration_days=duration,
                precautions=precautions
            )

        return QuarantineAdvice(
            needs_quarantine=False,
            reason="症状轻微，无明显传播风险",
            recommended_location="保持原位置观察",
            duration_days=0,
            precautions=["定期观察症状变化", "保持良好通风"]
        )

    def _count_similar_symptoms_in_zone(
        self,
        record: PestDiseaseRecord,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> int:
        zone_plant_ids = set(zone.plant_ids) - {record.plant_id}
        similar_count = 0

        for r in self.records_db.values():
            if r.plant_id in zone_plant_ids and r.status != "resolved":
                common_symptoms = set(r.symptoms.symptom_types) & set(record.symptoms.symptom_types)
                if len(common_symptoms) >= 1:
                    time_diff = abs((r.discovery_time - record.discovery_time).days)
                    if time_diff <= 14:
                        similar_count += 1

        return similar_count

    def _generate_treatment_steps(
        self,
        record: PestDiseaseRecord,
        risk_level: RiskLevel,
        possible_causes: List[Dict],
        env_factors: Dict
    ) -> List[TreatmentStep]:
        steps = []
        step_num = 1

        primary_cause = possible_causes[0] if possible_causes else None

        if primary_cause and primary_cause["related_factor"] == "pest":
            steps.append(TreatmentStep(
                step=step_num,
                action="物理清除虫害",
                description="用清水冲洗叶片，特别是叶背和茎部；可用软刷轻轻刷除可见虫害",
                urgency="immediate",
                estimated_duration="15分钟"
            ))
            step_num += 1

            steps.append(TreatmentStep(
                step=step_num,
                action="施用杀虫药剂",
                description="根据虫害类型选择合适的杀虫剂，如吡虫啉、苦参碱等；按照说明稀释后均匀喷施，重点喷施叶背",
                urgency="immediate",
                estimated_duration="20分钟"
            ))
            step_num += 1

        if primary_cause and primary_cause["related_factor"] in ["disease", "humidity", "ventilation"]:
            if SymptomType.MOLD in record.symptoms.symptom_types or SymptomType.BLACK_SPOT in record.symptoms.symptom_types:
                steps.append(TreatmentStep(
                    step=step_num,
                    action="清除受感染组织",
                    description="用消毒剪刀剪除所有受感染的叶片和枝条，剪切位置应在健康组织以下2cm处",
                    urgency="immediate",
                    estimated_duration="15分钟"
                ))
                step_num += 1

                steps.append(TreatmentStep(
                    step=step_num,
                    action="施用杀菌剂",
                    description="喷施广谱杀菌剂如多菌灵、代森锰锌等；7-10天后重复喷施一次",
                    urgency="immediate",
                    estimated_duration="20分钟"
                ))
                step_num += 1

        if primary_cause and primary_cause["related_factor"] == "root_rot":
            steps.append(TreatmentStep(
                step=step_num,
                action="检查根系",
                description="将植物脱盆，检查根系状况；剪除所有软烂发黑的根系，切口涂抹多菌灵消毒",
                urgency="immediate",
                estimated_duration="30分钟"
            ))
            step_num += 1

            steps.append(TreatmentStep(
                step=step_num,
                action="更换盆土",
                description="使用经过消毒的新盆土，确保排水良好；新土建议添加珍珠岩或蛭石增加透气性",
                urgency="soon",
                estimated_duration="30分钟"
            ))
            step_num += 1

        if env_factors.get("high_fungus_risk") or not env_factors.get("humidity_optimal"):
            steps.append(TreatmentStep(
                step=step_num,
                action="改善环境条件",
                description="增加通风，降低空气湿度；避免叶面喷水；确保光照充足",
                urgency="immediate",
                estimated_duration="持续进行"
            ))
            step_num += 1

        if record.symptoms.affected_percentage and record.symptoms.affected_percentage > 30:
            steps.append(TreatmentStep(
                step=step_num,
                action="整株消毒",
                description="可用稀释的高锰酸钾溶液或多菌灵溶液浸泡整株30分钟，晾干后重新定植",
                urgency="soon",
                estimated_duration="1小时"
            ))
            step_num += 1

        steps.append(TreatmentStep(
            step=step_num,
            action="隔离观察",
            description="将植物移至隔离区域，单独养护；每日观察症状变化",
            urgency="immediate",
            estimated_duration="持续观察"
        ))
        step_num += 1

        review_days = {RiskLevel.EXTREME: 2, RiskLevel.HIGH: 3, RiskLevel.MEDIUM: 5, RiskLevel.LOW: 7}
        steps.append(TreatmentStep(
            step=step_num,
            action="定期复查",
            description=f"每{review_days.get(risk_level, 3)}天复查一次，评估治疗效果；如症状加重需及时调整方案",
            urgency="scheduled",
            estimated_duration="10分钟/次"
        ))

        return steps

    def _generate_review_reminder(
        self,
        record: PestDiseaseRecord,
        risk_level: RiskLevel,
        treatment_steps: List[TreatmentStep]
    ) -> ReviewReminder:
        review_days_map = {
            RiskLevel.EXTREME: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.MEDIUM: 5,
            RiskLevel.LOW: 7
        }

        review_days = review_days_map.get(risk_level, 3)
        review_time = datetime.now() + timedelta(days=review_days)

        review_focus = ["症状是否缓解", "是否有新的感染迹象", "整体生长状态"]
        
        if record.pest_signs.has_pest:
            review_focus.append("虫害是否完全清除")
            review_focus.append("是否有新的虫卵孵化")
        
        if record.suspected_disease_type == DiseaseType.FUNGAL:
            review_focus.append("霉斑是否继续扩散")
            review_focus.append("是否有新的斑点出现")
        
        if SymptomType.ROT in record.symptoms.symptom_types:
            review_focus.append("根系恢复情况")
            review_focus.append("叶片是否恢复挺立")

        follow_up_actions = [
            "继续当前治疗方案",
            "保持良好的通风环境",
            "避免浇水过多"
        ]

        return ReviewReminder(
            needs_review=True,
            review_time=review_time,
            review_focus=review_focus,
            follow_up_actions=follow_up_actions
        )

    def _analyze_zone_spread_risk(
        self,
        record: PestDiseaseRecord,
        zone: Optional[Zone],
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant]
    ) -> ZoneSpreadRisk:
        if not zone or len(zone.plant_ids) <= 1:
            return ZoneSpreadRisk(
                risk_level=RiskLevel.LOW,
                affected_plants_count=0,
                similar_symptoms_count=0,
                vulnerable_plants=[],
                spread_vector="无其他植物",
                preventive_measures=["无需特殊预防措施"]
            )

        similar_symptoms_count = self._count_similar_symptoms_in_zone(record, zone, plants_db)
        affected_plants_count = similar_symptoms_count

        zone_env = zone.environment
        spread_vector = "空气传播"
        high_risk = False

        if zone_env and zone_env.ventilation:
            from models.zone import VentilationLevel
            if zone_env.ventilation == VentilationLevel.POOR:
                high_risk = True
                spread_vector = "空气不流通加速孢子/害虫扩散"

        if record.pest_signs.has_pest:
            spread_vector = "虫害爬行/飞行传播"
            high_risk = True
        elif record.suspected_disease_type == DiseaseType.FUNGAL:
            spread_vector = "空气传播（真菌孢子）"
            if zone_env and zone_env.avg_humidity and zone_env.avg_humidity > 70:
                high_risk = True
        elif record.suspected_disease_type == DiseaseType.BACTERIAL:
            spread_vector = "接触传播（浇水、工具）"

        vulnerable_plants = []
        other_plant_ids = [pid for pid in zone.plant_ids if pid != record.plant_id]
        
        for pid in other_plant_ids:
            plant = plants_db.get(pid)
            if not plant:
                continue
            
            plant_info = get_plant_info(plant.species)
            vulnerability_score = 0.5
            
            if plant_info:
                rot_resistance = plant_info.get("rot_resistance", 0.5)
                if record.suspected_disease_type == DiseaseType.FUNGAL and rot_resistance < 0.4:
                    vulnerability_score = 0.9
                elif rot_resistance < 0.3:
                    vulnerability_score = 0.8

                if plant_info.get("optimal_humidity_min", 50) > 60:
                    if zone_env and zone_env.avg_humidity and zone_env.avg_humidity > 70:
                        vulnerability_score = min(1.0, vulnerability_score + 0.2)

            vulnerable_plants.append({
                "plant_id": pid,
                "plant_name": plant.name,
                "species": plant.species,
                "vulnerability_score": round(vulnerability_score, 2)
            })

        vulnerable_plants.sort(key=lambda x: x["vulnerability_score"], reverse=True)

        if high_risk and similar_symptoms_count >= 1:
            risk_level = RiskLevel.HIGH
        elif high_risk or similar_symptoms_count >= 2:
            risk_level = RiskLevel.HIGH if similar_symptoms_count >= 2 else RiskLevel.MEDIUM
        elif similar_symptoms_count == 1:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        preventive_measures = []
        
        if record.pest_signs.has_pest:
            preventive_measures.append("检查分区内其他植物是否有虫害迹象")
            preventive_measures.append("在分区内放置粘虫板进行监测")
            preventive_measures.append("对相邻植物进行预防性喷施")
        
        if record.suspected_disease_type == DiseaseType.FUNGAL:
            preventive_measures.append("改善分区通风条件")
            preventive_measures.append("降低空气湿度")
            preventive_measures.append("避免浇水时淋湿叶片")
            preventive_measures.append("对健康植物喷施保护性杀菌剂")
        
        preventive_measures.append("隔离患病植物，避免接触传播")
        preventive_measures.append("工具使用后彻底消毒")
        preventive_measures.append("每日巡查，早发现早处理")

        return ZoneSpreadRisk(
            risk_level=risk_level,
            affected_plants_count=affected_plants_count,
            similar_symptoms_count=similar_symptoms_count,
            vulnerable_plants=vulnerable_plants,
            spread_vector=spread_vector,
            preventive_measures=preventive_measures
        )

    def _generate_actionable_advice(
        self,
        record: PestDiseaseRecord,
        risk_level: RiskLevel,
        env_factors: Dict,
        water_factors: Dict,
        quarantine_advice: QuarantineAdvice,
        zone_spread_risk: ZoneSpreadRisk
    ) -> ActionableAdvice:
        advice = ActionableAdvice()

        if water_factors.get("root_rot_risk") in ["medium", "high"] or water_factors.get("overwatering_risk"):
            advice.suspend_watering = True
            advice.watering_suspend_days = 7 if water_factors.get("root_rot_risk") == "high" else 3

        if env_factors.get("high_fungus_risk") or not env_factors.get("humidity_optimal"):
            if env_factors.get("current_humidity", 0) > 70:
                advice.improve_ventilation = True
                ventilation_level = env_factors.get("ventilation_level")
                if ventilation_level == "poor":
                    advice.ventilation_advice = "通风极差，建议安装排气扇或移至通风良好的位置，每天通风至少2小时"
                elif ventilation_level == "moderate":
                    advice.ventilation_advice = "通风一般，建议每天开窗通风3-4次，每次30分钟"
                else:
                    advice.ventilation_advice = "保持当前通风条件，避免湿度过高"

        if quarantine_advice.needs_quarantine:
            advice.move_out_of_zone = True

        if (SymptomType.MOLD in record.symptoms.symptom_types or 
            SymptomType.BLACK_SPOT in record.symptoms.symptom_types or
            SymptomType.LEAF_SPOT in record.symptoms.symptom_types):
            advice.remove_infected_leaves = True
            if record.symptoms.affected_percentage and record.symptoms.affected_percentage > 50:
                advice.leaf_removal_advice = "受感染面积超过50%，建议重度修剪所有病叶病枝，剪切后伤口涂抹杀菌剂"
            else:
                advice.leaf_removal_advice = "及时剪除所有可见病斑的叶片，集中销毁，切勿堆肥"

        if SymptomType.ROT in record.symptoms.symptom_types or water_factors.get("root_rot_risk") == "high":
            advice.adjust_soil = True
            advice.soil_adjustment_advice = "根系存在腐烂风险，建议脱盆检查根系，剪除烂根后更换透气性好的新盆土，可添加珍珠岩、蛭石改善排水"

        if risk_level in [RiskLevel.EXTREME, RiskLevel.HIGH, RiskLevel.MEDIUM]:
            advice.needs_review_plan = True

        return advice

    def _generate_explanation(
        self,
        record: PestDiseaseRecord,
        plant: Plant,
        risk_level: RiskLevel,
        possible_causes: List[Dict],
        env_factors: Dict
    ) -> str:
        parts = []

        severity_desc = {
            SeverityLevel.MILD: "轻微",
            SeverityLevel.MODERATE: "中等",
            SeverityLevel.SEVERE: "严重",
            SeverityLevel.CRITICAL: "危急"
        }

        parts.append(f"【{plant.name}】病虫害诊断报告：")
        parts.append(f"上报症状为{severity_desc.get(record.severity, '未知')}级别，")
        
        if record.symptoms.symptom_types:
            symptoms_desc = "、".join([s.value for s in record.symptoms.symptom_types])
            parts.append(f"主要表现为{symptoms_desc}。")
        
        if possible_causes:
            top_cause = possible_causes[0]
            parts.append(f"最可能诱因是{top_cause['cause']}，概率{int(top_cause['probability'] * 100)}%。")
        
        risk_desc = {
            RiskLevel.EXTREME: "极高",
            RiskLevel.HIGH: "高",
            RiskLevel.MEDIUM: "中",
            RiskLevel.LOW: "低"
        }
        parts.append(f"综合风险等级为{risk_desc.get(risk_level, '未知')}。")

        if env_factors.get("high_fungus_risk"):
            parts.append("⚠️ 注意：当前环境湿度偏高且通风不足，真菌繁殖风险高，需特别注意防控。")
        
        if env_factors.get("current_humidity") and env_factors["current_humidity"] > 80:
            parts.append(f"当前湿度{env_factors['current_humidity']}%，建议尽快降低湿度。")

        return "".join(parts)

    def _calculate_confidence(
        self,
        record: PestDiseaseRecord,
        history: List[WateringReport],
        plant_info: Optional[Dict]
    ) -> float:
        confidence = 0.5

        if record.symptoms.symptom_types:
            confidence += 0.1

        if record.severity:
            confidence += 0.05

        if record.symptoms.affected_percentage:
            confidence += 0.05

        if record.pest_signs.has_pest and record.pest_signs.pest_type:
            confidence += 0.1

        if record.suspected_disease_type and record.suspected_disease_type != "unknown":
            confidence += 0.05

        if history:
            confidence += 0.1
            if len(history) >= 5:
                confidence += 0.05

        if plant_info:
            confidence += 0.1

        return min(0.98, confidence)

    def analyze_zone_pest_outbreak(
        self,
        zone: Zone,
        plants_db: Dict[str, Plant]
    ) -> Optional[Dict[str, Any]]:
        zone_records = self.get_zone_records(zone.id, {zone.id: zone})
        active_records = [r for r in zone_records if r.status in ["open", "in_treatment"]]

        if len(active_records) < 2:
            return None

        recent_records = [r for r in active_records if (datetime.now() - r.discovery_time).days <= 14]
        if len(recent_records) < 2:
            return None

        all_symptoms = []
        for r in recent_records:
            all_symptoms.extend(r.symptoms.symptom_types)

        symptom_counter = Counter(all_symptoms)
        common_symptoms = [s for s, c in symptom_counter.items() if c >= 2]

        if not common_symptoms:
            return None

        has_pest = any(r.pest_signs.has_pest for r in recent_records)
        has_fungal = any(r.suspected_disease_type == DiseaseType.FUNGAL for r in recent_records)

        outbreak_type = "unknown"
        if has_pest:
            outbreak_type = "虫害爆发"
        elif has_fungal:
            outbreak_type = "真菌病害爆发"
        else:
            outbreak_type = "群体性症状"

        severity_scores = {SeverityLevel.MILD: 1, SeverityLevel.MODERATE: 2, SeverityLevel.SEVERE: 3, SeverityLevel.CRITICAL: 4}
        avg_severity = sum(severity_scores.get(r.severity, 2) for r in recent_records) / len(recent_records)

        risk_level = RiskLevel.MEDIUM
        if len(recent_records) >= 3 and avg_severity >= 2.5:
            risk_level = RiskLevel.HIGH
        elif len(recent_records) >= 4:
            risk_level = RiskLevel.HIGH

        affected_plant_names = []
        for r in recent_records:
            plant = plants_db.get(r.plant_id)
            if plant:
                affected_plant_names.append(plant.name)

        return {
            "zone_id": zone.id,
            "zone_name": zone.name,
            "outbreak_type": outbreak_type,
            "risk_level": risk_level.value,
            "affected_count": len(recent_records),
            "affected_plants": affected_plant_names,
            "common_symptoms": [s.value for s in common_symptoms],
            "average_severity": round(avg_severity, 1),
            "timeframe_days": 14,
            "recommended_actions": [
                "立即隔离所有受感染植物",
                "对整个分区进行消毒处理",
                "改善通风条件，降低湿度",
                "对健康植物进行预防性喷药",
                "增加巡查频率，每日观察"
            ]
        }

    def get_statistics(self, zone_id: Optional[str] = None, zones_db: Optional[Dict[str, Zone]] = None) -> Dict[str, Any]:
        records = list(self.records_db.values())
        
        if zone_id and zones_db:
            zone_records = self.get_zone_records(zone_id, zones_db)
            records = zone_records

        total = len(records)
        open_count = sum(1 for r in records if r.status == "open")
        in_treatment_count = sum(1 for r in records if r.status == "in_treatment")
        resolved_count = sum(1 for r in records if r.status == "resolved")
        closed_count = sum(1 for r in records if r.status == "closed")

        severity_dist = Counter(r.severity.value for r in records)
        symptom_dist = Counter()
        for r in records:
            for s in r.symptoms.symptom_types:
                symptom_dist[s.value] += 1

        risk_levels = []
        for r in records:
            if r.severity in [SeverityLevel.SEVERE, SeverityLevel.CRITICAL]:
                risk_levels.append("high")
            elif r.severity == SeverityLevel.MODERATE:
                risk_levels.append("medium")
            else:
                risk_levels.append("low")
        risk_dist = Counter(risk_levels)

        return {
            "total_records": total,
            "status_distribution": {
                "open": open_count,
                "in_treatment": in_treatment_count,
                "resolved": resolved_count,
                "closed": closed_count
            },
            "severity_distribution": dict(severity_dist),
            "symptom_distribution": dict(symptom_dist),
            "risk_distribution": dict(risk_dist),
            "last_updated": datetime.now().isoformat()
        }
