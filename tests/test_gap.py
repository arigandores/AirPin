gap = 50
pw = 2560

# Simulate 2 right panels
panels = [
    (0, "main"),
    (pw, "right"),       # VDD1 at x=2560
    (pw * 2, "right"),   # VDD2 at x=5120
]

right_n = 0
rendered = []
for actual_x, pos in panels:
    if pos == "main":
        rendered.append((actual_x, "main"))
    else:
        right_n += 1
        rendered.append((actual_x + gap * right_n, pos))

for off, pos in rendered:
    end = off + pw
    print(pos + ": " + str(off) + "-" + str(end))

for i in range(len(rendered) - 1):
    visual_gap = rendered[i + 1][0] - (rendered[i][0] + pw)
    print("Gap " + rendered[i][1] + " -> " + rendered[i + 1][1] + ": " + str(visual_gap) + "px")
