# -*- coding: utf-8 -*-
"""
llm_gateway.py - 企业级大模型高可用网关与风控断路器 (Circuit Breaker & Primary-Backup Router)

核心特性：
1. 严格控制超时时间 (默认 15s)，防止百炼网络波动长耗时阻塞
2. 主备模型自动故障转移 (Primary: qwen3.8-flash, Backup: qwen3.7-flash-2026-07-15)
3. 统计最近 10 次调用的滑动窗口超时率；若超时率 >= 50%，触发断路器熔断并阻断请求，直接返回“AI 算力暂时拥塞”
4. 60秒冷却时间后进入 Half-Open 状态，自动试探自愈
"""

import os
import time
import collections
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import openai

load_dotenv()

class CircuitBreakerOpenError(Exception):
    """断路器熔断异常"""
    pass

class CircuitBreaker:
    """
    基于滑动窗口的断路器 (Sliding-Window Circuit Breaker)
    - 统计最近 window_size (10) 次调用
    - 若超时率 >= failure_threshold (50%)，状态进入 OPEN (开启熔断)
    - 冷却 recovery_timeout (60s) 后转入 HALF-OPEN，放行单次试探请求
    """
    def __init__(self, window_size: int = 10, failure_threshold: float = 0.5, recovery_timeout: float = 60.0):
        self.window_size = window_size
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.history = collections.deque(maxlen=window_size)
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_state_change = time.time()

    def before_call(self):
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_state_change > self.recovery_timeout:
                print("[CircuitBreaker] ⏳ 熔断冷却时间已过，进入 HALF-OPEN 半开启状态，允许单次试探调用...")
                self.state = "HALF-OPEN"
                self.last_state_change = now
            else:
                remaining = int(self.recovery_timeout - (now - self.last_state_change))
                raise CircuitBreakerOpenError(f"⚠️ AI 算力暂时拥塞，已触发系统防拖死熔断机制，请等待 {remaining} 秒或使用兜底表单录入！")

    def record_success(self):
        self.history.append("SUCCESS")
        if self.state == "HALF-OPEN":
            print("[CircuitBreaker] ✅ 半开启试探调用成功，断路器恢复 CLOSED 正常状态！")
            self.state = "CLOSED"
            self.last_state_change = time.time()

    def record_failure(self, is_timeout: bool = False):
        status = "TIMEOUT" if is_timeout else "FAILURE"
        self.history.append(status)
        now = time.time()

        if self.state == "HALF-OPEN":
            print("[CircuitBreaker] ❌ 半开启试探再次失败/超时，继续保持 OPEN 熔断状态！")
            self.state = "OPEN"
            self.last_state_change = now
            return

        if len(self.history) >= min(4, self.window_size):
            timeout_count = sum(1 for x in self.history if x == "TIMEOUT")
            timeout_rate = timeout_count / len(self.history)
            if timeout_rate >= self.failure_threshold:
                print(f"[CircuitBreaker] 🚨 最近 {len(self.history)} 次调用中超时率高达 {timeout_rate*100:.1f}% >= 50%！正式开启熔断 (OPEN)，锁定 60 秒！")
                self.state = "OPEN"
                self.last_state_change = now

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "recent_history": list(self.history),
            "window_size": self.window_size,
            "cooldown_remaining": max(0, int(self.recovery_timeout - (time.time() - self.last_state_change))) if self.state == "OPEN" else 0
        }

# 全局断路器单例
circuit_breaker = CircuitBreaker(window_size=10, failure_threshold=0.5, recovery_timeout=60.0)

import concurrent.futures

