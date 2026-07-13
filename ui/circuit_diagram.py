"""Schematic diagram renderer for an equivalent-circuit tree (from
core.circuit_library) -- lets a researcher SEE the circuit topology
they're fitting (element symbols in their series/parallel arrangement),
not just read a text label like "Rs(Rct(Q-Wo))", and optionally see each
symbol annotated with its fitted value.

This draws standard-ish schematic symbols (box resistor, parallel-plate
capacitor, CPE as a capacitor with a diagonal arrow, a hatched box for
Warburg elements, a small ladder icon for the transmission-line element,
a labeled box for the Gerischer element) via matplotlib patches/lines --
not a full CAD-quality symbol library, but enough to make the topology
immediately legible, which is the actual goal (traceability, per this
app's design brief) rather than schematic-capture precision.
"""
import numpy as np
from matplotlib.patches import Rectangle

from core.circuit_library import element_param_names
from . import theme

_LEAF_W = 2.6
_LEAF_H = 1.3
_GAP = 0.7


def _measure(node) -> tuple[float, float]:
    kind = node[0]
    if kind == "elem":
        return _LEAF_W, _LEAF_H
    children = node[1]
    sizes = [_measure(c) for c in children]
    if kind == "series":
        width = sum(w for w, h in sizes) + _GAP * (len(sizes) + 1)
        height = max(h for w, h in sizes)
        return width, height
    if kind == "parallel":
        width = max(w for w, h in sizes) + _GAP * 2
        height = sum(h for w, h in sizes) + _GAP * (len(sizes) - 1)
        return width, height
    raise ValueError(f"Unknown node type: {kind}")


def _short_label(kind: str, prefix: str, params: dict) -> str:
    names = element_param_names(kind, prefix)
    parts = []
    for name in names:
        if name in params:
            suffix = name[len(prefix):].lstrip("_") or kind
            parts.append(f"{suffix}={params[name]:.4g}")
    return ", ".join(parts)


def _draw_element(ax, node, x: float, y: float, width: float, height: float, params: dict):
    _, kind, prefix = node
    cx, cy = x + width / 2, y + height / 2

    if kind == "R":
        box_w, box_h = width * 0.5, height * 0.32
        ax.add_patch(Rectangle((cx - box_w / 2, cy - box_h / 2), box_w, box_h,
                                fill=False, edgecolor=theme.RAW, linewidth=1.6))
        ax.plot([x, cx - box_w / 2], [cy, cy], color=theme.INK, linewidth=1.1)
        ax.plot([cx + box_w / 2, x + width], [cy, cy], color=theme.INK, linewidth=1.1)

    elif kind in ("C", "Q"):
        gap = width * 0.07
        plate_h = height * 0.5
        ax.plot([cx - gap, cx - gap], [cy - plate_h / 2, cy + plate_h / 2], color=theme.FIT, linewidth=2.2)
        ax.plot([cx + gap, cx + gap], [cy - plate_h / 2, cy + plate_h / 2], color=theme.FIT, linewidth=2.2)
        if kind == "Q":
            ax.annotate("", xy=(cx + gap * 2.4, cy + plate_h * 0.55),
                        xytext=(cx - gap * 2.4, cy - plate_h * 0.55),
                        arrowprops=dict(arrowstyle="-|>", color=theme.FIT, linewidth=1.3))
        ax.plot([x, cx - gap], [cy, cy], color=theme.INK, linewidth=1.1)
        ax.plot([cx + gap, x + width], [cy, cy], color=theme.INK, linewidth=1.1)

    elif kind in ("L", "La"):
        span = width * 0.5
        start_x = cx - span / 2
        xs = np.linspace(start_x, start_x + span, 200)
        ys = cy + (height * 0.16) * np.abs(np.sin(np.linspace(0, 4 * np.pi, 200)))
        ax.plot(xs, ys, color=theme.GOOD, linewidth=1.6)
        ax.plot([x, start_x], [cy, cy], color=theme.INK, linewidth=1.1)
        ax.plot([start_x + span, x + width], [cy, cy], color=theme.INK, linewidth=1.1)

    elif kind in ("W", "Wo", "Ws", "Winf", "Ma", "Mg"):
        box_w, box_h = width * 0.55, height * 0.4
        ax.add_patch(Rectangle((cx - box_w / 2, cy - box_h / 2), box_w, box_h,
                                fill=False, edgecolor=theme.RAW, linewidth=1.6))
        n_hatch = 4
        for k in range(n_hatch):
            hx = cx - box_w / 2 + box_w * (k + 0.5) / n_hatch
            ax.plot([hx - box_w / (2.4 * n_hatch), hx + box_w / (2.4 * n_hatch)],
                    [cy - box_h / 2, cy + box_h / 2], color=theme.RAW, linewidth=0.8)
        ax.plot([x, cx - box_w / 2], [cy, cy], color=theme.INK, linewidth=1.1)
        ax.plot([cx + box_w / 2, x + width], [cy, cy], color=theme.INK, linewidth=1.1)

    elif kind == "T":
        # Simplified ladder icon (R-rungs down to a CPE rail) to suggest
        # a distributed porous-electrode element -- not a literal N-stage
        # circuit, just a recognizable "this is a transmission line" mark.
        n_rungs = 3
        span = width * 0.62
        start_x = cx - span / 2
        top_y = cy + height * 0.14
        bot_y = cy - height * 0.14
        ax.plot([x, start_x], [cy, cy], color=theme.INK, linewidth=1.1)
        ax.plot([start_x, start_x + span], [top_y, top_y], color=theme.INK, linewidth=1.0)
        ax.plot([start_x, start_x + span], [bot_y, bot_y], color=theme.FIT, linewidth=1.6)
        for k in range(n_rungs):
            rx = start_x + span * (k + 0.5) / n_rungs
            ax.plot([rx, rx], [bot_y, top_y], color=theme.RAW, linewidth=1.3)
        ax.plot([start_x + span, x + width], [cy, cy], color=theme.INK, linewidth=1.1)

    elif kind in ("G", "Ga", "Gb"):
        box_w, box_h = width * 0.5, height * 0.4
        ax.add_patch(Rectangle((cx - box_w / 2, cy - box_h / 2), box_w, box_h,
                                fill=False, edgecolor=theme.GOOD, linewidth=1.6))
        ax.plot([x, cx - box_w / 2], [cy, cy], color=theme.INK, linewidth=1.1)
        ax.plot([cx + box_w / 2, x + width], [cy, cy], color=theme.INK, linewidth=1.1)

    else:
        ax.plot([x, x + width], [cy, cy], color=theme.INK, linewidth=1.1)

    ax.annotate(kind, (cx, cy + height * 0.34), ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=theme.INK)
    label = _short_label(kind, prefix, params)
    if label:
        ax.annotate(label, (cx, y - height * 0.16), ha="center", va="top",
                    fontsize=7, color=theme.INK_DIM)


