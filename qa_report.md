# PalmT9 交付质量门禁报告
- 时间: 2026-09-05 16:34:45
- 总判定: **不通过 FAIL**

## 自动化测试: FAIL
```
32 failed, 45 passed in 0.22s
```
- FAILED test_product_qa.py::TestStateIntegrity::test_state_has_pinch_state - A...
- FAILED test_product_qa.py::TestStateIntegrity::test_evaluate_frame_smoke - At...
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_1]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_2]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_3]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_4]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_5]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_6]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_7]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_8]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_9]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_BACK]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_0]
- FAILED test_product_qa.py::TestPinchStateMachine::test_left_key_double_pinch_fires[L_ENTER]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_1]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_2]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_3]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_4]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_5]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_6]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_7]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_8]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_9]
- FAILED test_product_qa.py::TestPinchStateMachine::test_right_key_double_pinch_fires[R_0]
- FAILED test_product_qa.py::TestPinchStateMachine::test_rest_hand_zero_false_trigger
- FAILED test_product_qa.py::TestPinchStateMachine::test_single_pinch_no_trigger
- FAILED test_product_qa.py::TestPinchStateMachine::test_cooldown_blocks_immediate_retrigger
- FAILED test_product_qa.py::TestPinchStateMachine::test_max_interval_timeout
- FAILED test_product_qa.py::TestPinchStateMachine::test_two_hands_independent
- FAILED test_product_qa.py::TestPerformance::test_frame_latency_under_1ms - At...
- FAILED test_gesture_core.py::test_letter_trigger_updates_digits - AttributeEr...
- FAILED test_gesture_core.py::test_rest_hand_no_false_trigger - AttributeError...

## 交付文件: PASS

## 模块导入: PASS

## 待人工验收项（视觉/体验）
- [ ] 摄像头实跑 acceptance.py，逐键视觉验收通过
- [ ] launcher.py / start.bat 首次运行自动标定流程顺畅
- [ ] build_exe.bat 打包产物在干净机器可运行
- [ ] 演示场景: 盲打 hello / 你好 / 数字 全通过