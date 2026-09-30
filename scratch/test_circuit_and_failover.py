# -*- coding: utf-8 -*-
"""
test_circuit_and_failover.py - 验证断路器 (Circuit Breaker) 与主备模型故障转移逻辑
"""

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_gateway import circuit_breaker, CircuitBreakerOpenError, llm_gateway

def test_circuit_breaker_sliding_window():
    print("=" * 70)
    print("🚀 启动断路器 (Circuit Breaker) 滑动窗口熔断测试")
    print("=" * 70)

    # 1. 初始状态必须是 CLOSED
    status = circuit_breaker.get_status()
    print(f"1. 初始状态: {status['state']}, 历史记录: {status['recent_history']}")
    assert status['state'] == "CLOSED"

    # 2. 模拟连续 5 次超时失败 (达到 10 次滑动窗口中 50% 阈值)
    print("\n2. 模拟上游大模型连续发生超时 (5 次)...")
    for i in range(5):
        circuit_breaker.record_failure(is_timeout=True)
        print(f"   -> 记录第 {i+1} 次超时，当前状态: {circuit_breaker.state}")

    # 3. 验证此时断路器是否已翻转为 OPEN
    status = circuit_breaker.get_status()
    print(f"\n3. 触发熔断后状态: {status['state']}, 剩余冷却: {status['cooldown_remaining']}s")
    assert status['state'] == "OPEN", "超时率达到 50% 必须触发熔断！"

    # 4. 验证在 OPEN 状态下，再次发起请求是否被立即阻断抛出 CircuitBreakerOpenError
    print("\n4. 验证断路器拦截效果 (before_call)...")
    try:
        circuit_breaker.before_call()
        print("❌ 错误：熔断期间未阻断请求！")
        assert False
    except CircuitBreakerOpenError as e:
        print(f"✅ 成功拦截请求并抛出熔断提示: \"{e}\"")

    # 5. 模拟 60 秒冷却完成，进入 HALF-OPEN
    print("\n5. 模拟冷却时间结束 (重设时间戳)...")
    circuit_breaker.last_state_change = time.time() - 65
    circuit_breaker.before_call()
    assert circuit_breaker.state == "HALF-OPEN"
    print(f"✅ 断路器成功进入 HALF-OPEN 半开启试探状态")

    # 6. 半开启状态下单次成功，自动自愈恢复 CLOSED
    circuit_breaker.record_success()
    assert circuit_breaker.state == "CLOSED"
    print(f"✅ 试探请求成功，断路器恢复正常 CLOSED 状态！")

def test_gateway_config():
    print("\n" + "=" * 70)
    print("🚀 验证大模型主备配置与超时收紧参数")
    print("=" * 70)
    print(f"• 主模型名称: {llm_gateway.primary_model_name}")
    print(f"• 备用模型名称: {llm_gateway.backup_model_name}")
    print(f"• 超时限额 (Timeout): {llm_gateway.timeout_seconds} 秒 (已由 180s 强力收紧至 15s)")
    assert llm_gateway.timeout_seconds == 15
    assert llm_gateway.backup_model_name == "qwen3.7-flash-2026-07-15"
    print("✅ 大模型层主备及超时配置 100% 校验通过！")

if __name__ == "__main__":
    test_circuit_breaker_sliding_window()
    test_gateway_config()
    print("\n🎉 全部高可用与断路器单元测试通过！")