def _draw(ax, node, x: float, y: float, width: float, height: float, params: dict):
    """Draw `node` inside box (x, y, width, height); returns (entry, exit)
    wire-connection points on the left/right edges."""
    kind = node[0]
    cy = y + height / 2

    if kind == "elem":
        _draw_element(ax, node, x, y, width, height, params)
        return (x, cy), (x + width, cy)

    children = node[1]

    if kind == "series":
        entry = (x, cy)
        cx = x + _GAP
        prev_x = x
        for child in children:
            cw, ch = _measure(child)
            child_y = cy - ch / 2
            in_pt, out_pt = _draw(ax, child, cx, child_y, cw, ch, params)
            ax.plot([prev_x, in_pt[0]], [cy, cy], color=theme.INK, linewidth=1.1)
            prev_x = out_pt[0]
            cx += cw + _GAP
        exit_pt = (x + width, cy)
        ax.plot([prev_x, exit_pt[0]], [cy, cy], color=theme.INK, linewidth=1.1)
        return entry, exit_pt

    if kind == "parallel":
        entry = (x, cy)
        exit_pt = (x + width, cy)
        left_bus_x = x + _GAP * 0.5
        right_bus_x = x + width - _GAP * 0.5
        cursor_y = y + height
        branch_cys = []
        for child in children:
            cw, ch = _measure(child)
            cursor_y -= ch
            child_x = x + _GAP + (width - _GAP * 2 - cw) / 2
            branch_cy = cursor_y + ch / 2
            in_pt, out_pt = _draw(ax, child, child_x, cursor_y, cw, ch, params)
            ax.plot([left_bus_x, in_pt[0]], [branch_cy, in_pt[1]], color=theme.INK, linewidth=1.1)
            ax.plot([out_pt[0], right_bus_x], [out_pt[1], branch_cy], color=theme.INK, linewidth=1.1)
            branch_cys.append(branch_cy)
            cursor_y -= _GAP
        ax.plot([left_bus_x, left_bus_x], [min(branch_cys), max(branch_cys)], color=theme.INK, linewidth=1.1)
        ax.plot([right_bus_x, right_bus_x], [min(branch_cys), max(branch_cys)], color=theme.INK, linewidth=1.1)
        ax.plot([entry[0], left_bus_x], [cy, cy], color=theme.INK, linewidth=1.1)
        ax.plot([right_bus_x, exit_pt[0]], [cy, cy], color=theme.INK, linewidth=1.1)
        return entry, exit_pt

    raise ValueError(f"Unknown node type: {kind}")


def draw_circuit(fig, spec, params: dict | None = None) -> None:
    """Draw circuit `spec` (a core.circuit_library.CircuitSpec) onto a
    freshly-cleared matplotlib `fig`. If `params` (a {param_name: value}
    dict, e.g. an EquivalentCircuitFitResult.params) is given, each
    symbol is annotated with its own fitted value(s)."""
    fig.clear()
    ax = fig.add_subplot(111)
    width, height = _measure(spec.tree)
    _draw(ax, spec.tree, 0.0, 0.0, width, height, params or {})
    pad_x, pad_y = width * 0.06, height * 0.35
    ax.set_xlim(-pad_x, width + pad_x)
    ax.set_ylim(-pad_y, height + pad_y * 0.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(spec.display, fontsize=10, color=theme.INK)
    fig.patch.set_facecolor(theme.PANEL)
    ax.set_facecolor(theme.PANEL)
    fig.tight_layout()
