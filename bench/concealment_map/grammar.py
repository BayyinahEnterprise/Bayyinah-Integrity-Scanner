"""Enumerate one-page PDFs from a grammar of ways to hide a line of text.

Each document has one ordinary visible line and one payload line whose
drawing is controlled by eight independent choices. ``build(cfg,
with_payload=False)`` writes the same page without the payload, which is
what the oracle renders to decide whether the payload was visible.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import pikepdf

MARK = "ZQXMARK"
PAYLOAD = f"{MARK} quarterly ledger alpha seven"
PAGE_W, PAGE_H = 612, 792

DIMENSIONS: dict[str, tuple[str, ...]] = {
    "position": ("on_page", "off_td", "off_tm", "off_cm", "edge"),
    "size": ("11", "3", "1", "0.3"),
    "render_mode": ("0", "3", "7", "1"),
    "color": ("black", "white", "near_white"),
    "overlay": ("none", "white_box"),
    "clip": ("none", "clip_away"),
    "alpha": ("1", "0"),
    "scale": ("1", "tiny"),
}
BASELINE: dict[str, str] = {k: v[0] for k, v in DIMENSIONS.items()}


@dataclass(frozen=True)
class Config:
    position: str = "on_page"
    size: str = "11"
    render_mode: str = "0"
    color: str = "black"
    overlay: str = "none"
    clip: str = "none"
    alpha: str = "1"
    scale: str = "1"

    def key(self) -> str:
        return "|".join(f"{k}={v}" for k, v in asdict(self).items()
                        if v != BASELINE[k]) or "baseline"

    def changed(self) -> int:
        return sum(1 for k, v in asdict(self).items() if v != BASELINE[k])


def enumerate_configs(max_changed: int | None = None) -> Iterator[Config]:
    """Every combination, or only those differing from the baseline in at
    most ``max_changed`` dimensions (the small-scope cut)."""
    names = list(DIMENSIONS)
    for combo in itertools.product(*(DIMENSIONS[n] for n in names)):
        cfg = Config(**dict(zip(names, combo)))
        if max_changed is None or cfg.changed() <= max_changed:
            yield cfg


def _payload_ops(cfg: Config) -> str:
    size = cfg.size
    color = {"black": "0 g 0 G", "white": "1 g 1 G", "near_white": "0.985 g 0.985 G"}[cfg.color]
    x, y = 72, 400
    pre, place = "", f"{x} {y} Td"
    if cfg.position == "off_td":
        place = f"{x} 2000 Td"
    elif cfg.position == "off_tm":
        place = f"1 0 0 1 -500 {y} Tm"
    elif cfg.position == "off_cm":
        pre = "1 0 0 1 0 3000 cm"
    elif cfg.position == "edge":
        place = f"{PAGE_W - 8} {y} Td"
    if cfg.scale == "tiny":
        tx, ty = (x, y) if cfg.position in ("on_page", "off_cm") else (
            (x, 2000) if cfg.position == "off_td" else
            (-500, y) if cfg.position == "off_tm" else (PAGE_W - 8, y))
        place = f"0.001 0 0 0.001 {tx} {ty} Tm"
    ops = ["q"]
    if cfg.clip == "clip_away":
        ops.append("500 700 40 40 re W n")
    if cfg.alpha == "0":
        ops.append("/GSa gs")
    if pre:
        ops.append(pre)
    ops += ["BT", f"/F1 {size} Tf", color, f"{cfg.render_mode} Tr", place,
            f"({PAYLOAD}) Tj", "ET", "Q"]
    return "\n".join(ops)


def build(cfg: Config, path: str, with_payload: bool = True) -> None:
    body = "BT /F1 11 Tf 0 g 72 700 Td (Quarterly vendor summary. All figures are final.) Tj ET"
    parts = [body]
    if with_payload:
        parts.append(_payload_ops(cfg))
    if cfg.overlay == "white_box":
        parts.append("q 1 g 60 380 500 40 re f Q")
    pdf = pikepdf.new()
    font = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
        BaseFont=pikepdf.Name.Helvetica))
    gs = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, ca=0, CA=0)
    page = pikepdf.Dictionary(
        Type=pikepdf.Name.Page, MediaBox=[0, 0, PAGE_W, PAGE_H],
        Resources=pikepdf.Dictionary(
            Font=pikepdf.Dictionary(F1=font),
            ExtGState=pikepdf.Dictionary(GSa=gs)),
        Contents=pdf.make_stream("\n".join(parts).encode("latin-1")))
    pdf.pages.append(pikepdf.Page(pdf.make_indirect(page)))
    pdf.save(path, deterministic_id=True)
    pdf.close()
