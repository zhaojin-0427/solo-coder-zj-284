from fastapi.testclient import TestClient
from datetime import date, datetime, timedelta
import main

print("=" * 70)
print("植物养护耗材库存与采购补货管理 综合测试")
print("=" * 70)

with TestClient(main.app) as client:
    zone_ids = []
    plant_ids = []
    consumable_ids = []

    print("\n" + "=" * 70)
    print("【准备数据】创建分区和植物")
    print("=" * 70)

    resp = client.post('/api/zones', json={
        'name': '客厅A区',
        'zone_type': 'living_room',
        'environment': {
            'avg_temperature': 23,
            'avg_humidity': 60,
            'ventilation': 'good',
            'light_level': 'bright_indirect',
            'is_near_window': True
        }
    })
    zone1_id = resp.json()['data']['id']
    zone_ids.append(zone1_id)
    print(f"创建分区1（客厅A区）: {zone1_id}")

    resp = client.post('/api/zones', json={
        'name': '阳台B区',
        'zone_type': 'balcony',
        'environment': {
            'avg_temperature': 26,
            'avg_humidity': 55,
            'ventilation': 'excellent',
            'light_level': 'direct_sun'
        }
    })
    zone2_id = resp.json()['data']['id']
    zone_ids.append(zone2_id)
    print(f"创建分区2（阳台B区）: {zone2_id}")

    species_list = ['绿萝', '多肉', '月季', '龟背竹', '薄荷']
    for i, sp in enumerate(species_list):
        resp = client.post('/api/plants', json={
            'name': f'{sp}-{i+1}',
            'species': sp,
            'pot_material': 'ceramic' if i % 2 == 0 else 'plastic',
            'soil_type': 'peat'
        })
        pid = resp.json()['data']['id']
        plant_ids.append(pid)
        zone_to_bind = zone1_id if i < 3 else zone2_id
        client.post(f'/api/zones/{zone_to_bind}/plants', json={'plant_ids': [pid]})
        print(f"创建植物 {sp}-{i+1}: {pid} -> 分区{1 if i<3 else 2}")

    print("\n" + "=" * 70)
    print("【测试1-1】创建耗材库存档案")
    print("=" * 70)

    today = date.today()
    future_30 = today + timedelta(days=30)
    future_15 = today + timedelta(days=15)
    past_3 = today - timedelta(days=3)

    test_consumables = [
        {
            'name': '奥绿缓释肥A2',
            'category': 'fertilizer',
            'specification': '500g/瓶',
            'unit': '瓶',
            'current_stock': 1.5,
            'min_safe_stock': 2.0,
            'unit_price': 45.0,
            'applicable_zones': zone_ids,
            'expiry_date': future_30.isoformat(),
            'storage_location': '储物架A-01',
            'storage_condition': 'cool_dry',
            'supplier': {
                'name': '花儿朵朵农资店',
                'contact': '张经理',
                'phone': '13800000001'
            },
            'is_critical': True,
            'consumption_rate_per_plant': 5.0,
            'typical_usage_interval_days': 14,
            'notes': '通用缓释肥'
        },
        {
            'name': '花多多1号营养液',
            'category': 'nutrient_solution',
            'specification': '1L/瓶',
            'unit': '瓶',
            'current_stock': 3.0,
            'min_safe_stock': 2.0,
            'unit_price': 38.0,
            'applicable_zones': [zone1_id],
            'expiry_date': future_15.isoformat(),
            'opened_at': (datetime.now() - timedelta(days=40)).isoformat(),
            'shelf_life_days_after_open': 30,
            'storage_location': '储物架A-02',
            'is_critical': False,
            'consumption_rate_per_plant': 10.0,
            'typical_usage_interval_days': 7
        },
        {
            'name': '多菌灵杀菌剂',
            'category': 'fungicide',
            'specification': '100g/袋',
            'unit': '袋',
            'current_stock': 0.3,
            'min_safe_stock': 2.0,
            'unit_price': 12.0,
            'expiry_date': past_3.isoformat(),
            'storage_location': '危险品柜B-01',
            'storage_condition': 'avoid_sunlight',
            'supplier': {
                'name': '护花神农药店',
                'phone': '13800000002'
            },
            'is_critical': True,
            'alternatives': [],
            'consumption_rate_per_plant': 20.0
        },
        {
            'name': '吡虫啉杀虫剂',
            'category': 'insecticide',
            'specification': '50ml/瓶',
            'unit': '瓶',
            'current_stock': 5.0,
            'min_safe_stock': 1.0,
            'unit_price': 25.0,
            'expiry_date': (today + timedelta(days=180)).isoformat(),
            'storage_location': '危险品柜B-02',
            'storage_condition': 'sealed',
            'is_critical': False,
            'consumption_rate_per_plant': 15.0
        },
        {
            'name': '进口泥炭土',
            'category': 'soil',
            'specification': '5L/袋',
            'unit': '袋',
            'current_stock': 4.0,
            'min_safe_stock': 3.0,
            'unit_price': 35.0,
            'expiry_date': (today + timedelta(days=365)).isoformat(),
            'storage_location': '阳台角落',
            'storage_condition': 'sealed',
            'is_critical': False,
            'consumption_rate_per_plant': 2.0
        },
        {
            'name': '陶粒铺面石',
            'category': 'clay_pellets',
            'specification': '1kg/袋',
            'unit': '袋',
            'current_stock': 2.0,
            'min_safe_stock': 1.0,
            'unit_price': 15.0,
            'storage_location': '储物架C-01'
        },
        {
            'name': '喷壶活性炭滤芯',
            'category': 'sprayer_filter',
            'specification': '10个/包',
            'unit': '包',
            'current_stock': 0.5,
            'min_safe_stock': 1.0,
            'unit_price': 20.0,
            'storage_location': '工具柜D-01'
        }
    ]

    for c in test_consumables:
        resp = client.post('/api/consumables', json=c)
        assert resp.status_code == 200, f"创建耗材失败: {c['name']}"
        data = resp.json()
        assert data['code'] == 200
        cid = data['data']['id']
        consumable_ids.append(cid)
        print(f"✅ 创建成功: {c['name']} (ID: {cid[:8]}...)")

    print(f"\n共创建 {len(consumable_ids)} 种耗材")

    print("\n" + "=" * 70)
    print("【测试1-2】获取耗材列表（筛选功能）")
    print("=" * 70)

    resp = client.get('/api/consumables')
    assert resp.status_code == 200
    data = resp.json()
    assert data['code'] == 200
    assert data['data']['total'] == len(consumable_ids)
    print(f"✅ 获取全部耗材成功：共 {data['data']['total']} 条")

    resp = client.get('/api/consumables', params={'low_stock_only': True})
    data = resp.json()
    low_count = data['data']['total']
    print(f"✅ 低库存筛选: {low_count} 条（库存≤安全线）")

    resp = client.get('/api/consumables', params={'critical_only': True})
    data = resp.json()
    print(f"✅ 关键耗材筛选: {data['data']['total']} 条")

    resp = client.get('/api/consumables', params={'category': 'fertilizer'})
    data = resp.json()
    print(f"✅ 按分类筛选（肥料）: {data['data']['total']} 条")

    print("\n" + "=" * 70)
    print("【测试1-3】耗材CRUD - 查询/更新/删除")
    print("=" * 70)

    resp = client.get(f'/api/consumables/{consumable_ids[0]}')
    data = resp.json()
    assert data['code'] == 200
    print(f"✅ 查询单个耗材成功: {data['data']['name']}")

    resp = client.put(f'/api/consumables/{consumable_ids[0]}', json={
        'notes': '更新备注：测试更新功能正常',
        'storage_location': '储物架A-01（已盘点）'
    })
    data = resp.json()
    assert data['code'] == 200
    print(f"✅ 更新耗材成功: notes={data['data']['notes']}")

    print("\n" + "=" * 70)
    print("【测试2-1】库存调整（入库/消耗）")
    print("=" * 70)

    resp = client.post('/api/consumables/stock/adjust', json={
        'consumable_id': consumable_ids[3],
        'adjustment_type': 'consume',
        'quantity': -0.5,
        'reason': '日常养护消耗',
        'operator': '张养护',
        'notes': '为客厅绿萝施肥'
    })
    data = resp.json()
    assert data['code'] == 200
    print(f"✅ 消耗登记成功: 吡虫啉 消耗0.5瓶, 当前库存: {data['data']['current_stock']}")

    resp = client.post('/api/consumables/stock/adjust', json={
        'consumable_id': consumable_ids[4],
        'adjustment_type': 'restock',
        'quantity': 3,
        'reason': '采购入库',
        'operator': '李采购',
        'notes': '月度常规采购'
    })
    data = resp.json()
    assert data['code'] == 200
    print(f"✅ 入库登记成功: 泥炭土 入库3袋, 当前库存: {data['data']['current_stock']}")

    resp = client.post('/api/consumables/stock/adjust', json={
        'consumable_id': consumable_ids[0],
        'adjustment_type': 'consume',
        'quantity': -100,
        'reason': '测试超量消耗'
    })
    data = resp.json()
    assert data['code'] == 400, f"超量消耗应该返回400"
    print(f"✅ 库存不足拦截成功: 返回 {data['code']}: {data['message']}")

    resp = client.get(f'/api/consumables/{consumable_ids[0]}/transactions')
    data = resp.json()
    print(f"✅ 查询库存变动记录: {data['data']['total']} 条记录")

    print("\n" + "=" * 70)
    print("【测试3-1】综合评估 - 消耗预测 + 风险评估")
    print("=" * 70)

    for horizon in [7, 14, 30]:
        resp = client.get('/api/consumables/assessment/all', params={'horizon_days': horizon})
        data = resp.json()
        assert data['code'] == 200
        summary = data['data']['summary']
        print(f"\n--- 未来{horizon}天评估 ---")
        print(f"  评估耗材总数: {summary['total_consumables']}")
        print(f"  风险/警告: {summary['total_at_risk']}/{summary['total_warning']}")
        print(f"  临期/过期提醒: {summary['total_expiry_alerts_critical']}")
        print(f"  采购建议数量: {summary['total_procurement_items']} (紧急{summary['total_procurement_urgent']})")
        print(f"  调整建议数量: {summary['total_adjustment_suggestions']}")
        print(f"  预计采购总成本: ¥{summary['total_estimated_purchase_cost']}")
        print(f"  库存总价值: ¥{summary['total_inventory_value']}")
        print(f"  成本效率评分: {summary['cost_efficiency_score']}/100")

    print("\n✅ 综合评估接口正常")

    print("\n" + "=" * 70)
    print("【测试3-2】消耗预测评估详细")
    print("=" * 70)

    resp = client.get('/api/consumables/assessment/consumption', params={'horizon_days': 14})
    data = resp.json()
    assert data['code'] == 200
    for est in data['data']['consumption_estimates'][:5]:
        print(f"  {est['consumable_name']}: 预测消耗 {est['estimated_consumption']} {est['unit']}, "
              f"期末库存: {est['projected_end_stock']}, 置信度: {est['confidence']}")

    print("\n✅ 消耗预测正常")

    print("\n" + "=" * 70)
    print("【测试3-3】风险评估详细")
    print("=" * 70)

    resp = client.get('/api/consumables/assessment/risks', params={'horizon_days': 14})
    risks = resp.json()['data']
    print(f"共 {len(risks['stock_risk_assessments'])} 个风险评估:")
    for risk in risks['stock_risk_assessments']:
        print(f"  {risk['consumable_name']}: 综合风险={risk['overall_risk_level']} (分数{risk['overall_risk_score']})")
        for factor in risk['risk_factors'][:2]:
            print(f"    - {factor}")

    print(f"\n到期提醒 {len(risks['expiry_alerts'])} 条:")
    for alert in risks['expiry_alerts'][:5]:
        suffix = f" (到期日还有{alert['days_to_expiry']}天)" if alert['days_to_expiry'] is not None else ""
        print(f"  [{alert['severity']}] {alert['consumable_name']}: {alert['alert_type']}{suffix}")

    print(f"\n替代可行性 {len(risks['substitute_feasibility'])} 个:")
    for sub in risks['substitute_feasibility']:
        print(f"  {sub['consumable_name']}: 替代可行性={sub['overall_feasibility']}, 替代品数={sub['alternative_count']}")

    print("\n✅ 风险评估正常")

    print("\n" + "=" * 70)
    print("【测试4-1】补货建议 + 采购清单")
    print("=" * 70)

    resp = client.get('/api/consumables/procurement/suggestions', params={'horizon_days': 30})
    data = resp.json()
    assert data['code'] == 200
    summary = data['data']['summary']
    print(f"采购清单统计: 共{summary['total_items']}项")
    print(f"  紧急: {summary['urgent_count']}, 高: {summary['high_count']}, 中: {summary['medium_count']}, 低: {summary['low_count']}")
    print(f"  预计采购总费用: ¥{summary['total_estimated_cost']}")

    print("\n采购明细:")
    for item in data['data']['procurement_list']:
        print(f"  [{item['priority']}] {item['consumable_name']}: 建议采购{item['recommended_quantity']}{item['unit']}, "
              f"¥{item['estimated_total_cost']} 优先级分数{item['priority_score']}")
        for reason in item['reason'][:2]:
            print(f"    原因: {reason}")

    print("\n补货建议:")
    for s in data['data']['restock_suggestions'][:3]:
        print(f"  {s['action']}: {s['consumable_name']} -> {s['recommended_quantity']}{s['unit']}")
        print(f"    建议采购日期: {s['suggested_purchase_date']}, 截止: {s['deadline_date']}")

    print("\n✅ 采购建议正常")

    print("\n" + "=" * 70)
    print("【测试4-2】临期提醒独立接口")
    print("=" * 70)

    resp = client.get('/api/consumables/alerts/expiry')
    data = resp.json()
    print(f"临期提醒共 {data['data']['total']} 条")
    print(f"  严重: {data['data']['critical_count']}, 高: {data['data']['high_count']}, 中: {data['data']['medium_count']}")
    print(f"  预计浪费价值: ¥{data['data']['total_estimated_waste']}")
    for a in data['data']['alerts']:
        print(f"  [{a['severity']}] {a['consumable_name']}: {a['alert_type']}, 剩{a['remaining_stock']}{a['unit']}")
        if a['can_be_used_up']:
            print(f"    可在到期前用完")
        elif a['suggestions']:
            print(f"    建议: {a['suggestions'][0]}")

    print("\n✅ 临期提醒正常")

    print("\n" + "=" * 70)
    print("【测试4-3】成本概览")
    print("=" * 70)

    resp = client.get('/api/consumables/cost/overview', params={'horizon_days': 30})
    data = resp.json()
    assert data['code'] == 200
    c = data['data']
    print(f"库存总价值: ¥{c['total_inventory_value']}")
    print(f"预计采购成本: ¥{c['total_estimated_purchase_cost']}")
    print(f"预计浪费价值: ¥{c['estimated_waste_value']}")
    if c.get('monthly_consumption_value'):
        print(f"月度消耗价值: ¥{c['monthly_consumption_value']}")
    print(f"成本效率评分: {c['cost_efficiency_score']}/100")
    print("\n分类成本分布:")
    for cat in c['category_breakdown']:
        print(f"  {cat['category']}: ¥{cat['inventory_value']} ({cat['value_ratio']}%)")

    print(f"\n高成本耗材TOP3:")
    for item in c['top_cost_items'][:3]:
        print(f"  {item['name']}: ¥{item['stock_value']}")

    if c['saving_opportunities']:
        print("\n成本优化机会:")
        for s in c['saving_opportunities']:
            print(f"  💡 {s['type']}: 可节省 ¥{s['potential_saving']}")
            if s['actions']:
                print(f"    措施: {s['actions'][:2]}")

    print("\n✅ 成本概览正常")

    print("\n" + "=" * 70)
    print("【测试5】可解释的调整建议")
    print("=" * 70)

    resp = client.get('/api/consumables/suggestions/adjustments', params={'horizon_days': 30})
    data = resp.json()
    assert data['code'] == 200
    summary = data['data']['summary']
    print(f"调整建议总数: {data['data']['total']}")
    print(f"  按类型分布: {summary['by_type']}")
    print(f"  按优先级: {summary['by_priority']}")

    print("\n调整建议详细:")
    for s in data['data']['suggestions']:
        print(f"\n  【{s['priority']}】{s['title']}")
        print(f"    类型: {s['suggestion_type']}")
        print(f"    触发: {s['trigger_condition']}")
        print(f"    建议措施: {s['recommended_action']}")
        print(f"    解释: {s['explanation'][:80]}...")
        print(f"    置信度: {s['confidence']}")
        if s['affected_consumables']:
            print(f"    影响耗材数: {len(s['affected_consumables'])}")
        if s['alternative_actions']:
            print(f"    备选方案数: {len(s['alternative_actions'])}")

    print("\n✅ 调整建议正常")

    print("\n" + "=" * 70)
    print("【测试6】统一响应格式验证")
    print("=" * 70)

    test_endpoints = [
        ('GET', '/api/consumables', None),
        ('GET', f'/api/consumables/{consumable_ids[0]}', None),
        ('GET', '/api/consumables/assessment/all', {'horizon_days': 7}),
        ('GET', '/api/consumables/procurement/suggestions', None),
        ('GET', '/api/consumables/alerts/expiry', None),
    ]

    all_ok = True
    for method, path, params in test_endpoints:
        if method == 'GET':
            resp = client.get(path, params=params) if params else client.get(path)
        else:
            resp = client.post(path)
        body = resp.json()
        has_code = 'code' in body
        has_msg = 'message' in body
        has_data = 'data' in body
        is_200 = body.get('code') == 200
        status = "✅" if (has_code and has_msg and has_data and is_200) else "❌"
        if not (has_code and has_msg and has_data):
            all_ok = False
        print(f"  {status} {path[:50]}: code={body.get('code')} "
              f"{'有' if has_code else '无'}code, {'有' if has_msg else '无'}message, {'有' if has_data else '无'}data")

    if all_ok:
        print("\n✅ 所有接口统一返回 {code, message, data} 格式")

    print("\n" + "=" * 70)
    print("所有测试完成！")
    print("=" * 70)
