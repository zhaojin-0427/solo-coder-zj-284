from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
import uuid
from collections import Counter, defaultdict

from models.consumable import (
    Consumable, ConsumableCreate, ConsumableUpdate,
    StockAdjustment, StockTransaction,
    ConsumableCategory,
    ConsumptionEstimate, StockRiskLevel, ExpiryRiskLevel,
    StockRiskAssessment, SubstituteFeasibility,
    ProcurementPriority, ProcurementItem, RestockSuggestion,
    ExpiryAlert, CostOverview, AdjustmentType as ConsumableAdjustmentType,
    AdjustmentSuggestion as ConsumableAdjustmentSuggestion, ConsumableAssessmentResponse
)
from models.zone import Zone
from models.schedule import PlantWateringTask
from models.pest_disease import PestDiseaseRecord, DiseaseType, PestType
from models.maintenance_log import MaintenanceLog, MaintenanceOperationType
from models import Plant
from watering_engine import WateringEngine


class ConsumableService:
    def __init__(self, watering_engine: WateringEngine):
        self.consumables_db: Dict[str, Consumable] = {}
        self.transactions_db: Dict[str, StockTransaction] = {}
        self.watering_engine = watering_engine
        self.consumption_history: Dict[str, List[Tuple[datetime, float, str]]] = defaultdict(list)

    def create_consumable(self, data: ConsumableCreate) -> Consumable:
        consumable_id = str(uuid.uuid4())
        now = datetime.now()

        consumable = Consumable(
            id=consumable_id,
            **data.model_dump(),
            created_at=now,
            updated_at=now
        )

        self.consumables_db[consumable_id] = consumable
        return consumable

    def get_consumable(self, consumable_id: str) -> Optional[Consumable]:
        return self.consumables_db.get(consumable_id)

    def get_all_consumables(
        self,
        category: Optional[ConsumableCategory] = None,
        low_stock_only: bool = False,
        critical_only: bool = False
    ) -> List[Consumable]:
        consumables = list(self.consumables_db.values())

        if category:
            consumables = [c for c in consumables if c.category == category]

        if low_stock_only:
            consumables = [c for c in consumables if c.current_stock <= c.min_safe_stock]

        if critical_only:
            consumables = [c for c in consumables if c.is_critical]

        consumables.sort(key=lambda c: c.updated_at, reverse=True)
        return consumables

    def update_consumable(
        self,
        consumable_id: str,
        data: ConsumableUpdate
    ) -> Optional[Consumable]:
        consumable = self.consumables_db.get(consumable_id)
        if not consumable:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(consumable, key, value)

        consumable.updated_at = datetime.now()
        return consumable

    def delete_consumable(self, consumable_id: str) -> bool:
        if consumable_id in self.consumables_db:
            del self.consumables_db[consumable_id]
            return True
        return False

    def adjust_stock(self, adjustment: StockAdjustment) -> Optional[StockTransaction]:
        consumable = self.consumables_db.get(adjustment.consumable_id)
        if not consumable:
            return None

        new_stock = consumable.current_stock + adjustment.quantity
        if new_stock < 0:
            return None

        consumable.current_stock = new_stock
        consumable.updated_at = datetime.now()

        transaction_id = str(uuid.uuid4())
        transaction = StockTransaction(
            id=transaction_id,
            **adjustment.model_dump(),
            created_at=datetime.now()
        )

        self.transactions_db[transaction_id] = transaction

        if adjustment.quantity < 0:
            self.consumption_history[adjustment.consumable_id].append(
                (adjustment.adjusted_at, abs(adjustment.quantity), adjustment.adjustment_type)
            )

        return transaction

    def get_transactions(
        self,
        consumable_id: Optional[str] = None,
        limit: int = 100
    ) -> List[StockTransaction]:
        transactions = list(self.transactions_db.values())

        if consumable_id:
            transactions = [t for t in transactions if t.consumable_id == consumable_id]

        transactions.sort(key=lambda t: t.adjusted_at, reverse=True)
        return transactions[:limit]

    def _get_scheduled_tasks(
        self,
        schedule_service,
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant],
        days: int
    ) -> List[PlantWateringTask]:
        all_tasks: List[PlantWateringTask] = []

        for zone in zones_db.values():
            try:
                schedule = schedule_service.generate_schedule(zone, plants_db, days)
                if schedule:
                    for day in schedule.schedule:
                        all_tasks.extend(day.tasks)
            except Exception:
                continue

        return all_tasks

    def _get_active_pest_records(
        self,
        pest_service,
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant]
    ) -> List[PestDiseaseRecord]:
        records = pest_service.get_all_records(status="open", limit=200)
        records.extend(pest_service.get_all_records(status="in_treatment", limit=200))
        return records

    def _get_recent_maintenance_logs(
        self,
        maintenance_service,
        days: int = 30
    ) -> List[MaintenanceLog]:
        cutoff = datetime.now() - timedelta(days=days)
        all_logs = []
        if hasattr(maintenance_service, 'logs_db'):
            for log in maintenance_service.logs_db.values():
                if log.execution_time >= cutoff:
                    all_logs.append(log)
        return all_logs

    def _get_zone_plants(
        self,
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant]
    ) -> Dict[str, List[Plant]]:
        zone_plants: Dict[str, List[Plant]] = {}
        for zone in zones_db.values():
            plants = [plants_db[pid] for pid in zone.plant_ids if pid in plants_db]
            zone_plants[zone.id] = plants
        return zone_plants

    def estimate_consumption(
        self,
        consumable: Consumable,
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant],
        schedule_service,
        pest_service,
        maintenance_service,
        days: int = 7
    ) -> ConsumptionEstimate:
        breakdown: List[Dict[str, Any]] = []
        total_consumption = 0.0
        confidence = 0.3

        zone_plants = self._get_zone_plants(zones_db, plants_db)
        applicable_plants: List[Plant] = []
        applicable_zone_ids = consumable.applicable_zones or []
        applicable_species = consumable.applicable_species or []

        if applicable_zone_ids:
            for zid in applicable_zone_ids:
                if zid in zone_plants:
                    for p in zone_plants[zid]:
                        if not applicable_species or p.species in applicable_species:
                            applicable_plants.append(p)
        else:
            for plants in zone_plants.values():
                for p in plants:
                    if not applicable_species or p.species in applicable_species:
                        applicable_plants.append(p)

        unique_plants = {}
        for p in applicable_plants:
            unique_plants[p.id] = p
        applicable_plants = list(unique_plants.values())

        cat = consumable.category
        plant_count = len(applicable_plants)

        if cat == ConsumableCategory.FERTILIZER:
            tasks = self._get_scheduled_tasks(schedule_service, zones_db, plants_db, days)
            fertilizer_days = 0
            for task in tasks:
                if task.plant_id in unique_plants:
                    fertilizer_days += 1

            rate = consumable.consumption_rate_per_plant or 5
            interval = consumable.typical_usage_interval_days or 14
            estimated_uses = max(1, (fertilizer_days / max(1, len(tasks) if tasks else 1))) * (days / max(1, interval)) * plant_count
            est = round(estimated_uses * rate, 2)
            total_consumption += est

            if plant_count > 0:
                breakdown.append({
                    "source": "fertilizing_schedule",
                    "description": f"基于{plant_count}株植物、{interval}天施肥周期预测",
                    "quantity": est,
                    "plant_count": plant_count
                })
                confidence = max(confidence, 0.6)

        elif cat == ConsumableCategory.NUTRIENT_SOLUTION:
            rate = consumable.consumption_rate_per_plant or 10
            interval = consumable.typical_usage_interval_days or 7
            est = round(plant_count * (days / max(1, interval)) * rate, 2)
            total_consumption += est

            if plant_count > 0:
                breakdown.append({
                    "source": "nutrient_schedule",
                    "description": f"基于{plant_count}株植物、{interval}天营养液使用周期预测",
                    "quantity": est,
                    "plant_count": plant_count
                })
                confidence = max(confidence, 0.55)

        elif cat in [ConsumableCategory.FUNGICIDE, ConsumableCategory.INSECTICIDE, ConsumableCategory.PESTICIDE]:
            active_records = self._get_active_pest_records(pest_service, zones_db, plants_db)
            relevant_records = []
            for r in active_records:
                if r.plant_id in unique_plants:
                    if cat == ConsumableCategory.FUNGICIDE and r.suspected_disease_type == DiseaseType.FUNGAL:
                        relevant_records.append(r)
                    elif cat == ConsumableCategory.INSECTICIDE and r.pest_signs.has_pest:
                        relevant_records.append(r)
                    elif cat == ConsumableCategory.PESTICIDE and (r.pest_signs.has_pest or r.suspected_disease_type in [DiseaseType.BACTERIAL, DiseaseType.FUNGAL]):
                        relevant_records.append(r)

            rate = consumable.consumption_rate_per_plant or 20
            treatments_per_record = 3
            est = round(len(relevant_records) * rate * treatments_per_record, 2)
            total_consumption += est

            if relevant_records:
                breakdown.append({
                    "source": "pest_disease_treatment",
                    "description": f"基于{len(relevant_records)}个活跃病虫害处置记录预测",
                    "quantity": est,
                    "record_count": len(relevant_records)
                })
                confidence = max(confidence, 0.7)

            outbreak_zones = 0
            for zone in zones_db.values():
                analysis = pest_service.analyze_zone_pest_outbreak(zone, plants_db)
                if analysis and (not applicable_zone_ids or zone.id in applicable_zone_ids):
                    outbreak_zones += 1
                    zone_plant_count = len([pid for pid in zone.plant_ids if pid in unique_plants])
                    preventive_est = round(zone_plant_count * rate * 0.5, 2)
                    total_consumption += preventive_est
                    breakdown.append({
                        "source": "preventive_spraying",
                        "description": f"{zone.name}区域病害爆发风险，需预防性喷施",
                        "quantity": preventive_est,
                        "zone_id": zone.id,
                        "zone_name": zone.name
                    })
                    confidence = max(confidence, 0.65)

        elif cat == ConsumableCategory.SOIL:
            recent_logs = self._get_recent_maintenance_logs(maintenance_service, days)
            repotting_logs = [l for l in recent_logs if l.operation_type == MaintenanceOperationType.REPOTTING]
            repot_count = len([l for l in repotting_logs if l.target_id in unique_plants])

            scheduled_repotting = max(0, int(plant_count * 0.05 * (days / 30)))
            total_repot = repot_count + scheduled_repotting

            rate = consumable.consumption_rate_per_plant or 2
            est = round(total_repot * rate, 2)
            total_consumption += est

            if total_repot > 0:
                breakdown.append({
                    "source": "repotting_schedule",
                    "description": f"基于{repot_count}次已记录换盆+{scheduled_repotting}次预测换盆",
                    "quantity": est,
                    "total_repot_count": total_repot
                })
                confidence = max(confidence, 0.5)

        elif cat == ConsumableCategory.CLAY_PELLETS:
            rate = consumable.consumption_rate_per_plant or 0.5
            soil_logs = self._get_recent_maintenance_logs(maintenance_service, days)
            soil_ops = [l for l in soil_logs if l.operation_type in [
                MaintenanceOperationType.REPOTTING, MaintenanceOperationType.SOIL_REPLACEMENT
            ]]
            op_count = len([l for l in soil_ops if l.target_id in unique_plants])
            scheduled_ops = max(0, int(plant_count * 0.05 * (days / 30)))

            est = round((op_count + scheduled_ops) * rate, 2)
            total_consumption += est

            if est > 0:
                breakdown.append({
                    "source": "soil_operations",
                    "description": f"基于{op_count + scheduled_ops}次换土/换盆操作预测",
                    "quantity": est
                })
                confidence = max(confidence, 0.45)

        elif cat == ConsumableCategory.SPRAYER_FILTER:
            pest_records = self._get_active_pest_records(pest_service, zones_db, plants_db)
            spray_logs = self._get_recent_maintenance_logs(maintenance_service, days)
            spray_count = len([l for l in spray_logs if l.operation_type in [
                MaintenanceOperationType.SPRAYING, MaintenanceOperationType.PEST_CONTROL,
                MaintenanceOperationType.DISEASE_TREATMENT
            ]])

            changes_per_30_days = max(1, (spray_count + len(pest_records)) / max(1, days / 30))
            est = round((changes_per_30_days / 10) * (days / 30), 2)
            total_consumption += est

            if est > 0:
                breakdown.append({
                    "source": "sprayer_maintenance",
                    "description": f"基于{spray_count}次喷施操作预估滤芯更换",
                    "quantity": est
                })
                confidence = max(confidence, 0.4)

        else:
            history = self.consumption_history.get(consumable.id, [])
            if history:
                recent = [h for h in history if (datetime.now() - h[0]).days <= 30]
                if recent:
                    avg_daily = sum(h[1] for h in recent) / max(1, 30)
                    est = round(avg_daily * days, 2)
                    total_consumption += est
                    breakdown.append({
                        "source": "historical_trend",
                        "description": f"基于30天历史消耗趋势预测",
                        "quantity": est,
                        "avg_daily": round(avg_daily, 4)
                    })
                    confidence = max(confidence, 0.5)

        projected_end = max(0, consumable.current_stock - total_consumption)

        return ConsumptionEstimate(
            consumable_id=consumable.id,
            consumable_name=consumable.name,
            category=consumable.category,
            days_horizon=days,
            estimated_consumption=round(total_consumption, 2),
            unit=consumable.unit,
            current_stock=consumable.current_stock,
            projected_end_stock=round(projected_end, 2),
            consumption_breakdown=breakdown,
            confidence=round(confidence, 2)
        )

    def assess_stock_risk(
        self,
        consumable: Consumable,
        consumption: ConsumptionEstimate,
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant]
    ) -> StockRiskAssessment:
        risk_factors: List[str] = []

        stock_ratio = consumable.current_stock / max(0.01, consumable.min_safe_stock)
        stock_score = 0
        stock_level = StockRiskLevel.SAFE

        if stock_ratio <= 0.2:
            stock_score = 100
            stock_level = StockRiskLevel.CRITICAL
            risk_factors.append(f"库存仅剩安全线的{int(stock_ratio*100)}%，严重不足")
        elif stock_ratio <= 0.5:
            stock_score = 70
            stock_level = StockRiskLevel.DANGER
            risk_factors.append(f"库存仅为安全线的{int(stock_ratio*100)}%，库存紧张")
        elif stock_ratio <= 1.0:
            stock_score = 40
            stock_level = StockRiskLevel.WARNING
            risk_factors.append("库存低于最低安全线")
        elif stock_ratio <= 1.5:
            stock_score = 20
            risk_factors.append("库存接近安全线")
        else:
            stock_score = 0

        projected_ratio = consumption.projected_end_stock / max(0.01, consumable.min_safe_stock)
        if consumption.estimated_consumption > 0:
            if projected_ratio <= 0:
                stock_score += 30
                stock_level = StockRiskLevel.CRITICAL
                risk_factors.append(f"按预测消耗，{consumption.days_horizon}天内库存将耗尽")
            elif projected_ratio <= 0.5:
                stock_score += 20
                if stock_level != StockRiskLevel.CRITICAL:
                    stock_level = StockRiskLevel.DANGER
                risk_factors.append(f"按预测消耗，{consumption.days_horizon}天后库存仅剩{int(projected_ratio*100)}%")

        if consumable.is_critical:
            stock_score += 15
            risk_factors.append("关键耗材，缺货将影响核心养护")

        expiry_score = 0
        expiry_level = ExpiryRiskLevel.FRESH
        days_to_expiry = None
        days_remaining_after_open = None

        if consumable.expiry_date:
            days_to_expiry = (consumable.expiry_date - date.today()).days
            if days_to_expiry <= 0:
                expiry_score = 100
                expiry_level = ExpiryRiskLevel.EXPIRED
                risk_factors.append(f"已过期{abs(days_to_expiry)}天")
            elif days_to_expiry <= 7:
                expiry_score = 80
                expiry_level = ExpiryRiskLevel.NEAR_EXPIRY
                risk_factors.append(f"距过期仅剩{days_to_expiry}天")
            elif days_to_expiry <= 30:
                expiry_score = 50
                expiry_level = ExpiryRiskLevel.NEAR_EXPIRY
                risk_factors.append(f"距过期仅剩{days_to_expiry}天，建议尽快使用")
            elif days_to_expiry <= 90:
                expiry_score = 20
                risk_factors.append(f"距过期还有{days_to_expiry}天")

        if consumable.opened_at and consumable.shelf_life_days_after_open:
            days_since_open = (datetime.now() - consumable.opened_at).days
            days_remaining_after_open = consumable.shelf_life_days_after_open - days_since_open
            if days_remaining_after_open <= 0:
                expiry_score = max(expiry_score, 90)
                expiry_level = ExpiryRiskLevel.EXPIRED
                risk_factors.append(f"开封后已超过保质期{abs(days_remaining_after_open)}天")
            elif days_remaining_after_open <= 7:
                expiry_score = max(expiry_score, 70)
                expiry_level = ExpiryRiskLevel.NEAR_EXPIRY
                risk_factors.append(f"开封后保质期仅剩{days_remaining_after_open}天")

        applicable_zone_ids = consumable.applicable_zones or []
        applicable_plants_count = 0
        for zid in applicable_zone_ids or list(zones_db.keys()):
            zone = zones_db.get(zid)
            if zone:
                if consumable.applicable_species:
                    for pid in zone.plant_ids:
                        plant = plants_db.get(pid)
                        if plant and plant.species in consumable.applicable_species:
                            applicable_plants_count += 1
                else:
                    applicable_plants_count += len(zone.plant_ids)

        affected_zones_count = len(applicable_zone_ids) if applicable_zone_ids else len(zones_db)

        overall_score = min(100, int(stock_score * 0.6 + expiry_score * 0.4))
        if overall_score >= 80:
            overall_level = "critical"
        elif overall_score >= 60:
            overall_level = "high"
        elif overall_score >= 30:
            overall_level = "medium"
        else:
            overall_level = "low"

        return StockRiskAssessment(
            consumable_id=consumable.id,
            consumable_name=consumable.name,
            category=consumable.category,
            current_stock=consumable.current_stock,
            min_safe_stock=consumable.min_safe_stock,
            stock_to_min_ratio=round(stock_ratio, 2),
            stock_risk_level=stock_level,
            stock_risk_score=min(100, stock_score),
            expiry_risk_level=expiry_level,
            expiry_risk_score=min(100, expiry_score),
            days_to_expiry=days_to_expiry,
            days_remaining_after_open=days_remaining_after_open,
            overall_risk_score=overall_score,
            overall_risk_level=overall_level,
            affected_tasks_count=None,
            affected_zones_count=affected_zones_count,
            affected_plants_count=applicable_plants_count,
            risk_factors=risk_factors
        )

    def assess_substitute_feasibility(self, consumable: Consumable) -> SubstituteFeasibility:
        alternatives_avail: List[Dict[str, Any]] = []
        alt_ids = consumable.alternatives or []

        for alt_id in alt_ids:
            alt = self.consumables_db.get(alt_id)
            if alt:
                alt_ratio = alt.current_stock / max(0.01, alt.min_safe_stock)
                alternatives_avail.append({
                    "consumable_id": alt.id,
                    "name": alt.name,
                    "category": alt.category.value,
                    "current_stock": alt.current_stock,
                    "unit": alt.unit,
                    "stock_adequate": alt_ratio >= 1.0,
                    "stock_to_min_ratio": round(alt_ratio, 2),
                    "specification": alt.specification
                })

        adequate_count = sum(1 for a in alternatives_avail if a["stock_adequate"])

        if adequate_count >= 2:
            feasibility = "high"
            feasibility_score = 80
        elif adequate_count >= 1:
            feasibility = "medium"
            feasibility_score = 50
        elif len(alternatives_avail) > 0:
            feasibility = "low"
            feasibility_score = 20
        else:
            feasibility = "none"
            feasibility_score = 0

        notes = None
        if feasibility == "none" and consumable.is_critical:
            notes = "关键耗材且无替代品，需重点保障供应"

        return SubstituteFeasibility(
            consumable_id=consumable.id,
            consumable_name=consumable.name,
            has_alternatives=len(alt_ids) > 0,
            alternative_count=len(alt_ids),
            alternatives_available=alternatives_avail,
            overall_feasibility=feasibility,
            feasibility_score=feasibility_score,
            notes=notes
        )

    def calculate_procurement_priority(
        self,
        consumable: Consumable,
        risk: StockRiskAssessment,
        consumption: ConsumptionEstimate,
        substitute: SubstituteFeasibility
    ) -> Tuple[ProcurementPriority, int, List[str]]:
        reasons: List[str] = []
        score = 0

        score += risk.overall_risk_score

        if consumable.is_critical:
            score += 25
            reasons.append("关键耗材，需优先保障")

        if substitute.feasibility_score == 0:
            score += 20
            reasons.append("无可用替代品")
        elif substitute.feasibility_score <= 20:
            score += 10
            reasons.append("替代品库存不足")

        if consumption.estimated_consumption > 0:
            coverage_days = None
            if consumption.estimated_consumption > 0 and consumption.days_horizon > 0:
                daily_rate = consumption.estimated_consumption / consumption.days_horizon
                if daily_rate > 0:
                    coverage_days = consumable.current_stock / daily_rate

            if coverage_days is not None:
                if coverage_days <= 3:
                    score += 30
                    reasons.append(f"当前库存仅够使用{int(coverage_days)}天")
                elif coverage_days <= 7:
                    score += 20
                    reasons.append(f"当前库存仅够使用{int(coverage_days)}天")
                elif coverage_days <= 14:
                    score += 10
                    reasons.append(f"库存预计可使用{int(coverage_days)}天")

        if risk.stock_risk_level in [StockRiskLevel.CRITICAL, StockRiskLevel.DANGER]:
            reasons.extend(risk.risk_factors)

        if risk.expiry_risk_level == ExpiryRiskLevel.EXPIRED:
            score += 15
            reasons.append("现有库存已过期，需重新采购")

        score = min(100, score)

        if score >= 80:
            priority = ProcurementPriority.URGENT
        elif score >= 60:
            priority = ProcurementPriority.HIGH
        elif score >= 30:
            priority = ProcurementPriority.MEDIUM
        else:
            priority = ProcurementPriority.LOW

        return priority, score, list(set(reasons))

    def generate_procurement_item(
        self,
        consumable: Consumable,
        risk: StockRiskAssessment,
        consumption: ConsumptionEstimate,
        substitute: SubstituteFeasibility
    ) -> Optional[ProcurementItem]:
        if consumable.current_stock >= consumable.min_safe_stock * 2 and consumption.projected_end_stock >= consumable.min_safe_stock:
            if risk.overall_risk_score < 30:
                return None

        priority, priority_score, reasons = self.calculate_procurement_priority(
            consumable, risk, consumption, substitute
        )

        if priority == ProcurementPriority.LOW and risk.overall_risk_level == "low":
            if consumption.projected_end_stock >= consumable.min_safe_stock:
                return None

        desired_coverage_days = 90
        if priority == ProcurementPriority.URGENT:
            desired_coverage_days = 30
        elif priority == ProcurementPriority.HIGH:
            desired_coverage_days = 60

        base_qty = max(consumable.min_safe_stock * 2, consumable.current_stock * 0.5)

        if consumption.days_horizon > 0 and consumption.estimated_consumption > 0:
            daily_consumption = consumption.estimated_consumption / consumption.days_horizon
            projected_need = daily_consumption * desired_coverage_days
            shortfall = max(0, projected_need - consumable.current_stock)
            recommended_qty = max(consumable.min_safe_stock, shortfall)
        else:
            recommended_qty = max(consumable.min_safe_stock, base_qty - consumable.current_stock)

        recommended_qty = max(consumable.min_safe_stock, round(recommended_qty, 2))

        unit_price = consumable.unit_price
        total_cost = round(unit_price * recommended_qty, 2) if unit_price else None

        urgency_days = None
        if priority == ProcurementPriority.URGENT:
            urgency_days = 3
        elif priority == ProcurementPriority.HIGH:
            urgency_days = 7

        return ProcurementItem(
            consumable_id=consumable.id,
            consumable_name=consumable.name,
            category=consumable.category,
            specification=consumable.specification,
            unit=consumable.unit,
            current_stock=consumable.current_stock,
            min_safe_stock=consumable.min_safe_stock,
            recommended_quantity=recommended_qty,
            unit_price=unit_price,
            estimated_total_cost=total_cost,
            supplier=consumable.supplier,
            priority=priority,
            priority_score=priority_score,
            reason=reasons,
            urgency_days=urgency_days
        )

    def generate_restock_suggestion(
        self,
        item: ProcurementItem,
        risk: StockRiskAssessment
    ) -> RestockSuggestion:
        today = date.today()

        if item.urgency_days:
            suggested_date = today
            deadline = today + timedelta(days=item.urgency_days)
        else:
            suggested_date = today + timedelta(days=3)
            deadline = today + timedelta(days=14)

        action = "立即采购"
        if item.priority == ProcurementPriority.URGENT:
            action = "紧急采购"
        elif item.priority == ProcurementPriority.LOW:
            action = "择机采购"

        evidence = {
            "current_stock": item.current_stock,
            "min_safe_stock": item.min_safe_stock,
            "stock_to_min_ratio": risk.stock_to_min_ratio,
            "overall_risk_level": risk.overall_risk_level,
            "overall_risk_score": risk.overall_risk_score,
            "expiry_risk": risk.expiry_risk_level.value
        }

        return RestockSuggestion(
            suggestion_id=str(uuid.uuid4()),
            consumable_id=item.consumable_id,
            consumable_name=item.consumable_name,
            category=item.category,
            action=action,
            recommended_quantity=item.recommended_quantity,
            unit=item.unit,
            priority=item.priority,
            estimated_cost=item.estimated_total_cost,
            reason=item.reason,
            evidence=evidence,
            supplier=item.supplier,
            suggested_purchase_date=suggested_date,
            deadline_date=deadline
        )

    def generate_expiry_alerts(self) -> List[ExpiryAlert]:
        alerts: List[ExpiryAlert] = []
        today = date.today()
        now = datetime.now()

        for c in self.consumables_db.values():
            alert_types = []
            severity = "low"
            days_to_expiry = None
            days_after_opened = None
            days_remaining_after_open = None

            if c.expiry_date:
                days_to_expiry = (c.expiry_date - today).days
                if days_to_expiry <= 0:
                    alert_types.append("expired")
                    severity = "critical"
                elif days_to_expiry <= 7:
                    alert_types.append("imminent_expiry")
                    severity = "high"
                elif days_to_expiry <= 30:
                    alert_types.append("near_expiry")
                    severity = "medium" if severity == "low" else severity
                elif days_to_expiry <= 90:
                    alert_types.append("approaching_expiry")

            if c.opened_at and c.shelf_life_days_after_open:
                days_after_opened = (now - c.opened_at).days
                days_remaining_after_open = c.shelf_life_days_after_open - days_after_opened
                if days_remaining_after_open <= 0:
                    alert_types.append("post_open_expired")
                    severity = "critical"
                elif days_remaining_after_open <= 7:
                    alert_types.append("post_open_near_expiry")
                    severity = "high" if severity in ["low", "medium"] else severity

            if not alert_types:
                continue

            history = self.consumption_history.get(c.id, [])
            recent = [h for h in history if (now - h[0]).days <= 30]
            recent_total = sum(h[1] for h in recent)
            avg_daily = recent_total / 30 if recent else 0

            if avg_daily > 0 and c.current_stock > 0:
                days_to_finish = c.current_stock / avg_daily
            else:
                days_to_finish = float('inf')

            can_use_up = False
            if c.expiry_date and days_to_expiry and days_to_expiry > 0:
                if days_to_finish != float('inf') and days_to_finish <= days_to_expiry * 0.8:
                    can_use_up = True
            elif not c.expiry_date and c.shelf_life_days_after_open and days_remaining_after_open and days_remaining_after_open > 0:
                if days_to_finish != float('inf') and days_to_finish <= days_remaining_after_open * 0.8:
                    can_use_up = True

            usage_freq = "frequent"
            if avg_daily == 0:
                usage_freq = "unused"
            elif avg_daily * 30 < c.min_safe_stock * 0.3:
                usage_freq = "rare"
            elif avg_daily * 30 < c.min_safe_stock:
                usage_freq = "occasional"

            suggestions: List[str] = []

            if "expired" in alert_types or "post_open_expired" in alert_types:
                suggestions.append("请立即停止使用，按规定处理过期产品")
                suggestions.append("记录报废并及时补充新库存")
                if c.current_stock > 0 and c.unit_price:
                    suggestions.append("注意记录报废损失成本")
            elif severity == "high":
                if can_use_up:
                    suggestions.append("可在过期前优先安排使用，避免浪费")
                else:
                    suggestions.append("即将过期，建议尽快安排集中使用")
                    suggestions.append("如无法用完，考虑分享或降级使用")
                suggestions.append("采购时注意控制数量避免积压")
            elif severity == "medium":
                suggestions.append("建议在近期养护计划中优先安排使用")
                suggestions.append("下次采购前评估实际需求量")

            if c.is_critical and severity in ["high", "critical"]:
                suggestions.append("关键耗材，请确保有替代方案或及时补货")

            estimated_waste = None
            if c.current_stock > 0 and c.unit_price:
                if "expired" in alert_types:
                    estimated_waste = round(c.current_stock * c.unit_price, 2)
                elif not can_use_up and severity in ["high", "medium"] and c.expiry_date and days_to_expiry:
                    if days_to_finish != float('inf') and days_to_finish > days_to_expiry:
                        unused_portion = max(0, 1 - (days_to_expiry / days_to_finish))
                        estimated_waste = round(c.current_stock * unused_portion * c.unit_price, 2)

            for at in alert_types:
                alerts.append(ExpiryAlert(
                    alert_id=str(uuid.uuid4()),
                    consumable_id=c.id,
                    consumable_name=c.name,
                    category=c.category,
                    specification=c.specification,
                    alert_type=at,
                    severity=severity,
                    expiry_date=c.expiry_date,
                    opened_at=c.opened_at,
                    days_to_expiry=days_to_expiry,
                    days_after_opened=days_after_opened,
                    days_remaining_after_open=days_remaining_after_open,
                    remaining_stock=c.current_stock,
                    unit=c.unit,
                    estimated_waste_cost=estimated_waste,
                    recent_usage_frequency=usage_freq,
                    can_be_used_up=can_use_up,
                    suggestions=suggestions
                ))

        alerts.sort(key=lambda a: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}[a.severity],
            a.days_to_expiry if a.days_to_expiry is not None else 999
        ))

        return alerts

    def generate_cost_overview(
        self,
        procurement_items: List[ProcurementItem],
        expiry_alerts: List[ExpiryAlert]
    ) -> CostOverview:
        total_inv_value = 0.0
        category_inv: Dict[str, float] = defaultdict(float)
        category_count: Dict[str, int] = defaultdict(int)

        for c in self.consumables_db.values():
            if c.unit_price and c.current_stock:
                val = c.current_stock * c.unit_price
                total_inv_value += val
                category_inv[c.category.value] += val
                category_count[c.category.value] += 1

        total_purchase_cost = sum(item.estimated_total_cost or 0 for item in procurement_items)
        waste_value = sum(a.estimated_waste_cost or 0 for a in expiry_alerts)

        monthly_consumption = 0.0
        for cid, history in self.consumption_history.items():
            c = self.consumables_db.get(cid)
            if c and c.unit_price:
                recent = [h for h in history if (datetime.now() - h[0]).days <= 30]
                qty = sum(h[1] for h in recent)
                monthly_consumption += qty * c.unit_price

        category_breakdown = []
        for cat in set(list(category_inv.keys()) + list(category_count.keys())):
            category_breakdown.append({
                "category": cat,
                "inventory_value": round(category_inv[cat], 2),
                "item_count": category_count[cat],
                "value_ratio": round(category_inv[cat] / max(0.01, total_inv_value) * 100, 1)
            })
        category_breakdown.sort(key=lambda x: x["inventory_value"], reverse=True)

        top_cost_items = []
        items_with_value = []
        for c in self.consumables_db.values():
            if c.unit_price and c.current_stock:
                items_with_value.append({
                    "consumable_id": c.id,
                    "name": c.name,
                    "category": c.category.value,
                    "stock_value": round(c.current_stock * c.unit_price, 2),
                    "current_stock": c.current_stock,
                    "unit": c.unit,
                    "unit_price": c.unit_price
                })
        items_with_value.sort(key=lambda x: x["stock_value"], reverse=True)
        top_cost_items = items_with_value[:10]

        efficiency_score = 80.0
        if total_inv_value > 0:
            waste_ratio = waste_value / total_inv_value
            efficiency_score = max(0, 100 - waste_ratio * 200)

            purchase_ratio = total_purchase_cost / max(0.01, total_inv_value)
            if purchase_ratio > 1.5:
                efficiency_score -= 10
            elif purchase_ratio > 1.0:
                efficiency_score -= 5

        saving_ops: List[Dict[str, Any]] = []

        if waste_value > 0:
            saving_ops.append({
                "type": "reduce_waste",
                "description": "减少临期耗材浪费",
                "potential_saving": round(waste_value, 2),
                "actions": ["集中使用临期耗材", "优化采购数量", "建立耗材轮换机制"]
            })

        overstocked = []
        for c in self.consumables_db.values():
            if c.unit_price and c.current_stock > c.min_safe_stock * 3:
                excess = c.current_stock - c.min_safe_stock * 2
                if excess * c.unit_price > 10:
                    overstocked.append({
                        "consumable_id": c.id,
                        "name": c.name,
                        "excess_qty": round(excess, 2),
                        "unit": c.unit,
                        "excess_value": round(excess * c.unit_price, 2)
                    })

        if overstocked:
            overstocked.sort(key=lambda x: x["excess_value"], reverse=True)
            total_overstock = sum(o["excess_value"] for o in overstocked)
            saving_ops.append({
                "type": "reduce_overstock",
                "description": "优化过高库存占用资金",
                "potential_saving": round(total_overstock * 0.3, 2),
                "actions": ["减少采购频率", "先消耗现有库存", "考虑小批量多次采购"],
                "top_overstocked": overstocked[:5]
            })

        if monthly_consumption > 0:
            saving_ops.append({
                "type": "batch_purchase",
                "description": "合并采购批次降低采购成本",
                "potential_saving": round(monthly_consumption * 0.05, 2),
                "actions": ["每月固定日期采购", "从同一供应商集中采购", "协商批量折扣"]
            })

        return CostOverview(
            total_inventory_value=round(total_inv_value, 2),
            total_estimated_purchase_cost=round(total_purchase_cost, 2),
            estimated_waste_value=round(waste_value, 2),
            monthly_consumption_value=round(monthly_consumption, 2) if monthly_consumption > 0 else None,
            category_breakdown=category_breakdown,
            top_cost_items=top_cost_items,
            cost_efficiency_score=round(efficiency_score, 1),
            saving_opportunities=saving_ops
        )

    def generate_adjustment_suggestions(
        self,
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant],
        schedule_service,
        pest_service,
        risk_assessments: List[StockRiskAssessment],
        procurement_items: List[ProcurementItem],
        consumptions: List[ConsumptionEstimate],
        substitutes: Dict[str, SubstituteFeasibility],
        expiry_alerts: List[ExpiryAlert]
    ) -> List[ConsumableAdjustmentSuggestion]:
        suggestions: List[ConsumableAdjustmentSuggestion] = []
        now = datetime.now()

        critical_shortages = [
            r for r in risk_assessments
            if r.overall_risk_level in ["critical", "high"]
            and r.stock_risk_level in [StockRiskLevel.CRITICAL, StockRiskLevel.DANGER]
        ]

        for risk in critical_shortages:
            consumable = self.consumables_db.get(risk.consumable_id)
            if not consumable:
                continue

            sub = substitutes.get(risk.consumable_id)
            urgent_items = [i for i in procurement_items if i.consumable_id == risk.consumable_id]
            item = urgent_items[0] if urgent_items else None

            affected_zones_info = []
            zone_ids = consumable.applicable_zones or list(zones_db.keys())
            for zid in zone_ids:
                zone = zones_db.get(zid)
                if zone:
                    affected_plants = 0
                    if consumable.applicable_species:
                        for pid in zone.plant_ids:
                            plant = plants_db.get(pid)
                            if plant and plant.species in consumable.applicable_species:
                                affected_plants += 1
                    else:
                        affected_plants = len(zone.plant_ids)

                    affected_zones_info.append({
                        "zone_id": zid,
                        "zone_name": zone.name,
                        "affected_plants_count": affected_plants
                    })

            affected_tasks_info = []
            try:
                for zid in zone_ids[:3]:
                    zone = zones_db.get(zid)
                    if zone:
                        tasks = self._get_scheduled_tasks(schedule_service, {zid: zone}, plants_db, 14)
                        relevant_tasks = [t for t in tasks if t.plant_id in (
                            [pid for pid in zone.plant_ids if (
                                not consumable.applicable_species or
                                (pid in plants_db and plants_db[pid].species in consumable.applicable_species)
                            )]
                        )]
                        if relevant_tasks:
                            affected_tasks_info.append({
                                "zone_id": zid,
                                "zone_name": zone.name,
                                "upcoming_tasks_count": len(relevant_tasks),
                                "next_task_date": relevant_tasks[0].scheduled_date.isoformat() if relevant_tasks else None
                            })
            except Exception:
                pass

            alt_actions = []
            if sub and sub.has_alternatives:
                alt_actions.append({
                    "action": "切换替代品",
                    "feasibility": sub.overall_feasibility,
                    "alternatives": sub.alternatives_available[:3]
                })
            alt_actions.append({
                "action": "延后非紧急操作",
                "description": "将非紧急养护操作延后至采购到货后"
            })

            priority = "critical" if risk.overall_risk_level == "critical" else "high"
            trigger = f"耗材{consumable.name}库存严重不足" if risk.overall_risk_level == "critical" else f"耗材{consumable.name}库存低于安全线"

            title = f"【紧急采购建议】{consumable.name}"
            desc = f"{consumable.name}({consumable.specification})当前库存{consumable.current_stock}{consumable.unit}，仅为安全线的{int(risk.stock_to_min_ratio*100)}%，无法支撑即将到来的养护任务。"
            if risk.affected_plants_count:
                desc += f"预计影响{risk.affected_plants_count}株植物。"

            recommended = "立即下单采购"
            if item:
                recommended += f" {item.recommended_quantity}{consumable.unit}"

            sup_data = {
                "current_stock": consumable.current_stock,
                "min_safe_stock": consumable.min_safe_stock,
                "stock_to_min_ratio": risk.stock_to_min_ratio,
                "overall_risk_score": risk.overall_risk_score,
                "is_critical": consumable.is_critical,
                "procurement_item": item.model_dump(mode="json") if item else None
            }

            risks = ["继续等待可能导致养护任务无法执行", "如无法及时采购可能影响植物健康"]
            if consumable.is_critical:
                risks.insert(0, "关键耗材缺货将严重影响核心养护流程")

            suggestions.append(ConsumableAdjustmentSuggestion(
                suggestion_id=str(uuid.uuid4()),
                suggestion_type=ConsumableAdjustmentType.EMERGENCY_PURCHASE if risk.overall_risk_level == "critical" else ConsumableAdjustmentType.ADVANCE_PURCHASE,
                title=title,
                description=desc,
                priority=priority,
                trigger_condition=trigger,
                affected_consumables=[{
                    "id": consumable.id,
                    "name": consumable.name,
                    "category": consumable.category.value,
                    "current_stock": consumable.current_stock,
                    "unit": consumable.unit
                }],
                affected_zones=affected_zones_info,
                affected_tasks=affected_tasks_info,
                recommended_action=recommended,
                alternative_actions=alt_actions,
                expected_outcome=f"采购到货后可保障未来{90 if not item else 30 if item.priority==ProcurementPriority.URGENT else 60}天的养护需求",
                potential_risks=risks,
                supporting_data=sup_data,
                explanation=desc + f" 综合风险评分{risk.overall_risk_score}/100。建议" + recommended + "。",
                confidence=min(1.0, risk.overall_risk_score / 100 + 0.2),
                generated_at=now
            ))

        critical_expiry = [a for a in expiry_alerts if a.severity in ["high", "critical"]]
        used_supplier_ids = set()
        frequent_pest_cats = defaultdict(int)

        for a in critical_expiry:
            consumable = self.consumables_db.get(a.consumable_id)
            if not consumable:
                continue

            active_pest = self._get_active_pest_records(pest_service, zones_db, plants_db)
            relevant_count = 0
            for r in active_pest:
                if consumable.category == ConsumableCategory.FUNGICIDE and r.suspected_disease_type == DiseaseType.FUNGAL:
                    relevant_count += 1
                    frequent_pest_cats[consumable.category.value] += 1
                elif consumable.category == ConsumableCategory.INSECTICIDE and r.pest_signs.has_pest:
                    relevant_count += 1
                    frequent_pest_cats[consumable.category.value] += 1

            if a.severity == "critical" and a.alert_type in ["expired", "post_open_expired"]:
                suggestions.append(ConsumableAdjustmentSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    suggestion_type=ConsumableAdjustmentType.SWITCH_ALTERNATIVE,
                    title=f"【停用警告】{a.consumable_name}已过期",
                    description=f"{consumable.name}({consumable.specification})已过期/开封过期，请立即停止使用并妥善处理。",
                    priority="high",
                    trigger_condition="耗材已过期",
                    affected_consumables=[{
                        "id": consumable.id,
                        "name": consumable.name,
                        "category": consumable.category.value,
                        "remaining_stock": a.remaining_stock,
                        "unit": a.unit,
                        "waste_cost": a.estimated_waste_cost
                    }],
                    affected_zones=[],
                    affected_tasks=[],
                    recommended_action="立即报废处理，并使用替代品或紧急采购新品",
                    alternative_actions=[{
                        "action": "使用替代品",
                        "alternatives": substitutes[a.consumable_id].alternatives_available if a.consumable_id in substitutes else []
                    }],
                    expected_outcome="避免使用过期产品对植物造成伤害",
                    potential_risks=["继续使用过期产品可能导致植物药害", "过期药剂效果大幅下降可能无法控制病虫害"],
                    supporting_data={
                        "alert_type": a.alert_type,
                        "days_to_expiry": a.days_to_expiry,
                        "days_remaining_after_open": a.days_remaining_after_open,
                        "estimated_waste": a.estimated_waste_cost
                    },
                    explanation=f"{consumable.name}已过期，必须立即停用。如有替代品请使用替代品，否则需紧急采购。",
                    confidence=0.95,
                    generated_at=now
                ))
            elif relevant_count >= 1 and a.severity == "high":
                suggestions.append(ConsumableAdjustmentSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    suggestion_type=ConsumableAdjustmentType.SWITCH_ALTERNATIVE,
                    title=f"【临期提醒】{a.consumable_name}临期但仍有频繁使用需求",
                    description=f"{consumable.name}即将过期但当前有{relevant_count}个活跃记录需要使用。" +
                                (f"按当前使用速度{'可' if a.can_be_used_up else '不可'}在过期前用完。" if a.can_be_used_up is not None else ""),
                    priority="medium",
                    trigger_condition="临期耗材被频繁用于处置",
                    affected_consumables=[{
                        "id": consumable.id,
                        "name": consumable.name,
                        "category": consumable.category.value,
                        "remaining_stock": a.remaining_stock,
                        "unit": a.unit,
                        "days_to_expiry": a.days_to_expiry,
                        "active_usage_count": relevant_count
                    }],
                    affected_zones=[],
                    affected_tasks=[],
                    recommended_action="优先集中使用临期库存，同时准备新品",
                    alternative_actions=[
                        {"action": "切换新批次/新品", "description": "如担心效果，直接启用新采购品"},
                        {"action": "混用方案", "description": "临期品与新品交替使用"}
                    ],
                    expected_outcome="在保证效果前提下尽量减少浪费",
                    potential_risks=["临期产品效果可能下降", "集中使用可能增加药害风险"],
                    supporting_data={
                        "days_to_expiry": a.days_to_expiry,
                        "active_usage_count": relevant_count,
                        "can_use_up_before_expiry": a.can_be_used_up
                    },
                    explanation=f"{consumable.name}临期且有{relevant_count}个活跃使用需求。建议优先使用临期品，但需注意效果观察，必要时切换新品。",
                    confidence=0.8,
                    generated_at=now
                ))

        zone_consumable_demand: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for con in consumptions:
            consumable = self.consumables_db.get(con.consumable_id)
            if not consumable:
                continue
            zone_ids = consumable.applicable_zones or list(zones_db.keys())
            per_zone = con.estimated_consumption / max(1, len(zone_ids))
            for zid in zone_ids:
                zone_consumable_demand[zid][con.consumable_id] += per_zone

        for zid, demands in zone_consumable_demand.items():
            zone = zones_db.get(zid)
            if not zone:
                continue

            high_demand_items = []
            total_demand_value = 0.0
            for cid, qty in demands.items():
                consumable = self.consumables_db.get(cid)
                if not consumable:
                    continue
                if qty > consumable.min_safe_stock * 0.3:
                    val = qty * (consumable.unit_price or 0)
                    high_demand_items.append({
                        "consumable_id": cid,
                        "name": consumable.name,
                        "category": consumable.category.value,
                        "demand_qty": round(qty, 2),
                        "unit": consumable.unit,
                        "demand_value": round(val, 2)
                    })
                    total_demand_value += val

            if len(high_demand_items) >= 3 and total_demand_value >= 50:
                high_demand_items.sort(key=lambda x: x["demand_value"], reverse=True)

                suggestions.append(ConsumableAdjustmentSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    suggestion_type=ConsumableAdjustmentType.MERGE_BATCH,
                    title=f"【合并采购建议】{zone.name}区域集中采购",
                    description=f"{zone.name}区域未来7天有{len(high_demand_items)}种耗材需求较大，建议合并采购以降低成本和物流时间。",
                    priority="medium",
                    trigger_condition="同分区植物集中需要相同养护物资",
                    affected_consumables=high_demand_items,
                    affected_zones=[{
                        "zone_id": zid,
                        "zone_name": zone.name,
                        "plants_count": len(zone.plant_ids)
                    }],
                    affected_tasks=[],
                    recommended_action=f"为{zone.name}区域单独准备一批物资，集中从同一供应商采购",
                    alternative_actions=[
                        {"action": "按时间批次采购", "description": "拆分为2-3个时间批次采购，避免库存积压"},
                        {"action": "全区域统一采购", "description": "将所有区域的相同耗材需求合并统一采购"}
                    ],
                    expected_outcome=f"预计可节省约{round(total_demand_value * 0.05, 2)}元采购成本，减少物流次数",
                    potential_risks=["集中采购可能占用更多资金", "需预留足够仓储空间"],
                    supporting_data={
                        "zone_id": zid,
                        "zone_name": zone.name,
                        "total_demand_value": round(total_demand_value, 2),
                        "items_count": len(high_demand_items)
                    },
                    explanation=f"{zone.name}区域近期有多种耗材同时需求，合并采购可享受批量折扣、减少物流时间和人力成本。建议与供应商沟通统一配送。",
                    confidence=0.75,
                    generated_at=now
                ))

        supplier_groups: Dict[str, List[ProcurementItem]] = defaultdict(list)
        for item in procurement_items:
            if item.supplier and item.supplier.name:
                if item.supplier.name not in used_supplier_ids:
                    supplier_groups[item.supplier.name].append(item)

        for supplier_name, items in supplier_groups.items():
            if len(items) >= 3:
                total_value = sum(i.estimated_total_cost or 0 for i in items)
                if total_value >= 100:
                    consumables_info = [{
                        "consumable_id": i.consumable_id,
                        "name": i.consumable_name,
                        "qty": i.recommended_quantity,
                        "unit": i.unit,
                        "value": i.estimated_total_cost
                    } for i in items]

                    highest_priority = min(
                        [{"urgent": 0, "high": 1, "medium": 2, "low": 3}[i.priority.value] for i in items]
                    )
                    priority_map = {0: "urgent", 1: "high", 2: "medium", 3: "low"}

                    suggestions.append(ConsumableAdjustmentSuggestion(
                        suggestion_id=str(uuid.uuid4()),
                        suggestion_type=ConsumableAdjustmentType.MERGE_BATCH,
                        title=f"【供应商合并】{supplier_name}批量采购",
                        description=f"供应商{supplier_name}有{len(items)}种耗材需采购，建议合并下单。",
                        priority=priority_map[highest_priority],
                        trigger_condition="同一供应商多品采购需求",
                        affected_consumables=consumables_info,
                        affected_zones=[],
                        affected_tasks=[],
                        recommended_action=f"从{supplier_name}一次性下单采购全部{len(items)}种耗材",
                        alternative_actions=[
                            {"action": "分紧急度下单", "description": "紧急品先下单，非紧急品等待凑单"}
                        ],
                        expected_outcome=f"预计节省{round(total_value * 0.08, 2)}元批量折扣，减少物流次数",
                        potential_risks=["部分物资可能到货时间不同", "需确认供应商库存"],
                        supporting_data={
                            "supplier": supplier_name,
                            "items_count": len(items),
                            "total_estimated_value": round(total_value, 2)
                        },
                        explanation=f"同一供应商{supplier_name}有多个采购需求，合并下单通常可获得5%-15%的批量折扣，并节省物流费用。",
                        confidence=0.85,
                        generated_at=now
                    ))
                    used_supplier_ids.add(supplier_name)

        non_urgent_items = [i for i in procurement_items if i.priority in [ProcurementPriority.LOW, ProcurementPriority.MEDIUM]]
        urgent_count = len([i for i in procurement_items if i.priority in [ProcurementPriority.URGENT, ProcurementPriority.HIGH]])
        if urgent_count >= 3 and len(non_urgent_items) >= 2:
            total_non_urgent_value = sum(i.estimated_total_cost or 0 for i in non_urgent_items)

            suggestions.append(ConsumableAdjustmentSuggestion(
                suggestion_id=str(uuid.uuid4()),
                suggestion_type=ConsumableAdjustmentType.DELAY_NON_URGENT,
                title="【延后建议】非紧急耗材延后采购",
                description=f"当前有{urgent_count}项紧急采购需优先处理，建议将{len(non_urgent_items)}项非紧急采购延后至下一个采购周期。",
                priority="low",
                trigger_condition="紧急采购项过多需优先处理",
                affected_consumables=[{
                    "consumable_id": i.consumable_id,
                    "name": i.consumable_name,
                    "recommended_qty": i.recommended_quantity,
                    "unit": i.unit,
                    "priority": i.priority.value,
                    "delayed_value": i.estimated_total_cost
                } for i in non_urgent_items],
                affected_zones=[],
                affected_tasks=[],
                recommended_action="将低/中优先级采购延后7-14天",
                alternative_actions=[
                    {"action": "部分延后", "description": "仅延后低优先级项，中优先级继续采购"},
                    {"action": "分批采购", "description": "紧急品本周到，非紧急品下周安排"}
                ],
                expected_outcome=f"释放约{round(total_non_urgent_value, 2)}元资金，集中保障紧急需求",
                potential_risks=["延后期间可能出现意外消耗导致短缺", "需密切监控库存变化"],
                supporting_data={
                    "urgent_count": urgent_count,
                    "non_urgent_count": len(non_urgent_items),
                    "delayed_total_value": round(total_non_urgent_value, 2)
                },
                explanation="当前紧急采购较多，建议集中资源优先保障紧急需求。非紧急耗材当前库存仍可支撑一段时间，延后采购风险较低。",
                confidence=0.7,
                generated_at=now
            ))

        suggestions.sort(key=lambda s: {
            "critical": 0, "high": 1, "medium": 2, "low": 3
        }[s.priority])

        return suggestions

    def comprehensive_assessment(
        self,
        zones_db: Dict[str, Zone],
        plants_db: Dict[str, Plant],
        schedule_service,
        pest_service,
        maintenance_service,
        horizon_days: int = 7
    ) -> ConsumableAssessmentResponse:
        consumables = self.get_all_consumables()
        now = datetime.now()

        consumption_estimates: List[ConsumptionEstimate] = []
        risk_assessments: List[StockRiskAssessment] = []
        substitute_feasibility: List[SubstituteFeasibility] = []
        procurement_items: List[ProcurementItem] = []
        restock_suggestions: List[RestockSuggestion] = []
        substitute_map: Dict[str, SubstituteFeasibility] = {}

        for c in consumables:
            con = self.estimate_consumption(
                c, zones_db, plants_db, schedule_service, pest_service,
                maintenance_service, horizon_days
            )
            consumption_estimates.append(con)

            risk = self.assess_stock_risk(c, con, zones_db, plants_db)
            risk_assessments.append(risk)

            sub = self.assess_substitute_feasibility(c)
            substitute_feasibility.append(sub)
            substitute_map[c.id] = sub

            item = self.generate_procurement_item(c, risk, con, sub)
            if item:
                procurement_items.append(item)
                restock_suggestions.append(self.generate_restock_suggestion(item, risk))

        procurement_items.sort(key=lambda i: i.priority_score, reverse=True)
        restock_suggestions.sort(key=lambda s: {
            "urgent": 0, "high": 1, "medium": 2, "low": 3
        }[s.priority.value])

        expiry_alerts = self.generate_expiry_alerts()
        cost_overview = self.generate_cost_overview(procurement_items, expiry_alerts)

        adjustment_suggestions = self.generate_adjustment_suggestions(
            zones_db, plants_db, schedule_service, pest_service,
            risk_assessments, procurement_items, consumption_estimates,
            substitute_map, expiry_alerts
        )

        total_at_risk = sum(1 for r in risk_assessments if r.overall_risk_level in ["critical", "high"])
        total_warning = sum(1 for r in risk_assessments if r.overall_risk_level == "medium")
        total_expiry_critical = sum(1 for a in expiry_alerts if a.severity in ["critical", "high"])
        total_procurement_urgent = sum(1 for i in procurement_items if i.priority == ProcurementPriority.URGENT)

        summary = {
            "horizon_days": horizon_days,
            "total_consumables": len(consumables),
            "total_at_risk": total_at_risk,
            "total_warning": total_warning,
            "total_expiry_alerts_critical": total_expiry_critical,
            "total_expiry_alerts_all": len(expiry_alerts),
            "total_procurement_items": len(procurement_items),
            "total_procurement_urgent": total_procurement_urgent,
            "total_adjustment_suggestions": len(adjustment_suggestions),
            "total_estimated_purchase_cost": cost_overview.total_estimated_purchase_cost,
            "total_inventory_value": cost_overview.total_inventory_value,
            "total_estimated_waste_value": cost_overview.estimated_waste_value,
            "cost_efficiency_score": cost_overview.cost_efficiency_score
        }

        return ConsumableAssessmentResponse(
            assessment_time=now,
            horizon_days=horizon_days,
            total_consumables=len(consumables),
            consumption_estimates=consumption_estimates,
            risk_assessments=risk_assessments,
            substitute_feasibility=substitute_feasibility,
            procurement_items=procurement_items,
            restock_suggestions=restock_suggestions,
            expiry_alerts=expiry_alerts,
            cost_overview=cost_overview,
            adjustment_suggestions=adjustment_suggestions,
            summary=summary
        )
