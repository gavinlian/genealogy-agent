# -*- coding: utf-8 -*-
lines = open("src/App.vue", encoding="utf-8").readlines()
in_script = False
for i, line in enumerate(lines, 1):
    if "<script setup" in line:
        in_script = True
    if not in_script:
        continue
    if line.count("'") % 2 == 1 and not line.strip().startswith("//"):
        print(i, line.rstrip()[:100])
