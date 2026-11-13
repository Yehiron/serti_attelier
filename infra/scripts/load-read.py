#!/usr/bin/env python3
"""Read-only load test: concurrent GETs for a fixed time; no data is written."""
import random, statistics, sys, threading, time, urllib.request, urllib.error
ORIGIN = sys.argv[1].rstrip("/")  # e.g. http://127.0.0.1:3101 or https://staging.example
PATHS = ["/es", "/es/joyeria", "/es/piezas/aretes-esmeralda-2", "/es/legal/envios", "/en", "/es/joyeria?piedra=esmeralda"]
def run(conc, seconds):
    lat, errs, codes = [], 0, {}
    lock = threading.Lock(); stop = time.time() + seconds
    def worker():
        nonlocal errs
        while time.time() < stop:
            p = random.choice(PATHS); t = time.perf_counter()
            try:
                with urllib.request.urlopen(ORIGIN + p, timeout=30) as r: r.read(); c = r.status
            except urllib.error.HTTPError as e: c = e.code
            except Exception: c = "exc"
            d = (time.perf_counter() - t) * 1000
            with lock:
                lat.append(d); codes[c] = codes.get(c, 0) + 1
                if c != 200: errs += 1
    ts = [threading.Thread(target=worker) for _ in range(conc)]
    [t.start() for t in ts]; [t.join() for t in ts]
    q = statistics.quantiles(lat, n=100)
    print(f"conc={conc:3d} req={len(lat):5d} rps={len(lat)/seconds:6.1f} p50={q[49]:6.0f}ms p95={q[94]:6.0f}ms p99={q[98]:6.0f}ms errores={errs} {codes}", flush=True)
for p in PATHS:  # warm caches
    urllib.request.urlopen(ORIGIN + p, timeout=60).read()
for conc in (1, 10, 25, 50):
    run(conc, 20)
