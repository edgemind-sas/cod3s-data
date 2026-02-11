# COD3S Observatory - Metrics Dashboard

**Version:** 1.0
**Date:** 2026-02-11
**Status:** Functional Specification

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-06-MESSAGE-INSPECTOR](OBS-06-MESSAGE-INSPECTOR.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-08-CONFIGURATION →](OBS-08-CONFIGURATION.md) |

---

## Table of Contents

- [Purpose](#purpose)
- [Dashboard Layout](#dashboard-layout)
- [Global Stats Bar](#global-stats-bar)
- [Built-in Metric Cards](#built-in-metric-cards)
- [Chart Types](#chart-types)
- [Data Sources](#data-sources)
- [Update Frequency and History](#update-frequency-and-history)
- [Interaction Patterns](#interaction-patterns)
- [Performance Considerations](#performance-considerations)
- [Summary](#summary)

---

## Purpose

The **Metrics Dashboard** provides real-time visual monitoring of pipeline health, performance, and behavior. It aggregates and visualizes metrics published by the framework on `_metrics.*` channels, offering a centralized view of system state without requiring external monitoring tools.

**Key Goals:**
- Monitor pipeline throughput, latency, and error rates in real time
- Track buffer utilization and identify backpressure
- Observe per-component metrics (sources, destinations)
- Detect performance degradation or anomalies quickly

---

## Dashboard Layout

### Layout Structure

The dashboard uses a **two-tier layout**:

```
┌─────────────────────────────────────────────────────────────┐
│  GLOBAL STATS BAR                                            │
│  Throughput: 1,234 msg/s  |  Errors: 3  |  Uptime: 2h 45m   │
│  Connected Sources: 5     |  Active Channels: 42            │
└─────────────────────────────────────────────────────────────┘
┌──────────────────┬──────────────────┬──────────────────────┐
│                  │                  │                      │
│  Broker          │  Broker Latency  │  Error Rate         │
│  Throughput      │  (line chart)    │  (line chart)       │
│  (line chart)    │                  │                      │
│                  │                  │                      │
├──────────────────┼──────────────────┼──────────────────────┤
│                  │                  │                      │
│  Source Rates    │  Destination     │  Buffer Utilization │
│  (bar chart)     │  Rates           │  (gauges)           │
│                  │  (bar chart)     │                      │
│                  │                  │                      │
├──────────────────┴──────────────────┼──────────────────────┤
│                                     │                      │
│  Active Channels Count              │  Subscription Count │
│  (number card)                      │  (number card)      │
│                                     │                      │
└─────────────────────────────────────┴──────────────────────┘
```

### Responsive Behavior

- **Desktop (>1200px):** 3-column grid
- **Tablet (768-1200px):** 2-column grid
- **Mobile (<768px):** 1-column stack

---

## Global Stats Bar

The **global stats bar** appears at the top of the dashboard, showing high-level system metrics at a glance.

### Displayed Metrics

| Metric | Description | Source Channel |
|--------|-------------|----------------|
| **Total Throughput** | Current aggregate messages per second (all sources) | `_metrics.broker.throughput` |
| **Error Count** | Total errors in the last 5 minutes | `_metrics.source.*.errors`, `_metrics.destination.*.errors` |
| **Uptime** | Framework uptime since start (HH:MM:SS or days if >24h) | `_metrics.system.uptime` |
| **Connected Sources** | Number of active sources | `_metrics.source.*.status` |
| **Active Channels** | Number of channels with at least one active subscription | `_metrics.broker.channels` |

### Visual Design

- **Background:** Light gray (#f4f4f4) or dark theme equivalent
- **Text:** Large, bold numbers with smaller label text
- **Colors:**
  - Throughput: Blue
  - Errors: Red (if >0), Gray (if 0)
  - Uptime: Green
  - Connected Sources: Purple
  - Active Channels: Orange
- **Separators:** Vertical divider lines between metrics

---

## Built-in Metric Cards

### 1. Broker Throughput

**Type:** Line chart
**Y-axis:** Messages per second (msg/s)
**X-axis:** Time (last 5 minutes)
**Update:** Every 1 second

**Data source:** `_metrics.broker.throughput`

**Behavior:**
- Single line showing aggregate throughput over time
- Rolling 5-minute window
- Scale adjusts automatically to data range
- Hover tooltip shows exact value and timestamp

---

### 2. Broker Latency

**Type:** Multi-line chart
**Y-axis:** Latency (milliseconds)
**X-axis:** Time (last 5 minutes)
**Update:** Every 1 second

**Data source:** `_metrics.broker.latency`

**Lines displayed:**
- p50 (median) — Blue
- p95 — Yellow
- p99 — Orange

**Behavior:**
- Three lines on same chart for comparison
- Legend shows current values for each percentile
- Hover tooltip shows all three values at a given timestamp

---

### 3. Source Rates

**Type:** Horizontal bar chart
**Y-axis:** Source names
**X-axis:** Messages per second
**Update:** Every 1 second

**Data source:** `_metrics.source.<name>.messages`

**Behavior:**
- One bar per active source
- Bars sorted by rate (descending)
- Shows only sources with recent activity (last 10 seconds)
- Bar color indicates source type (CSV=green, MQTT=blue, Random=purple, etc.)

---

### 4. Destination Rates

**Type:** Horizontal bar chart
**Y-axis:** Destination names
**X-axis:** Messages per second
**Update:** Every 1 second

**Data source:** `_metrics.destination.<name>.messages`

**Behavior:**
- One bar per active destination
- Bars sorted by rate (descending)
- Shows only destinations with recent activity (last 10 seconds)
- Bar color indicates destination type (Console=cyan, File=green, Database=blue, etc.)

---

### 5. Buffer Utilization

**Type:** Gauge cards (multiple)
**Display:** Percentage fill (0-100%)
**Update:** Every 1 second

**Data source:** `_metrics.destination.<name>.buffer_utilization`

**Behavior:**
- One gauge per buffered destination
- Color coding:
  - 0-70%: Green (healthy)
  - 70-90%: Yellow (warning)
  - 90-100%: Red (critical)
- Shows destination name and current percentage
- Tooltip shows buffer size (used/total)

---

### 6. Error Rate

**Type:** Line chart
**Y-axis:** Errors per minute
**X-axis:** Time (last 5 minutes)
**Update:** Every 1 second

**Data source:** `_metrics.source.*.errors`, `_metrics.destination.*.errors`

**Behavior:**
- Single line showing aggregate error rate
- Red line color
- Zero-baseline (errors should be rare)
- Hover tooltip shows error type and last error message if available

---

### 7. Active Channels Count

**Type:** Number card
**Display:** Large number with trend indicator
**Update:** Every 1 second

**Data source:** `_metrics.broker.channels`

**Behavior:**
- Shows current count of active channels
- Trend arrow (↑/↓/→) comparing to 1 minute ago
- Subtitle: "channels with subscriptions"

---

### 8. Subscription Count

**Type:** Number card
**Display:** Large number with trend indicator
**Update:** Every 1 second

**Data source:** `_metrics.broker.subscriptions`

**Behavior:**
- Shows current total subscription count
- Trend arrow (↑/↓/→) comparing to 1 minute ago
- Subtitle: "total subscriptions"

---

## Chart Types

### Line Chart

**Use cases:** Time-series data (throughput, latency, error rate)

**Features:**
- Smooth line interpolation
- Grid lines for readability
- Auto-scaling Y-axis
- Hover crosshair with tooltip
- Zoom and pan (optional, disabled by default)

**Library:** Chart.js or D3.js

---

### Bar Chart

**Use cases:** Per-component metrics (source rates, destination rates)

**Features:**
- Horizontal orientation (better for variable-length names)
- Sorted by value (descending)
- Color-coded by component type
- Hover tooltip with exact value
- Auto-hide bars with zero values

**Library:** Chart.js or D3.js

---

### Gauge

**Use cases:** Percentage-based metrics (buffer utilization)

**Features:**
- Semi-circular or circular display
- Color zones (green/yellow/red)
- Large percentage text in center
- Animated transitions when value changes
- Compact layout (multiple gauges in one card)

**Library:** Custom SVG or Chart.js gauge plugin

---

### Sparkline

**Use cases:** Compact trend indicators (not in V1, reserved for future)

**Features:**
- Miniature line chart without axes
- Inline display (within cards)
- Shows trend at a glance

---

### Number Card

**Use cases:** Single-value metrics (channel count, subscription count)

**Features:**
- Large, bold number
- Trend indicator (arrow + delta)
- Optional icon
- Subtitle or description text

---

## Data Sources

### Metric Channel Patterns

The dashboard subscribes to the following `_metrics.*` channels:

| Metric Card | Channel Pattern | Message Structure |
|------------|----------------|-------------------|
| Broker Throughput | `_metrics.broker.throughput` | `{key, timestamp, value: number, tags: {window}}` |
| Broker Latency | `_metrics.broker.latency` | `{key, timestamp, value: {p50, p95, p99}, tags}` |
| Source Rates | `_metrics.source.*.messages` | `{key, timestamp, value: number, tags: {source_type}}` |
| Destination Rates | `_metrics.destination.*.messages` | `{key, timestamp, value: number, tags: {dest_type}}` |
| Buffer Utilization | `_metrics.destination.*.buffer` | `{key, timestamp, value: {used, total, percent}, tags}` |
| Error Rate | `_metrics.source.*.errors`, `_metrics.destination.*.errors` | `{key, timestamp, value: number, tags: {error_type}}` |
| Active Channels | `_metrics.broker.channels` | `{key, timestamp, value: number, tags: {state: "active"}}` |
| Subscription Count | `_metrics.broker.subscriptions` | `{key, timestamp, value: number, tags}` |

### Metric Aggregation

For metrics with multiple sources (e.g., errors from multiple destinations):
- **Sum:** Total error count = sum of all error counts
- **Average:** Not used in V1 (all metrics are sums or individual values)
- **Latest:** For status metrics (channel count, subscription count)

### Missing Data Handling

If a metric channel has not received data for more than 10 seconds:
- **Line charts:** Gap in the line (do not interpolate)
- **Bar charts:** Hide the bar or show zero
- **Gauges:** Show last known value with a "stale" indicator (grayed out)
- **Number cards:** Show last known value with a warning icon

---

## Update Frequency and History

### Update Frequency

**All charts update every 1 second** to provide near-real-time visibility.

**Implementation:**
- WebSocket events from bridge carry metric messages as they are published
- Frontend buffers incoming metrics and updates charts on a 1-second interval
- No explicit polling — event-driven updates

---

### History Window

**All time-series charts display a 5-minute rolling window:**
- X-axis spans exactly 5 minutes (300 seconds)
- Oldest data points are evicted as new data arrives
- Time axis scrolls automatically (right-to-left)

**Why 5 minutes?**
- Long enough to observe trends and anomalies
- Short enough to avoid overwhelming browser memory
- Standard observability practice (Grafana default is 5-15 minutes)

**Customization (V2):**
- User-selectable window (1 min, 5 min, 15 min, 1 hour)
- Per-card independent window settings

---

## Interaction Patterns

### Hover Tooltips

**All charts support hover tooltips:**
- Line charts: Show timestamp, metric name, and value
- Bar charts: Show component name, type, and rate
- Gauges: Show buffer size (used/total) and percentage

---

### Click Actions

**V1 (basic):**
- Click on a source bar → Jump to pipeline topology, highlight source
- Click on a destination bar → Jump to pipeline topology, highlight destination
- Click on error count → Open error log panel (if available)

**V2 (advanced):**
- Click on a metric line → Open detailed metric view with drill-down
- Right-click → Export chart as PNG or CSV

---

### Auto-Refresh

The dashboard updates automatically without user intervention. No manual refresh button is needed.

---

### Pause/Resume

**Debug mode integration:**
- When the pipeline is paused (via debug controls), the dashboard continues to show the last known values
- A "PAUSED" indicator appears in the global stats bar
- Charts freeze and show a grayed-out overlay
- When resumed, charts immediately update with new data

---

## Performance Considerations

### Browser Memory

**5-minute window with 1-second resolution = 300 data points per chart**

Estimated memory per chart:
- Line chart: 300 data points × 3 series × 8 bytes = ~7 KB
- Bar chart: ~10 components × 8 bytes = ~80 bytes
- Total dashboard: ~50 KB (negligible)

**No memory concerns for V1 with 5-minute windows.**

---

### Rendering Performance

**Chart.js performance:**
- Up to 10,000 data points: Smooth (60 FPS)
- V1 target: 300 data points × 8 charts = 2,400 points
- Well within performance limits

**Optimization:**
- Use `requestAnimationFrame` for smooth updates
- Batch chart updates (update all charts at once, not individually)
- Debounce hover tooltips

---

### High-Throughput Pipelines

For pipelines with very high throughput (>10,000 msg/s), the framework's metrics system uses **sampling** (see [OBS-08-CONFIGURATION](OBS-08-CONFIGURATION.md)):
- Default: No sampling (every message counted)
- High-throughput mode: Sample 1 in N messages, extrapolate total
- Dashboard displays extrapolated values transparently

---

## Summary

The **Metrics Dashboard** provides real-time visual monitoring of the COD3S Data pipeline:

1. **Global Stats Bar** — High-level overview (throughput, errors, uptime, connections)
2. **8 Built-in Cards** — Line charts, bar charts, gauges, and number cards
3. **Data Sources** — Subscribes to `_metrics.*` channels published by the framework
4. **Update Frequency** — 1-second refresh with 5-minute rolling window
5. **Interaction** — Hover tooltips, click navigation, auto-refresh

The dashboard leverages the framework's "metrics as messages" design, requiring no special metric collection infrastructure.

**Next:** [OBS-08-CONFIGURATION](OBS-08-CONFIGURATION.md) describes how to configure the Observatory module.

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-06-MESSAGE-INSPECTOR](OBS-06-MESSAGE-INSPECTOR.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-08-CONFIGURATION →](OBS-08-CONFIGURATION.md) |

---

*This is a functional specification document for the COD3S Observatory module. Technical implementation details are in [OBS-TECH-05-COMPONENT-LIBRARY](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-05-COMPONENT-LIBRARY.md).*
