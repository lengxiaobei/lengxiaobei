#!/usr/bin/env python3
"""
重置熔断保护状态
"""
import sys
import os

sys.path.insert(0, '/Users/panhao/projects/lengxiaobei')

from src.circuit_breaker import get_circuit_breaker

def reset_circuit_breaker():
    """重置熔断保护状态"""
    cb = get_circuit_breaker()
    print("熔断保护当前状态:")
    status = cb.get_health_status()
    for key, value in status.items():
        print(f"  {key}: {value}")

    print("\n正在重置熔断保护...")
    cb._reset()
    print("熔断保护已重置")

    print("\n重置后的状态:")
    status = cb.get_health_status()
    for key, value in status.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    reset_circuit_breaker()