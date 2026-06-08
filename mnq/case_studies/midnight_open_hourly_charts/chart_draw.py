"""Shared candlestick drawing for MNQ session review charts."""
from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


def draw_session_candles(ax, bars: pd.DataFrame, *, bar_minutes: int = 60) -> None:
    if bars.empty:
        return
    xs = mdates.date2num(list(bars.index.to_pydatetime()))
    width = (bar_minutes / (24.0 * 60.0)) * 0.72 if len(xs) > 1 else 0.04
    for x, (_, row) in zip(xs, bars.iterrows()):
        o, h_, l, c = map(float, (row['open'], row['high'], row['low'], row['close']))
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h_, color=col, linewidth=0.95, zorder=3, alpha=0.92)
        body_lo = min(o, c)
        body_hi = max(abs(c - o), 0.08)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                body_hi,
                facecolor=col,
                edgecolor=col,
                alpha=0.92,
                zorder=4,
            )
        )


def draw_1h_candles(ax, bars1h: pd.DataFrame) -> None:
    draw_session_candles(ax, bars1h, bar_minutes=60)


def style_session_ax(ax, bars: pd.DataFrame, *, ny, bar_minutes: int = 60) -> None:
    ax.set_xlabel('NY time', color='#B0BEC5')
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.22, color='#546E7A')
    for spine in ax.spines.values():
        spine.set_color('#37474F')
    if not bars.empty:
        pad = bar_minutes / (24.0 * 60.0)
        ax.set_xlim(
            mdates.date2num(bars.index.min()) - pad,
            mdates.date2num(bars.index.max()) + pad * 2,
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=ny))
        if bar_minutes <= 15:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
            ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=30))
        else:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))


def new_session_figure(figsize: tuple[float, float]):
    fig, ax = plt.subplots(figsize=figsize, facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')
    return fig, ax
