from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
from models import WateringReport, WateringPrediction, AnomalyAlert, MaintenanceSuggestion
from plant_database import (
    get_plant_info,
    get_pot_evaporation_coefficient,
    get_soil_retention_coefficient,
    get_season,
    PLANT_DATABASE
)


class WateringEngine:
    def __init__(self):
        self.watering_history: Dict[str, List[WateringReport]] = {}
        self.cached_predictions: Dict[str, Tuple[WateringPrediction, datetime]] = {}
        self.cached_alerts: Dict[str, List[AnomalyAlert]] = {}

    def add_report(self, report: WateringReport):
        if report.plant_id not in self.watering_history:
            self.watering_history[report.plant_id] = []
        self.watering_history[report.plant_id].append(report)
        self.watering_history[report.plant_id].sort(key=lambda r: r.report_time)
        
        if len(self.watering_history[report.plant_id]) > 100:
            self.watering_history[report.plant_id] = self.watering_history[report.plant_id][-100:]

    def get_plant_history(self, plant_id: str) -> List[WateringReport]:
        return self.watering_history.get(plant_id, [])

    def calculate_evaporation_rate(
        self,
        temperature: float,
        humidity: float,
        pot_material: str,
        soil_type: str,
        plant_species: str,
        light_intensity: Optional[float] = None
    ) -> float:
        pot_coeff = get_pot_evaporation_coefficient(pot_material)
        soil_coeff = get_soil_retention_coefficient(soil_type)
        
        plant_info = get_plant_info(plant_species)
        if plant_info:
            water_sensitivity = plant_info["water_sensitivity"]
        else:
            water_sensitivity = 0.5
        
        temp_factor = 1.0 + (temperature - 20) * 0.03
        if temp_factor < 0.5:
            temp_factor = 0.5
        if temp_factor > 2.0:
            temp_factor = 2.0
        
        humidity_factor = 1.0 - (humidity - 50) * 0.01
        if humidity_factor < 0.3:
            humidity_factor = 0.3
        if humidity_factor > 1.8:
            humidity_factor = 1.8
        
        light_factor = 1.0
        if light_intensity is not None:
            if light_intensity > 10000:
                light_factor = 1.2
            elif light_intensity > 5000:
                light_factor = 1.1
            elif light_intensity < 1000:
                light_factor = 0.8
        
        base_evaporation = 0.1
        
        evaporation_rate = (
            base_evaporation *
            pot_coeff *
            (1 - soil_coeff + 0.3) *
            temp_factor *
            humidity_factor *
            light_factor *
            (0.5 + water_sensitivity)
        )
        
        return evaporation_rate

    def calculate_average_interval(self, plant_id: str, plant_species: str) -> float:
        history = self.get_plant_history(plant_id)
        intervals = []
        
        for i in range(1, len(history)):
            prev = history[i-1]
            curr = history[i]
            interval = (curr.last_watering_time - prev.last_watering_time).total_seconds() / 86400
            if 0.5 <= interval <= 60:
                intervals.append(interval)
        
        if intervals:
            avg_interval = sum(intervals) / len(intervals)
        else:
            plant_info = get_plant_info(plant_species)
            if plant_info:
                avg_interval = plant_info["base_watering_interval_days"]
            else:
                avg_interval = 5.0
        
        return avg_interval

    def calculate_seasonal_coefficient(self, plant_species: str, date: Optional[datetime] = None) -> float:
        plant_info = get_plant_info(plant_species)
        season = get_season(date)
        
        if plant_info and "seasonal_adjustment" in plant_info:
            return plant_info["seasonal_adjustment"].get(season, 1.0)
        return 1.0

    def calculate_adaptation_score(
        self,
        plant_species: str,
        temperature: float,
        humidity: float,
        avg_interval: float,
        reported_intervals: List[float]
    ) -> float:
        plant_info = get_plant_info(plant_species)
        if not plant_info:
            return 70.0
        
        score = 100.0
        
        temp_min = plant_info["optimal_temp_min"]
        temp_max = plant_info["optimal_temp_max"]
        if temperature < temp_min:
            score -= (temp_min - temperature) * 2
        elif temperature > temp_max:
            score -= (temperature - temp_max) * 2
        
        hum_min = plant_info["optimal_humidity_min"]
        hum_max = plant_info["optimal_humidity_max"]
        if humidity < hum_min:
            score -= (hum_min - humidity) * 0.5
        elif humidity > hum_max:
            score -= (humidity - hum_max) * 0.3
        
        base_interval = plant_info["base_watering_interval_days"]
        interval_deviation = abs(avg_interval - base_interval) / base_interval
        if interval_deviation > 0.1:
            score -= min(interval_deviation * 20, 20)
        
        if reported_intervals and len(reported_intervals) >= 3:
            variance = sum((x - avg_interval) ** 2 for x in reported_intervals) / len(reported_intervals)
            consistency_penalty = min(variance * 5, 10)
            score -= consistency_penalty
        
        return max(0.0, min(100.0, score))

    def predict_watering(
        self,
        plant_id: str,
        plant_species: str,
        pot_material: str,
        soil_type: str,
        last_report: Optional[WateringReport] = None
    ) -> WateringPrediction:
        if last_report is None:
            history = self.get_plant_history(plant_id)
            if not history:
                raise ValueError("No watering reports found for this plant")
            last_report = history[-1]
        
        evaporation_rate = self.calculate_evaporation_rate(
            temperature=last_report.temperature,
            humidity=last_report.humidity,
            pot_material=pot_material,
            soil_type=soil_type,
            plant_species=plant_species,
            light_intensity=last_report.light_intensity
        )
        
        avg_interval = self.calculate_average_interval(plant_id, plant_species)
        seasonal_coeff = self.calculate_seasonal_coefficient(plant_species, last_report.report_time)
        
        adjusted_interval = avg_interval * seasonal_coeff
        
        days_since_watering = (last_report.report_time - last_report.last_watering_time).total_seconds() / 86400
        days_until_next = max(0.0, adjusted_interval - days_since_watering)
        
        predicted_next = last_report.report_time + timedelta(days=days_until_next)
        
        window_hours = max(6, int(adjusted_interval * 24 * 0.1))
        window_start = predicted_next - timedelta(hours=window_hours)
        window_end = predicted_next + timedelta(hours=window_hours)
        
        history = self.get_plant_history(plant_id)
        reported_intervals = []
        for i in range(1, len(history)):
            interval = (history[i].last_watering_time - history[i-1].last_watering_time).total_seconds() / 86400
            if 0.5 <= interval <= 60:
                reported_intervals.append(interval)
        
        adaptation_score = self.calculate_adaptation_score(
            plant_species=plant_species,
            temperature=last_report.temperature,
            humidity=last_report.humidity,
            avg_interval=avg_interval,
            reported_intervals=reported_intervals
        )
        
        confidence = 0.7
        if len(history) >= 10:
            confidence = 0.9
        elif len(history) >= 5:
            confidence = 0.8
        
        prediction = WateringPrediction(
            plant_id=plant_id,
            predicted_next_watering=predicted_next,
            watering_window_start=window_start,
            watering_window_end=window_end,
            days_until_next_watering=round(days_until_next, 2),
            avg_watering_interval=round(avg_interval, 2),
            seasonal_adjustment_coefficient=round(seasonal_coeff, 3),
            adaptation_score=round(adaptation_score, 2),
            confidence=round(confidence, 2),
            evaporation_rate=round(evaporation_rate, 4)
        )
        
        self.cached_predictions[plant_id] = (prediction, datetime.now())
        return prediction

    def detect_anomalies(
        self,
        plant_id: str,
        plant_species: str,
        last_report: Optional[WateringReport] = None,
        prediction: Optional[WateringPrediction] = None
    ) -> List[AnomalyAlert]:
        alerts: List[AnomalyAlert] = []
        
        if last_report is None:
            history = self.get_plant_history(plant_id)
            if not history:
                return alerts
            last_report = history[-1]
        
        if prediction is None:
            try:
                prediction = self.predict_watering(
                    plant_id=plant_id,
                    plant_species=plant_species,
                    pot_material="ceramic",
                    soil_type="loam",
                    last_report=last_report
                )
            except ValueError:
                return alerts
        
        plant_info = get_plant_info(plant_species)
        if not plant_info:
            return alerts
        
        days_since_watering = (last_report.report_time - last_report.last_watering_time).total_seconds() / 86400
        
        if last_report.soil_moisture is not None:
            if last_report.soil_moisture > 80 and days_since_watering < 2:
                rot_risk = 1.0 - plant_info["rot_resistance"]
                if rot_risk > 0.5:
                    severity = "high" if rot_risk > 0.7 else "medium"
                    alerts.append(AnomalyAlert(
                        plant_id=plant_id,
                        alert_type="root_rot_risk",
                        severity=severity,
                        message=f"检测到烂根风险：土壤湿度({last_report.soil_moisture}%)过高，浇水后仅{days_since_watering:.1f}天",
                        timestamp=datetime.now(),
                        suggestions=[
                            "立即停止浇水，让土壤充分干燥",
                            "检查花盆排水孔是否通畅",
                            "考虑更换透气性更好的土壤",
                            "将植物移至通风良好的位置"
                        ]
                    ))
            
            if last_report.soil_moisture < 15:
                drought_risk = 1.0 - plant_info["drought_tolerance"]
                if drought_risk > 0.3 or days_since_watering > plant_info["base_watering_interval_days"] * 1.5:
                    severity = "high" if drought_risk > 0.6 else "medium"
                    alerts.append(AnomalyAlert(
                        plant_id=plant_id,
                        alert_type="drought_stress",
                        severity=severity,
                        message=f"检测到干旱应激：土壤湿度({last_report.soil_moisture}%)过低，已{days_since_watering:.1f}天未浇水",
                        timestamp=datetime.now(),
                        suggestions=[
                            "立即浇水，直到盆底有水流出",
                            "可适当增加空气湿度，如喷雾",
                            "检查光照是否过强，适当遮阴",
                            "考虑增加浇水频率"
                        ]
                    ))
        
        if days_since_watering > prediction.avg_watering_interval * 2:
            alerts.append(AnomalyAlert(
                plant_id=plant_id,
                alert_type="missed_watering",
                severity="high",
                message=f"严重错过浇水时间：建议每{prediction.avg_watering_interval:.1f}天浇水，已{days_since_watering:.1f}天未浇水",
                timestamp=datetime.now(),
                suggestions=[
                    "立即浇水补充水分",
                    "设置浇水提醒避免遗忘",
                    "观察植物是否有脱水症状"
                ]
            ))
        elif days_since_watering > prediction.avg_watering_interval * 1.3:
            alerts.append(AnomalyAlert(
                plant_id=plant_id,
                alert_type="watering_due",
                severity="low",
                message=f"已到浇水时间：建议每{prediction.avg_watering_interval:.1f}天浇水，已{days_since_watering:.1f}天未浇水",
                timestamp=datetime.now(),
                suggestions=[
                    "今天是最佳浇水时间",
                    "请在24小时内完成浇水"
                ]
            ))
        
        if last_report.temperature < plant_info["optimal_temp_min"] - 5:
            alerts.append(AnomalyAlert(
                plant_id=plant_id,
                alert_type="temperature_stress_low",
                severity="medium",
                message=f"温度过低应激：当前温度{last_report.temperature}°C，低于最佳范围{plant_info['optimal_temp_min']}-{plant_info['optimal_temp_max']}°C",
                timestamp=datetime.now(),
                suggestions=[
                    "将植物移至温暖的位置",
                    "避免靠近空调或冷风口",
                    "考虑使用加温设备"
                ]
            ))
        elif last_report.temperature > plant_info["optimal_temp_max"] + 5:
            alerts.append(AnomalyAlert(
                plant_id=plant_id,
                alert_type="temperature_stress_high",
                severity="medium",
                message=f"温度过高应激：当前温度{last_report.temperature}°C，高于最佳范围{plant_info['optimal_temp_min']}-{plant_info['optimal_temp_max']}°C",
                timestamp=datetime.now(),
                suggestions=[
                    "将植物移至阴凉处",
                    "增加喷雾降温增湿",
                    "避免阳光直射"
                ]
            ))
        
        if last_report.humidity < plant_info["optimal_humidity_min"] - 20:
            alerts.append(AnomalyAlert(
                plant_id=plant_id,
                alert_type="humidity_stress_low",
                severity="low",
                message=f"湿度过低：当前湿度{last_report.humidity}%，低于最佳范围{plant_info['optimal_humidity_min']}-{plant_info['optimal_humidity_max']}%",
                timestamp=datetime.now(),
                suggestions=[
                    "使用加湿器增加空气湿度",
                    "每天喷雾1-2次",
                    "将花盆放在加湿托盘上"
                ]
            ))
        
        if prediction.days_until_next_watering < 1.0 and len(alerts) == 0:
            alerts.append(AnomalyAlert(
                plant_id=plant_id,
                alert_type="watering_reminder",
                severity="low",
                message=f"浇水提醒：还有{prediction.days_until_next_watering:.1f}天需要浇水，最佳窗口为{prediction.watering_window_start.strftime('%m-%d %H:%M')}至{prediction.watering_window_end.strftime('%m-%d %H:%M')}",
                timestamp=datetime.now(),
                suggestions=[
                    "建议在最佳浇水窗口内浇水",
                    "浇水时浇透直到盆底出水"
                ]
            ))
        
        self.cached_alerts[plant_id] = alerts
        return alerts

    def generate_maintenance_suggestions(
        self,
        plant_id: str,
        plant_species: str,
        last_report: Optional[WateringReport] = None,
        prediction: Optional[WateringPrediction] = None
    ) -> List[MaintenanceSuggestion]:
        suggestions: List[MaintenanceSuggestion] = []
        
        if last_report is None:
            history = self.get_plant_history(plant_id)
            if not history:
                return suggestions
            last_report = history[-1]
        
        if prediction is None:
            try:
                prediction = self.predict_watering(
                    plant_id=plant_id,
                    plant_species=plant_species,
                    pot_material="ceramic",
                    soil_type="loam",
                    last_report=last_report
                )
            except ValueError:
                return suggestions
        
        plant_info = get_plant_info(plant_species)
        if not plant_info:
            return suggestions
        
        if prediction.adaptation_score < 60:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="environment",
                suggestion="改善养护环境，提高适配度评分",
                priority="high",
                reason=f"当前适配度评分{prediction.adaptation_score:.1f}，低于60分，环境条件与植物需求匹配度较低"
            ))
        
        temp = last_report.temperature
        if temp < plant_info["optimal_temp_min"]:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="temperature",
                suggestion=f"提高环境温度至{plant_info['optimal_temp_min']}-{plant_info['optimal_temp_max']}°C",
                priority="medium",
                reason=f"当前温度{temp}°C低于最佳温度范围{plant_info['optimal_temp_min']}-{plant_info['optimal_temp_max']}°C"
            ))
        elif temp > plant_info["optimal_temp_max"]:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="temperature",
                suggestion=f"降低环境温度至{plant_info['optimal_temp_min']}-{plant_info['optimal_temp_max']}°C",
                priority="medium",
                reason=f"当前温度{temp}°C高于最佳温度范围{plant_info['optimal_temp_min']}-{plant_info['optimal_temp_max']}°C"
            ))
        
        humidity = last_report.humidity
        if humidity < plant_info["optimal_humidity_min"]:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="humidity",
                suggestion=f"增加空气湿度至{plant_info['optimal_humidity_min']}-{plant_info['optimal_humidity_max']}%",
                priority="medium",
                reason=f"当前湿度{humidity}%低于最佳湿度范围{plant_info['optimal_humidity_min']}-{plant_info['optimal_humidity_max']}%"
            ))
        elif humidity > plant_info["optimal_humidity_max"]:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="humidity",
                suggestion=f"降低空气湿度至{plant_info['optimal_humidity_min']}-{plant_info['optimal_humidity_max']}%",
                priority="low",
                reason=f"当前湿度{humidity}%高于最佳湿度范围{plant_info['optimal_humidity_min']}-{plant_info['optimal_humidity_max']}%"
            ))
        
        season = get_season()
        seasonal_coeff = prediction.seasonal_adjustment_coefficient
        if seasonal_coeff < 0.8:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="seasonal",
                suggestion="当前为生长旺盛期，建议增加浇水频率",
                priority="medium",
                reason=f"{season}季节系数{seasonal_coeff:.2f}，植物代谢活跃，需水量增加"
            ))
        elif seasonal_coeff > 1.2:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="seasonal",
                suggestion="当前为休眠或缓慢生长期，建议减少浇水频率",
                priority="medium",
                reason=f"{season}季节系数{seasonal_coeff:.2f}，植物代谢减缓，需水量减少，注意控制浇水避免烂根"
            ))
        
        if prediction.evaporation_rate > 0.15:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="watering",
                suggestion="水分蒸发较快，建议关注土壤湿度变化",
                priority="low",
                reason=f"当前蒸发速率{prediction.evaporation_rate:.4f}较高，可能需要更频繁浇水"
            ))
        
        light_pref = plant_info.get("light_preference", "medium")
        if last_report.light_intensity is not None:
            light = last_report.light_intensity
            if light_pref == "high" and light < 3000:
                suggestions.append(MaintenanceSuggestion(
                    plant_id=plant_id,
                    category="light",
                    suggestion="增加光照强度",
                    priority="medium",
                    reason=f"该植物喜强光，当前光照{light}lux偏低"
                ))
            elif light_pref == "low" and light > 8000:
                suggestions.append(MaintenanceSuggestion(
                    plant_id=plant_id,
                    category="light",
                    suggestion="适当遮阴，避免强光直射",
                    priority="medium",
                    reason=f"该植物喜阴，当前光照{light}lux过强"
                ))
        
        if not suggestions:
            suggestions.append(MaintenanceSuggestion(
                plant_id=plant_id,
                category="general",
                suggestion="继续保持当前养护方式",
                priority="low",
                reason=f"当前环境条件良好，适配度评分{prediction.adaptation_score:.1f}分"
            ))
        
        return suggestions

    def get_plant_statistics(self, plant_id: str, plant_name: str, plant_species: str) -> Optional[Dict]:
        history = self.get_plant_history(plant_id)
        if not history:
            return None
        
        last_report = history[-1]
        
        try:
            prediction = self.predict_watering(
                plant_id=plant_id,
                plant_species=plant_species,
                pot_material="ceramic",
                soil_type="loam",
                last_report=last_report
            )
        except ValueError:
            return None
        
        return {
            "plant_id": plant_id,
            "plant_name": plant_name,
            "species": plant_species,
            "avg_watering_interval": prediction.avg_watering_interval,
            "seasonal_adjustment_coefficient": prediction.seasonal_adjustment_coefficient,
            "adaptation_score": prediction.adaptation_score,
            "total_watering_reports": len(history),
            "last_watering": last_report.last_watering_time,
            "next_predicted_watering": prediction.predicted_next_watering
        }
