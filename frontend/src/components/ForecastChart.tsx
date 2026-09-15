import type { Candle, CandleSeries, ForecastResponse } from '../types'
import {
  fmtBarDateTime,
  fmtBarTime,
  fmtFractionPct,
  fmtPrice,
  intervalLabel,
  isIntraday,
  signClass,
} from '../format'

const WIDTH = 1000
const HEIGHT = 420
const HEIGHT_COMPACT = 300
const PAD = { top: 18, right: 72, bottom: 30, left: 10 }
/** Aim for roughly this many axis labels so a phone does not render an unreadable thicket. */
const TARGET_TICKS = 6

const UP = '#26a69a'
const DOWN = '#ef5350'
const FORECAST_UP = '#7dd3fc'
const FORECAST_DOWN = '#c084fc'

interface Props {
  series: CandleSeries | null
  forecast: ForecastResponse | null
  /** Bar size label of the selected interval, e.g. "5m" — shown in the chart legend. */
  interval?: string | null
  /** Compact mode for phone-sized cards: shorter chart, fewer labels. */
  compact?: boolean
}

/**
 * Candlesticks plus the Kronos forecast, drawn by hand.
 *
 * No chart library: candlesticks are rectangles and wicks are lines, and hand-rolling them keeps
 * the dependency graph at React alone (see the Decision log in `doc/plan.md`). The forecast is
 * drawn as faded candles plus a bright close-path polyline — faded because it is a sample, not a
 * price, and the line because that is what a reader actually compares against the history.
 *
 * The time axis is interval-aware: intraday bars are labelled with clock times (a date would be
 * meaningless when the whole visible window is one trading day), daily and weekly bars with
 * dates. Tick labels are spaced to a target count rather than drawn on every bar so the axis
 * stays readable on a phone. A `<time>` element in `chart-meta` states the bar size explicitly,
 * so "1m" and "1d" charts can never be confused.
 */
