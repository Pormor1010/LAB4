"""Server-side SVG charts for the Lab 04 simulator.

The browser only draws what this module was given: every coordinate comes
from an array parsed out of an ngspice output file. Nothing here contains a
sample waveform, a placeholder curve or a hard-coded gain.

Two figures are produced:

* :func:`bode_svg`      - |Vout/Vin| in dB and phase in degrees vs frequency
* :func:`waveform_svg`  - Vin and Vout vs time in milliseconds
"""

from __future__ import annotations

import math

# Palette shared with static/style.css
INK = "#17344b"
MUTED = "#546d83"
GRID = "#dfe9f1"
AXIS = "#8aa4b8"
TEAL = "#0c7d72"
ORANGE = "#b85c2c"
NAVY = "#103658"

WIDTH = 720


def _nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    """Return round tick values that cover ``low``..``high`` completely.

    The first tick is always <= ``low`` and the last one >= ``high`` so the
    plotted curve can never run past the labelled axis.
    """
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        return [low]
    span = high - low
    raw_step = span / max(count - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = magnitude * 10
    for factor in (1, 2, 2.5, 5, 10):
        if magnitude * factor >= raw_step:
            step = magnitude * factor
            break
    start = math.floor(low / step) * step
    stop = math.ceil(high / step) * step
    steps = int(round((stop - start) / step))
    return [round(start + index * step, 10) for index in range(steps + 1)]


def _format_tick(value: float, decimals: int = 1) -> str:
    """Format one tick, never printing ``-0`` for a value that rounds to zero."""
    if abs(value) < 1e-12:
        return "0"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def _tick_labels(ticks: list[float], scale: float = 1.0,
                 max_decimals: int = 2) -> list[str]:
    """Labels for ``ticks * scale`` using the fewest decimals that stay unique."""
    for decimals in range(max_decimals + 1):
        labels = [_format_tick(value * scale, decimals) for value in ticks]
        if len(set(labels)) == len(labels):
            return labels
    return [_format_tick(value * scale, max_decimals) for value in ticks]


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _svg_open(height: int, title: str) -> list[str]:
    return [
        f'<svg class="chart" viewBox="0 0 {WIDTH} {height}" '
        f'role="img" aria-label="{_escape(title)}" '
        'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{_escape(title)}</title>",
    ]


def _polyline(points: list[tuple[float, float]], colour: str, width: float = 2.2) -> str:
    if len(points) < 2:
        return ""
    path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (
        f'<polyline points="{path}" fill="none" stroke="{colour}" '
        f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def _legend(items: list[tuple[str, str, str]], x: float, y: float) -> str:
    parts = []
    cursor = x
    for label, colour, dash in items:
        parts.append(
            f'<line x1="{cursor:.1f}" y1="{y}" x2="{cursor + 22:.1f}" y2="{y}" '
            f'stroke="{colour}" stroke-width="3" {dash}/>'
        )
        parts.append(
            f'<text x="{cursor + 28:.1f}" y="{y + 4}" font-size="11" '
            f'fill="{MUTED}">{_escape(label)}</text>'
        )
        cursor += 28 + 7 * len(label) + 26
    return "".join(parts)


def bode_svg(data: dict) -> str:
    """Return the two-panel Bode figure built from AC sweep data."""
    freq = data["freq"]
    gain_db = data["gain_db"]
    phase = data["phase"]
    if not freq:
        return ""

    log_min = math.log10(freq[0])
    log_max = math.log10(freq[-1])
    log_span = log_max - log_min or 1.0

    left, right = 62, 26
    plot_w = WIDTH - left - right
    mag_top, mag_h = 62, 168
    ph_top, ph_h = mag_top + mag_h + 62, 132
    height = ph_top + ph_h + 66

    def x_of(f: float) -> float:
        return left + (math.log10(f) - log_min) / log_span * plot_w

    # ---- magnitude panel -------------------------------------------------
    g_min = min(gain_db)
    g_max = max(gain_db)
    if g_max - g_min < 6:
        mid = (g_max + g_min) / 2
        g_max, g_min = mid + 3, mid - 3
    mag_ticks = _nice_ticks(g_min, g_max, 6)
    g_lo, g_hi = mag_ticks[0], mag_ticks[-1]
    mag_labels = _tick_labels(mag_ticks, 1, 1)

    def y_mag(value: float) -> float:
        return mag_top + mag_h - (value - g_lo) / (g_hi - g_lo) * mag_h

    parts = _svg_open(height, "Bode plot: gain magnitude and phase")
    parts.append(
        f'<rect x="0" y="0" width="{WIDTH}" height="{height}" fill="#ffffff"/>'
    )

    for tick, label in zip(mag_ticks, mag_labels):
        y = y_mag(tick)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{MUTED}">{label}</text>'
        )

    # -3 dB reference line relative to the midband gain
    mid_db = data["midband_gain_db"]
    if math.isfinite(mid_db) and g_lo <= mid_db - 3.0103 <= g_hi:
        y = y_mag(mid_db - 3.0103)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{ORANGE}" stroke-width="1.2" stroke-dasharray="7 5"/>'
        )
        parts.append(
            f'<text x="{left + plot_w - 4}" y="{y - 6:.1f}" text-anchor="end" '
            f'font-size="10.5" fill="{ORANGE}">midband − 3 dB ('
            f'{mid_db - 3.0103:.1f} dB)</text>'
        )

    parts.append(
        f'<text x="14" y="{mag_top + mag_h / 2:.0f}" font-size="11" '
        f'fill="{MUTED}" transform="rotate(-90 14 {mag_top + mag_h / 2:.0f})" '
        'text-anchor="middle">Gain |Vout/Vin| (dB)</text>'
    )

    magnitude_points = [
        (x_of(f), y_mag(g)) for f, g in zip(freq, gain_db)
    ]
    parts.append(_polyline(magnitude_points, TEAL, 2.4))

    # ---- phase panel -----------------------------------------------------
    p_min = math.floor(min(phase) / 45) * 45
    p_max = math.ceil(max(phase) / 45) * 45
    if p_max - p_min < 45:
        p_min, p_max = p_min - 45, p_max + 45
    p_min = max(p_min, -360)
    p_max = min(p_max, 360)

    def y_ph(value: float) -> float:
        return ph_top + ph_h - (value - p_min) / (p_max - p_min) * ph_h

    for value in range(int(p_min), int(p_max) + 1, 45):
        y = y_ph(value)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{MUTED}">{value}</text>'
        )

    if p_min < 0 < p_max:
        y = y_ph(0)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{AXIS}" stroke-width="1.2"/>'
        )

    phase_points = [(x_of(f), y_ph(p)) for f, p in zip(freq, phase)]
    parts.append(_polyline(phase_points, ORANGE, 2.2))

    parts.append(
        f'<text x="14" y="{ph_top + ph_h / 2:.0f}" font-size="11" '
        f'fill="{MUTED}" transform="rotate(-90 14 {ph_top + ph_h / 2:.0f})" '
        'text-anchor="middle">Phase (deg)</text>'
    )

    # ---- shared log frequency axis --------------------------------------
    axis_y = ph_top + ph_h
    parts.append(
        f'<line x1="{left}" y1="{axis_y}" x2="{left + plot_w}" y2="{axis_y}" '
        f'stroke="{AXIS}" stroke-width="1.4"/>'
    )
    decade = math.floor(log_min)
    while decade <= math.ceil(log_max):
        f = 10 ** decade
        if freq[0] <= f <= freq[-1]:
            x = x_of(f)
            parts.append(
                f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 5}" '
                f'stroke="{AXIS}" stroke-width="1.2"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{axis_y + 19}" text-anchor="middle" '
                f'font-size="11" fill="{MUTED}">{_decade_label(f)}</text>'
            )
        decade += 1

    parts.append(
        f'<text x="{left + plot_w / 2:.0f}" y="{axis_y + 40}" '
        f'text-anchor="middle" font-size="11.5" fill="{MUTED}">'
        'Frequency (Hz, log scale)</text>'
    )

    # ---- corner markers --------------------------------------------------
    for key, label in (("f_low", "fL"), ("f_high", "fH")):
        value = data.get(key)
        limited = data.get(f"{key}_limited")
        if value and not limited and freq[0] < value < freq[-1]:
            x = x_of(value)
            parts.append(
                f'<line x1="{x:.1f}" y1="{mag_top}" x2="{x:.1f}" y2="{axis_y}" '
                f'stroke="{NAVY}" stroke-width="1" stroke-dasharray="4 4" '
                f'opacity="0.55"/>'
            )
            # Keep the corner label inside the plot box.
            if x > left + plot_w - 96:
                parts.append(
                    f'<text x="{x - 6:.1f}" y="{mag_top + 12}" text-anchor="end" '
                    f'font-size="10.5" fill="{NAVY}">{label} {_format_freq(value)}</text>'
                )
            else:
                parts.append(
                    f'<text x="{x + 4:.1f}" y="{mag_top + 12}" font-size="10.5" '
                    f'fill="{NAVY}">{label} {_format_freq(value)}</text>'
                )

    parts.append(_legend(
        [
            ("Gain |Vout/Vin| (dB)", TEAL, ""),
            ("Phase (deg)", ORANGE, ""),
        ],
        left, mag_top - 30,
    ))
    parts.append("</svg>")
    return "".join(parts)


