from fastapi.testclient import TestClient
import main

print("=" * 60)
print("测试数据一致性修复")
print("=" * 60)

with TestClient(main.app) as client:
    # 创建测试分区
    print("\n1. 创建测试分区...")
    response = client.post('/api/zones', json={
        'name': '一致性测试分区',
        'zone_type': 'living_room',
        'environment': {
            'temperature': 22,
            'humidity': 60,
            'ventilation': 'good',
            'light_level': 'medium'
        }
    })
    zone_id = response.json()['data']['id']
    print(f"   分区ID: {zone_id}")

    # 创建3株测试植物
    plant_ids = []
    print("\n2. 创建3株测试植物...")
    for i in range(3):
        response = client.post('/api/plants', json={
            'name': f'测试植物{i+1}',
            'species': '绿萝',
            'pot_material': 'ceramic',
            'soil_type': 'peat'
        })
        pid = response.json()['data']['id']
        plant_ids.append(pid)
        print(f"   植物{i+1} ID: {pid}")

    # 绑定植物到分区
    print("\n3. 绑定植物到分区...")
    response = client.post(f'/api/zones/{zone_id}/plants', json={
        'plant_ids': plant_ids
    })
    print(f"   绑定结果: {response.json()['message']}")

    # 为每株植物创建2条养护日志
    print("\n4. 为每株植物创建2条养护日志（共6条植物级日志）...")
    for i, pid in enumerate(plant_ids):
        for j in range(2):
            response = client.post('/api/maintenance/log', json={
                'target_type': 'plant',
                'target_id': pid,
                'operation_type': 'watering',
                'executor': '测试员',
                'operation_reason': '土壤干燥',
                'status_before': {
                    'health_score': 50 + i * 5,
                    'leaf_condition': 'normal',
                    'growth_status': 'stable',
                    'has_new_growth': False,
                    'pest_signs': False,
                    'disease_signs': False,
                    'soil_moisture': 'dry'
                },
                'status_after': {
                    'health_score': 65 + i * 5,
                    'leaf_condition': 'normal',
                    'growth_status': 'improving',
                    'has_new_growth': True,
                    'pest_signs': False,
                    'disease_signs': False,
                    'soil_moisture': 'moist'
                },
                'observation_result': '浇水后状态改善'
            })
            assert response.status_code == 200
            log_id = response.json()['data']['id']
            init_effectiveness = response.json()['data']['effectiveness']
            print(f"   植物{i+1} 日志{j+1}: {log_id}, 初始有效性: {init_effectiveness}")

    # 创建1条分区级养护日志
    print("\n5. 创建1条分区级养护日志...")
    response = client.post('/api/maintenance/log', json={
        'target_type': 'zone',
        'target_id': zone_id,
        'operation_type': 'ventilation',
        'executor': '测试员',
        'operation_reason': '分区通风不良',
        'status_before': {
            'health_score': 60,
            'leaf_condition': 'normal',
            'growth_status': 'stable',
            'has_new_growth': False,
            'pest_signs': False,
            'disease_signs': False,
            'soil_moisture': 'moist'
        },
        'status_after': {
            'health_score': 70,
            'leaf_condition': 'normal',
            'growth_status': 'stable',
            'has_new_growth': False,
            'pest_signs': False,
            'disease_signs': False,
            'soil_moisture': 'moist'
        },
        'observation_result': '通风后空气质量改善'
    })
    zone_log_id = response.json()['data']['id']
    print(f"   分区日志ID: {zone_log_id}")

    # 测试1: 分区日志列表数据一致性
    print("\n" + "=" * 60)
    print("测试1: 分区日志列表 vs 分区分析 数据一致性")
    print("=" * 60)

    response = client.get(f'/api/maintenance/zone/{zone_id}')
    zone_logs_result = response.json()['data']
    zone_logs_count = zone_logs_result['total']
    print(f"\n分区日志列表返回: {zone_logs_count} 条日志")
    print(f"  (期望: 6条植物级 + 1条分区级 = 7条)")

    response = client.get(f'/api/maintenance/zone/analysis/{zone_id}')
    analysis_result = response.json()['data']
    analysis_count = analysis_result['total_operations']
    print(f"\n分区分析返回: {analysis_count} 条操作")
    print(f"  有效操作: {analysis_result['effective_operations']}")
    print(f"  无效操作: {analysis_result['ineffective_operations']}")

    if zone_logs_count == analysis_count == 7:
        print("\n✅ 测试1通过: 分区日志列表与分区分析数据一致")
    else:
        print(f"\n❌ 测试1失败: 日志列表={zone_logs_count}, 分析={analysis_count}, 期望=7")

    # 测试2: 分区统计数据一致性
    print("\n" + "=" * 60)
    print("测试2: 分区日志列表 vs 分区统计 数据一致性")
    print("=" * 60)

    response = client.get(f'/api/maintenance/statistics', params={
        'target_type': 'zone',
        'target_id': zone_id
    })
    stats_result = response.json()['data']
    stats_count = stats_result['total_logs']
    print(f"\n分区统计返回: {stats_count} 条日志")
    print(f"  近7天操作: {stats_result['last_7_days_count']} 次")
    print(f"  有效性分布: {stats_result['effectiveness_distribution']}")

    if zone_logs_count == stats_count == 7:
        print("\n✅ 测试2通过: 分区日志列表与分区统计数据一致")
    else:
        print(f"\n❌ 测试2失败: 日志列表={zone_logs_count}, 统计={stats_count}, 期望=7")

    # 测试3: 效果评估前后一致性
    print("\n" + "=" * 60)
    print("测试3: 同一条日志效果评估前后一致性")
    print("=" * 60)

    # 获取第一条植物日志
    response = client.get(f'/api/maintenance/plant/{plant_ids[0]}')
    first_log_id = response.json()['data']['logs'][0]['id']
    first_log_effectiveness = response.json()['data']['logs'][0]['effectiveness']
    print(f"\n日志ID: {first_log_id}")
    print(f"日志列表显示有效性: {first_log_effectiveness}")

    # 分析该日志
    response = client.get(f'/api/maintenance/analysis/{first_log_id}')
    analysis_effectiveness = response.json()['data']['effectiveness']
    analysis_score = response.json()['data']['effectiveness_score']
    print(f"分析接口返回有效性: {analysis_effectiveness}")
    print(f"分析接口返回评分: {analysis_score}")

    # 再次获取日志详情
    response = client.get(f'/api/maintenance/logs/{first_log_id}')
    log_detail_effectiveness = response.json()['data']['effectiveness']
    print(f"再次获取日志详情有效性: {log_detail_effectiveness}")

    if first_log_effectiveness == analysis_effectiveness == log_detail_effectiveness:
        print("\n✅ 测试3通过: 同一条日志效果评估前后一致")
    else:
        print(f"\n❌ 测试3失败: 列表={first_log_effectiveness}, 分析={analysis_effectiveness}, 详情={log_detail_effectiveness}")

    # 测试4: 添加后续观察后效果评估一致性
    print("\n" + "=" * 60)
    print("测试4: 添加后续观察后效果评估一致性")
    print("=" * 60)

    # 添加后续观察（状态大幅改善）
    response = client.post('/api/maintenance/observation', json={
        'log_id': first_log_id,
        'observation_time': '2026-06-10T12:00:00',
        'observer': '测试员',
        'current_status': {
            'health_score': 90,
            'leaf_condition': 'healthy',
            'growth_status': 'thriving',
            'has_new_growth': True,
            'pest_signs': False,
            'disease_signs': False,
            'soil_moisture': 'moist'
        },
        'observation_notes': '植物状态明显好转，新叶生长旺盛'
    })
    observation_effectiveness = response.json()['data']['effectiveness']
    print(f"\n添加观察后日志有效性: {observation_effectiveness}")

    # 再次分析
    response = client.get(f'/api/maintenance/analysis/{first_log_id}')
    reanalysis_effectiveness = response.json()['data']['effectiveness']
    print(f"再次分析有效性: {reanalysis_effectiveness}")

    # 获取日志详情
    response = client.get(f'/api/maintenance/logs/{first_log_id}')
    final_effectiveness = response.json()['data']['effectiveness']
    print(f"日志详情有效性: {final_effectiveness}")

    if observation_effectiveness == reanalysis_effectiveness == final_effectiveness:
        print("\n✅ 测试4通过: 添加后续观察后效果评估一致")
    else:
        print(f"\n❌ 测试4失败: 观察后={observation_effectiveness}, 再分析={reanalysis_effectiveness}, 详情={final_effectiveness}")

    print("\n" + "=" * 60)
    print("一致性测试完成")
    print("=" * 60)
