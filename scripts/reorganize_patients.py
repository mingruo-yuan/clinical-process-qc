# -*- coding: utf-8 -*-
"""Reorganize name-based json files into per-patient folders."""
import os, json, sys, io, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MOCK = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mock_data"))

jsons = sorted([f for f in os.listdir(MOCK) if f.endswith(".json")])
print("found:", jsons)

next_no = 2
mapping = []
for j in jsons:
    src = os.path.join(MOCK, j)
    folder = os.path.join(MOCK, f"patient_{next_no:03d}")
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, "patient.json")
    shutil.move(src, dst)
    os.makedirs(os.path.join(folder, "外院报告"), exist_ok=True)
    name = json.load(open(dst, encoding="utf-8")).get("病案首页", {}).get("姓名", "?")
    mapping.append((f"patient_{next_no:03d}", name))
    next_no += 1

for folder, name in mapping:
    print(f"{folder}  <-  {name}")
print("done,", len(mapping), "patients organized")