def _format_freq(value: float) -> str:
    if value >= 1e6:
        return f"{value / 1e6:.3g} MHz"
    if value >= 1e3:
        return f"{value / 1e3:.3g} kHz"
    return f"{value:.3g} Hz"


def _decade_label(value: float) -> str:
    if value >= 1e9:
        return f"{value / 1e9:.3g}G"
    if value >= 1e6:
        return f"{value / 1e6:.3g}M"
    if value >= 1e3:
        return f"{value / 1e3:.3g}k"
    return f"{value:.3g}"


def waveform_svg(data: dict, max_points: int = 1200) -> str:
    """Return the Vin/Vout time-domain figure from transient data."""
    time_s = data["time_s"]
    vin = data["vin"]
    vout = data["vout"]
    if not time_s:
        return ""

    step = max(1, len(time_s) // max_points)
    t_ms = [t * 1000.0 for t in time_s[::step]]
    vin_s = vin[::step]
    vout_s = vout[::step]

    left, right, top = 62, 26, 46
    plot_w = WIDTH - left - right
    plot_h = 190
    height = top + plot_h + 62

    t_lo, t_hi = 0.0, t_ms[-1] or 1.0
    amp = max(max(abs(v) for v in vin_s), max(abs(v) for v in vout_s))
    amp = amp or 1.0
    y_ticks = _nice_ticks(-amp, amp, 6)
    y_lo, y_hi = y_ticks[0], y_ticks[-1]
    y_labels = _tick_labels(y_ticks, 1, 2)

    def x_of(t: float) -> float:
        return left + (t - t_lo) / (t_hi - t_lo) * plot_w

    def y_of(v: float) -> float:
        return top + plot_h - (v - y_lo) / (y_hi - y_lo) * plot_h

    parts = _svg_open(height, "Transient waveform: input and output voltage")
    parts.append(
        f'<rect x="0" y="0" width="{WIDTH}" height="{height}" fill="#ffffff"/>'
    )

    for tick, label in zip(y_ticks, y_labels):
        y = y_of(tick)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{MUTED}">{label}</text>'
        )

    if y_lo < 0 < y_hi:
        y = y_of(0)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{AXIS}" stroke-width="1.2"/>'
        )

    t_ticks = _nice_ticks(t_lo, t_hi, 6)
    t_labels = _tick_labels(t_ticks, 1, 2)
    for tick, label in zip(t_ticks, t_labels):
        x = x_of(tick)
        parts.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{top + plot_h + 20}" text-anchor="middle" '
            f'font-size="11" fill="{MUTED}">{label}</text>'
        )

    vin_points = [(x_of(t), y_of(v)) for t, v in zip(t_ms, vin_s)]
    vout_points = [(x_of(t), y_of(v)) for t, v in zip(t_ms, vout_s)]
    parts.append(_polyline(vout_points, ORANGE, 1.9))
    parts.append(_polyline(vin_points, TEAL, 2.1))

    axis_y = top + plot_h
    parts.append(
        f'<line x1="{left}" y1="{axis_y}" x2="{left + plot_w}" y2="{axis_y}" '
        f'stroke="{AXIS}" stroke-width="1.4"/>'
    )
    parts.append(
        f'<text x="{left + plot_w / 2:.0f}" y="{axis_y + 42}" '
        f'text-anchor="middle" font-size="11.5" fill="{MUTED}">Time (ms)</text>'
    )
    parts.append(
        f'<text x="14" y="{top + plot_h / 2:.0f}" font-size="11" fill="{MUTED}" '
        f'transform="rotate(-90 14 {top + plot_h / 2:.0f})" '
        'text-anchor="middle">Voltage (V)</text>'
    )
    parts.append(_legend(
        [("Vin @ src", TEAL, ""), ("Vout @ out", ORANGE, "")],
        left, top - 18,
    ))
    parts.append("</svg>")
    return "".join(parts)