class DualModelGateway:
    """
    工业级主备对冲竞速网关 (Speculative Hedged Racing Gateway):
    1. 彻底锁死 max_retries=0，坚决杜绝底层 HTTP 客户端隐式重试（消除 47 秒长尾）
    2. 硬时间预算 (Hard Deadline): 单次请求物理超时压至 16.0 秒
    3. 对冲竞速 (Hedged Requests): 主备模型并发同时请求，谁先返回 200 毫秒级采纳，同时掐断慢请求
    """
    def __init__(self, timeout_seconds: float = 16.0):
        self.timeout_seconds = timeout_seconds
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.base_url = os.getenv("DASHSCOPE_BASE_URL")
        self.primary_model_name = os.getenv("DASHSCOPE_MODEL_NAME", "qwen3.8-flash")
        self.backup_model_name = os.getenv("DASHSCOPE_BACKUP_MODEL_NAME", "qwen3.7-flash-2026-07-15")

        # 锁死 max_retries=0，彻底阻断 15s+15s+15s 的隐式重试叠加！
        self.primary_llm = ChatOpenAI(
            model=self.primary_model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0,
            timeout=self.timeout_seconds,
            max_retries=0
        )

        self.backup_llm = ChatOpenAI(
            model=self.backup_model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0,
            timeout=self.timeout_seconds,
            max_retries=0
        )
        print(f"[LLM Gateway] 🚀 对冲竞速网关启动: 主[{self.primary_model_name}] vs 备[{self.backup_model_name}] | 硬时间预算: {self.timeout_seconds}s | 隐式重试: 0")

    def _execute_single(self, runner: Any, call_type: str, arg: Any, schema: Any = None) -> Any:
        if call_type == "invoke":
            return runner.invoke(arg)
        else:
            structured = runner.with_structured_output(schema)
            return structured.invoke(arg)

    def _race_models(self, call_type: str, arg: Any, tools: Optional[List[Any]] = None, schema: Any = None) -> Any:
        """主备对冲竞速执行器"""
        circuit_breaker.before_call()

        primary_runner = self.primary_llm.bind_tools(tools) if (tools and call_type == "invoke") else self.primary_llm
        backup_runner = self.backup_llm.bind_tools(tools) if (tools and call_type == "invoke") else self.backup_llm

        print(f"[LLM Gateway] ⚡ 启动对冲竞速 (Race): 主[{self.primary_model_name}] 与 备[{self.backup_model_name}] 并发发起...")
        start_t = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_primary = executor.submit(self._execute_single, primary_runner, call_type, arg, schema)
            future_backup = executor.submit(self._execute_single, backup_runner, call_type, arg, schema)

            futures_map = {
                future_primary: self.primary_model_name,
                future_backup: self.backup_model_name
            }

            first_error = None
            try:
                # 谁先在硬时间预算内成功返回，就立即采纳谁的结果！
                for completed in concurrent.futures.as_completed(futures_map, timeout=self.timeout_seconds):
                    m_name = futures_map[completed]
                    try:
                        res = completed.result()
                        elapsed = time.time() - start_t
                        circuit_breaker.record_success()
                        print(f"[LLM Gateway] 🏆 对冲竞速胜出: 模型 [{m_name}] 仅耗时 {elapsed:.2f}s 率先返回！")
                        return res
                    except Exception as e:
                        first_error = e
                        print(f"[LLM Gateway] ⚠️ 模型 [{m_name}] 请求失败或超时: {e}")
            except concurrent.futures.TimeoutError:
                print(f"[LLM Gateway] 🚨 对冲竞速达到硬时间预算红线 ({self.timeout_seconds}s) 仍未返回！")
                circuit_breaker.record_failure(is_timeout=True)
                raise TimeoutError(f"对冲竞速所有模型在 {self.timeout_seconds}s 内均未能返回")

        circuit_breaker.record_failure(is_timeout=True)
        raise first_error or RuntimeError("对冲竞速模型调用全部失败")

    def invoke(self, messages: Any, tools: Optional[List[Any]] = None) -> Any:
        """通用对话对冲竞速"""
        return self._race_models(call_type="invoke", arg=messages, tools=tools)

    def invoke_structured(self, prompt: Any, schema: Any) -> Any:
        """结构化解析对冲竞速"""
        return self._race_models(call_type="structured", arg=prompt, schema=schema)

# 全局对冲网关单例 (绝对硬预算 8.0s)
llm_gateway = DualModelGateway(timeout_seconds=8.0)

