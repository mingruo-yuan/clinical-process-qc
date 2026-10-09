# -*- coding: utf-8 -*-
"""Generate simulated medical report images for OCR testing."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "mock_data", "patient_001", "外院报告")
OUT = os.path.abspath(OUT)


def font(size):
    for p in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_report(fname, hospital, title, lines):
    W, H = 1100, 1550
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title = font(40)
    f_head = font(26)
    f_body = font(28)
    f_line = font(24)
    d.rectangle([0, 0, W - 1, 130], fill=(0, 76, 153))
    d.text((W // 2, 30), hospital, font=f_head, fill="white", anchor="ma")
    d.text((W // 2, 75), title, font=f_title, fill="white", anchor="ma")
    d.line([40, 155, W - 40, 155], fill=(0, 76, 153), width=3)
    y = 190
    for i, line in enumerate(lines):
        if i < 4:
            d.text((60, y), line, font=f_head, fill=(0, 0, 0))
            y += 45
        else:
            d.text((60, y), line, font=f_body, fill=(30, 30, 30))
            y += 55
    d.line([40, y + 20, W - 40, y + 20], fill=(200, 200, 200), width=2)
    d.text((60, y + 40), "报告医生：王XX    审核医生：李XX", font=f_line, fill=(120, 120, 120))
    d.text((60, y + 80), "报告日期：2024-01-06    检查号：EX2024001", font=f_line, fill=(120, 120, 120))
    img.save(os.path.join(OUT, fname), quality=90)
    print("saved:", fname)


make_report("外院喉镜报告.jpg", "山东省立医院", "电子喉镜报告单", [
    "姓名：张XX    性别：男    年龄：59岁    病案号：WL2023110",
    "检查部位：喉部    检查方法：电子喉镜",
    "",
    "检查所见：",
    "右侧声带全长可见菜花样新生物，表面粗糙，触之易出血，",
    "病变累及前联合，右侧声带活动受限，左侧声带及室带未见异常。",
    "会厌、披裂、梨状窝对称，未见新生物。",
    "",
    "检查诊断：",
    "右侧声带占位性病变，考虑喉癌，建议病理活检。",
])

make_report("外院CT报告.jpg", "山东省立医院", "颈部CT平扫+增强报告单", [
    "姓名：张XX    性别：男    年龄：59岁    病案号：WL2023110",
    "检查部位：颈部    扫描方式：平扫+增强",
    "",
    "影像所见：",
    "右侧声门区见软组织肿块影，大小约2.5cm×1.8cm×1.5cm，",
    "不均匀强化，边界欠清晰，右侧声带增厚。",
    "右侧颈深部Ⅱ、Ⅲ区见多发肿大淋巴结，最大者短径约1.2cm。",
    "甲状软骨板未见明显骨质破坏，双肺、纵隔未见转移。",
    "",
    "诊断意见：",
    "右侧声门区占位，喉癌可能性大；右侧颈部淋巴结肿大。",
])

make_report("外院出院小结.jpg", "山东省立医院", "出院小结", [
    "姓名：张XX    性别：男    年龄：59岁    入院日期：2023-12-20  出院日期：2023-12-28",
    "入院诊断：声音嘶哑3个月余",
    "出院诊断：右侧声带肿物性质待查",
    "",
    "诊疗经过：",
    "患者因声音嘶哑3月余入院，电子喉镜示右侧声带新生物，",
    "予以喉镜活检，病理回报（右侧声带）鳞状细胞癌，中分化，",
    "建议转上级医院行手术治疗。",
    "",
    "出院医嘱：",
    "1.戒烟酒；2.建议至齐鲁医院行喉癌根治手术；3.不适随诊。",
])

print("done")
