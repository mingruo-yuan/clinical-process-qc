# -*- coding: utf-8 -*-
"""
一键生成 S02-S09 各技能的分析结果缓存。

用法(在 专病库系统/ 目录下执行):
    python scripts/generate_cache.py                          # 全部患者 x S02-S09, 仅补缺失缓存
    python scripts/generate_cache.py --force                  # 全部患者 x S02-S09, 强制重跑
    python scripts/generate_cache.py --skills S07,S09         # 只跑指定技能
    python scripts/generate_cache.py --patient patient_002    # 只跑指定患者(可多次/逗号分隔)
    python scripts/generate_cache.py --retry 3                # 失败重试次数(默认2)
    python scripts/generate_cache.py --allow-mock             # 未配置API时仍生成Mock缓存(不推荐)

生成的缓存与 app.py 的缓存键完全一致(patient_id=文件夹名, extra=None,
llm_mode=是否配置api_key), Streamlit 端可直接命中读取。
"""
import sys, io, os, time, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from skills import SKILL_REGISTRY
from skills.base import SkillStatus
from utils import result_cache, llm_client
from utils.data_loader import load_patient, list_patients

# 默认生成范围: S02-S09 (S01为OCR, 需图片输入, 缓存键不同, 默认跳过)
DEFAULT_SKILLS = [f"S{i:02d}" for i in range(2, 10)]
S01_NEEDS_IMAGES = "S01"


def build_parser():
    p = argparse.ArgumentParser(description="一键生成 S02-S09 技能结果缓存")
    p.add_argument("--skills", default=",".join(DEFAULT_SKILLS),
                   help=f"要运行的技能, 逗号分隔, 默认: {','.join(DEFAULT_SKILLS)}")
    p.add_argument("--patient", action="append", default=[],
                   help="只运行指定患者(id如patient_002), 可多次或逗号分隔; 默认全部")
    p.add_argument("--force", action="store_true", help="强制重跑, 忽略已有缓存")
    p.add_argument("--retry", type=int, default=2, help="单技能失败重试次数(默认2)")
    p.add_argument("--allow-mock", action="store_true", help="未配置OPENAI_API_KEY时仍生成Mock缓存")
    return p


def parse_skills(raw: str):
    skills = [s.strip().upper() for s in raw.split(",") if s.strip()]
    unknown = [s for s in skills if s not in SKILL_REGISTRY]
    if unknown:
        sys.exit(f"未知技能: {', '.join(unknown)}, 可用: {', '.join(SKILL_REGISTRY)}")
    if S01_NEEDS_IMAGES in skills:
        print("提示: S01(OCR)需图片输入且缓存键含图片信息, 本脚本跳过, 请在App内上传/选择图片后执行。")
        skills.remove(S01_NEEDS_IMAGES)
    return skills


def parse_patients(ids):
    if not ids:
        return list_patients()
    wanted = set()
    for x in ids:
        wanted.update(t.strip() for t in x.split(",") if t.strip())
    known = {p["id"] for p in list_patients()}
    unknown = [w for w in wanted if w not in known]
    if unknown:
        sys.exit(f"未知患者: {', '.join(unknown)}, 可用: {', '.join(sorted(known))}")
    return [p for p in list_patients() if p["id"] in wanted]


def result_ok(result) -> bool:
    """判定结果是否可接受: 失败或详情为空视为需要重试"""
    if result.status == SkillStatus.FAILED:
        return False
    if result.status == SkillStatus.NOT_TRIGGERED or result.status == SkillStatus.NEED_MORE_DATA:
        return True
    if result.status == SkillStatus.PARTIAL and not (result.详情 or {}):
        return False
    return True


def run_one(skill_id, patient_info, llm_mode, force, retry):
    patient_id = patient_info["id"]
    patient_data = load_patient(patient_info["folder"])["data"]

    if not force:
        cached = result_cache.load(skill_id, patient_id, patient_data, None, llm_mode)
        if cached is not None:
            return "缓存命中(跳过)", cached.get("status", "")

    skill = SKILL_REGISTRY[skill_id]()
    last = None
    for attempt in range(1, retry + 2):
        try:
            result = skill.analyze(patient_data)
        except Exception as e:
            last = f"异常: {e}"
            if attempt <= retry:
                time.sleep(2)
            continue
        if result_ok(result):
            result_cache.save(skill_id, patient_id, patient_data, result.to_dict(), None, llm_mode)
            return "完成", result.status.value
        last = f"结果异常({result.status.value})"
        if attempt <= retry:
            time.sleep(2)
    return f"失败({last})", "failed"


def main():
    args = build_parser().parse_args()
    skills = parse_skills(args.skills)
    patients = parse_patients(args.patient)
    llm_mode = bool(llm_client.LLM_CONFIG.get("api_key"))

    if not llm_mode and not args.allow_mock:
        sys.exit("未配置 OPENAI_API_KEY, 直接运行会生成Mock假缓存。"
                 "如确认需要请加 --allow-mock, 或在项目 utils/llm_client.py 配置后重试。")

    print(f"技能: {', '.join(skills)}")
    print(f"患者: {len(patients)} 个 -> {', '.join(p['id'] for p in patients)}")
    print(f"LLM: {'已配置(' + llm_client.LLM_CONFIG.get('model', '') + ')' if llm_mode else 'Mock模式'}")
    print(f"模式: {'强制重跑' if args.force else '仅补缺失缓存'}, 重试{args.retry}次")
    print("-" * 60)

    total, ok, skip, fail = 0, 0, 0, 0
    failed_list = []
    for p in patients:
        print(f"[{p['id']}]")
        for sid in skills:
            msg, status = run_one(sid, p, llm_mode, args.force, args.retry)
            total += 1
            flag = "OK " if msg == "完成" else ("SKIP" if msg.startswith("缓存命中") else "FAIL")
            print(f"  {sid} [{flag}] {msg}")
            if msg == "完成":
                ok += 1
            elif msg.startswith("缓存命中"):
                skip += 1
            else:
                fail += 1
                failed_list.append((p["id"], sid, status))

    print("-" * 60)
    print(f"总计 {total}: 完成 {ok}, 缓存命中 {skip}, 失败 {fail}")
    if failed_list:
        print("失败清单:")
        for pid, sid, st in failed_list:
            print(f"  - {pid} {sid} (status={st})")
        sys.exit(1)


if __name__ == "__main__":
    main()
