# -*- coding: utf-8 -*-
lines = open("src/App.vue", encoding="utf-8").readlines()
for i, line in enumerate(lines, 1):
    if i > 672:
        break
    if ("{{" in line or ":placeholder=" in line) and line.count("'") % 2 == 1:
        print(i, line.rstrip()[:100])
