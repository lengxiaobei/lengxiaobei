"""
性能基准测试
============
快速基准测试，用于 CI 性能回归检测
"""
import time
import statistics


def quick_benchmark(name: str, func, iterations: int = 100) -> dict:
    """快速基准测试"""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)

    return {
        "name": name,
        "iterations": iterations,
        "mean_ms": statistics.mean(times) * 1000,
        "median_ms": statistics.median(times) * 1000,
        "stdev_ms": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
    }


def run_quick_benchmarks():
    """运行快速基准测试"""
    results = []

    print("\n=== LengXiaobei Quick Benchmarks ===\n")

    # JSON 操作
    import json
    results.append(quick_benchmark(
        "json.dumps (small)",
        lambda: json.dumps({"key": "value"}),
        1000
    ))

    results.append(quick_benchmark(
        "json.loads (small)",
        lambda: json.loads('{"key": "value"}'),
        1000
    ))

    results.append(quick_benchmark(
        "json.dumps (1KB)",
        lambda: json.dumps({"data": "x" * 1000}),
        500
    ))

    # 字符串操作
    results.append(quick_benchmark(
        "string.split",
        lambda: "a b c d e".split(),
        1000
    ))

    results.append(quick_benchmark(
        "string.join",
        lambda: ",".join(["a", "b", "c", "d", "e"]),
        1000
    ))

    # 正则表达式
    import re
    pattern = re.compile(r'\d+')
    results.append(quick_benchmark(
        "regex.match",
        lambda: pattern.match("123 abc"),
        500
    ))

    # 字典操作
    d = {}
    results.append(quick_benchmark(
        "dict.setitem",
        lambda: d.update({time.time(): "value"}),
        1000
    ))

    # 列表操作
    lst = []
    results.append(quick_benchmark(
        "list.append",
        lambda: lst.append("x"),
        1000
    ))

    # 时间操作
    results.append(quick_benchmark(
        "time.time",
        lambda: time.time(),
        10000
    ))

    results.append(quick_benchmark(
        "time.strftime",
        lambda: time.strftime("%Y-%m-%d %H:%M:%S"),
        1000
    ))

    # 打印结果
    print(f"{'Benchmark':<30} {'Mean':>10} {'Median':>10} {'Stdev':>10}")
    print("-" * 62)
    for r in results:
        print(f"{r['name']:<30} {r['mean_ms']:>9.3f}ms {r['median_ms']:>9.3f}ms {r['stdev_ms']:>9.3f}ms")

    print(f"\n{len(results)} benchmarks completed\n")

    return results


if __name__ == "__main__":
    run_quick_benchmarks()
