# Generates prahari-explained.html — the ELI5 page. Run: python3 build.py

def dots(ox, found, maybe, cls_found):
    out = []
    for i in range(100):
        r, c = divmod(i, 10)
        cx, cy = ox + c * 22, 20 + r * 22
        if i < found:
            cls = cls_found
        elif i < found + maybe:
            cls = "f-green soft"
        else:
            cls = "f-road"
        out.append(f'<circle cx="{cx}" cy="{cy}" r="8" class="{cls}"/>')
    return "\n".join(out)

def plate_chars(text, x0, y, step, wrong):
    hi = "".join(
        f'<rect x="{x0 + i*step - 2}" y="{y-27}" width="{step+3}" height="34" rx="3" class="f-amber"/>'
        for i in wrong)
    chars = "".join(
        f'<text x="{x0 + i*step}" y="{y}" class="plate-t">{ch}</text>'
        for i, ch in enumerate(text) if ch != " ")
    return hi + chars

SCREENS = ["road", "hall", "depot", "road", "gate", "hall"]
POS = [(8, 40), (105, 40), (202, 40), (8, 132), (105, 132), (202, 132)]

def wall(after):
    parts = ['<rect x="0" y="0" width="300" height="210" rx="12" fill="#0E1216"/>',
             '<text x="150" y="26" text-anchor="middle" class="wall-t">control room wall</text>']
    for kind, (x, y) in zip(SCREENS, POS):
        parts.append(f'<use href="#scr-{kind}" x="{x}" y="{y}" width="90" height="64"/>')
        if kind == "road":
            parts.append(f'<rect x="{x+35}" y="{y+35}" width="22" height="18" fill="none" stroke="#3FCB86" stroke-width="2.5"/>')
            parts.append(f'<text x="{x+46}" y="{y+31}" text-anchor="middle" class="ov-t" fill="#3FCB86">plate</text>')
        elif not after:
            parts.append(f'<rect x="{x}" y="{y}" width="90" height="64" fill="#0B0E12" opacity=".72"/>')
            parts.append(f'<text x="{x+45}" y="{y+37}" text-anchor="middle" class="ov-t" fill="#C9D1D9">no cars</text>')
        elif kind == "hall":
            parts.append(f'<rect x="{x+40}" y="{y+29}" width="16" height="26" fill="none" stroke="#F0B545" stroke-width="2.5"/>')
            parts.append(f'<text x="{x+48}" y="{y+24}" text-anchor="middle" class="ov-t" fill="#F0B545">person</text>')
        elif kind == "depot":
            parts.append(f'<rect x="{x+50}" y="{y+22}" width="36" height="30" fill="none" stroke="#F0B545" stroke-width="2.5"/>')
            parts.append(f'<text x="{x+45}" y="{y+14}" text-anchor="middle" class="ov-t" fill="#F0B545">crowd 34</text>')
        elif kind == "gate":
            parts.append(f'<rect x="{x+54}" y="{y+26}" width="16" height="28" fill="none" stroke="#F0B545" stroke-width="2.5"/>')
            parts.append(f'<text x="{x+45}" y="{y+14}" text-anchor="middle" class="ov-t" fill="#F0B545">loitering</text>')
    return "\n".join(parts)

html = open("template.html", encoding="utf-8").read()
html = html.replace("{{DOTS_OLD}}", dots(40, 32, 0, "f-ink"))
html = html.replace("{{DOTS_NEW}}", dots(340, 48, 35, "f-green"))
html = html.replace("{{PLATE_BAD}}", plate_chars("6J 01 A8 I234", 214, 72, 16, [0, 7, 9]))
html = html.replace("{{WALL_BEFORE}}", wall(False))
html = html.replace("{{WALL_AFTER}}", wall(True))
open("prahari-explained.html", "w", encoding="utf-8").write(html)
print("wrote prahari-explained.html", len(html), "bytes")