export function ForecastChart({ series, forecast, interval, compact = false }: Props) {
  const history: Candle[] = series?.candles ?? []
  const points = forecast?.points ?? []
  const height = compact ? HEIGHT_COMPACT : HEIGHT
  const intraday = isIntraday(interval ?? series?.interval)

  if (history.length === 0 && points.length === 0) {
    return (
      <div className="empty">
        No market data yet. Press <strong>Run cycle</strong> to fetch prices and forecast.
      </div>
    )
  }

  const bars: { candle: Candle; isForecast: boolean }[] = [
    ...history.map((candle) => ({ candle, isForecast: false })),
    ...points.map((candle) => ({ candle, isForecast: true })),
  ]

  const lows = bars.map((b) => b.candle.low)
  const highs = bars.map((b) => b.candle.high)
  const rawMin = Math.min(...lows)
  const rawMax = Math.max(...highs)
  const padding = (rawMax - rawMin) * 0.06 || Math.abs(rawMax) * 0.01 || 1
  const yMin = rawMin - padding
  const yMax = rawMax + padding

  const plotWidth = WIDTH - PAD.left - PAD.right
  const plotHeight = height - PAD.top - PAD.bottom
  const slot = plotWidth / Math.max(bars.length, 1)
  const bodyWidth = Math.max(slot * 0.62, 1)

  const x = (index: number) => PAD.left + index * slot + slot / 2
  const y = (price: number) => PAD.top + ((yMax - price) / (yMax - yMin)) * plotHeight

  const gridLines = Array.from({ length: 5 }, (_, i) => yMin + ((yMax - yMin) * i) / 4)

  const boundaryX = history.length > 0 ? PAD.left + history.length * slot : null
  const forecastCloses = bars
    .map((bar, index) => ({ bar, index }))
    .filter(({ bar }) => bar.isForecast)
    .map(({ bar, index }) => `${x(index)},${y(bar.candle.close)}`)
    .join(' ')

  const lastActual =
    history.length > 0 ? history[history.length - 1]!.close : (points[0]?.close ?? 0)
  const finalForecast = points.length > 0 ? points[points.length - 1]!.close : null
  const expectedReturn =
    finalForecast != null && lastActual ? finalForecast / lastActual - 1 : 0

  // Time-axis ticks: evenly spaced indices with a time label, thinned to ~TARGET_TICKS so the
  // axis stays readable when there are hundreds of bars.
  const tickStep = Math.max(1, Math.ceil(bars.length / TARGET_TICKS))
  const ticks: { index: number; label: string }[] = []
  for (let index = 0; index < bars.length; index += tickStep) {
    ticks.push({
      index,
      label: fmtBarTime(bars[index]!.candle.timestamp, intraday),
    })
  }
  // Always show the newest bar's time — the reader's first question is "as of when?".
  const lastIndex = bars.length - 1
  const lastLabel = fmtBarTime(bars[lastIndex]!.candle.timestamp, intraday)
  const lastTick = ticks[ticks.length - 1]
  if (!lastTick || lastTick.index !== lastIndex) {
    if (lastTick && lastIndex - lastTick.index < tickStep / 2) {
      ticks[ticks.length - 1] = { index: lastIndex, label: lastLabel }
    } else {
      ticks.push({ index: lastIndex, label: lastLabel })
    }
  }

  const barSize = intervalLabel(interval ?? series?.interval)

  return (
    <div className={`chart-wrap${compact ? ' chart-wrap-compact' : ''}`}>
      <svg
        className="chart"
        viewBox={`0 0 ${WIDTH} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Price history and ${barSize || ''} forecast for ${series?.symbol ?? 'symbol'}`.trim()}
      >
        {gridLines.map((price) => (
          <g key={price}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(price)}
              y2={y(price)}
              stroke="#2a2f3a"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            <text x={WIDTH - PAD.right + 6} y={y(price) + 4} className="axis-label">
              {fmtPrice(price)}
            </text>
          </g>
        ))}

        {boundaryX != null && (
          <rect
            x={boundaryX}
            y={PAD.top}
            width={Math.max(WIDTH - PAD.right - boundaryX, 0)}
            height={plotHeight}
            fill="#7dd3fc"
            opacity={0.05}
          />
        )}

        {bars.map(({ candle, isForecast }, index) => {
          const up = candle.close >= candle.open
          const colour = isForecast
            ? up
              ? FORECAST_UP
              : FORECAST_DOWN
            : up
              ? UP
              : DOWN
          const bodyTop = y(Math.max(candle.open, candle.close))
          const bodyBottom = y(Math.min(candle.open, candle.close))
          return (
            <g key={`${isForecast ? 'f' : 'h'}-${candle.timestamp}-${index}`} opacity={isForecast ? 0.55 : 1}>
              <line
                x1={x(index)}
                x2={x(index)}
                y1={y(candle.high)}
                y2={y(candle.low)}
                stroke={colour}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
              <rect
                x={x(index) - bodyWidth / 2}
                y={bodyTop}
                width={bodyWidth}
                height={Math.max(bodyBottom - bodyTop, 1)}
                fill={colour}
              />
            </g>
          )
        })}

        {forecastCloses && (
          <polyline
            points={forecastCloses}
            fill="none"
            stroke={FORECAST_UP}
            strokeWidth={1.6}
            vectorEffect="non-scaling-stroke"
          />
        )}

        {boundaryX != null && (
          <line
            x1={boundaryX}
            x2={boundaryX}
            y1={PAD.top}
            y2={PAD.top + plotHeight}
            stroke="#7dd3fc"
            strokeWidth={1}
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
          />
        )}

        {ticks.map(({ index, label }) => (
          <text
            key={`t-${index}`}
            x={x(index)}
            y={height - 8}
            className={`axis-label${index === lastIndex ? ' anchor-end' : ''}`}
            textAnchor={index === 0 ? 'start' : index === lastIndex ? 'end' : 'middle'}
          >
            {label}
          </text>
        ))}
      </svg>

      <div className="chart-meta">
        <span className="legend">
          <i className="swatch" style={{ background: UP }} /> history
        </span>
        <span className="legend">
          <i className="swatch" style={{ background: FORECAST_UP }} /> Kronos forecast
          {forecast ? ` (${forecast.horizon} × ${barSize || 'bars'})` : ''}
        </span>
        {barSize && <span className="legend mono">{barSize} bars</span>}
        {finalForecast != null && (
          <span className={`legend mono ${signClass(expectedReturn)}`}>
            target {fmtPrice(finalForecast)} · {fmtFractionPct(expectedReturn)}
          </span>
        )}
        {history.length > 0 && (
          <span className="legend muted tiny" title="Last actual bar of this series">
            <time dateTime={history[history.length - 1]!.timestamp}>
              as of {fmtBarDateTime(history[history.length - 1]!.timestamp)}
            </time>
          </span>
        )}
      </div>
    </div>
  )
}
