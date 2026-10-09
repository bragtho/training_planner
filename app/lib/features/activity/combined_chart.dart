import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../core/charts.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'highlight.dart';
import 'zoom.dart';

/// Eine Messreihe der Fahrt fuer die kombinierte Ansicht.
class ChartSeries {
  const ChartSeries({required this.key, required this.title, required this.unit, required this.color, required this.icon, required this.spots});
  final String key;
  final String title;
  final String unit;
  final Color color;
  final IconData icon;
  final List<FlSpot> spots; // x = Minuten, y = Messwert

  double get min => spots.map((s) => s.y).reduce((a, b) => a < b ? a : b);
  double get max => spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);

  /// Leistung und Trittfrequenz beginnen bei 0 (Rollen), Puls und Hoehe nutzen ihren echten Bereich.
  double get floor => (key == 'watts' || key == 'cadence') ? 0 : min;

  /// Messwert auf 0..1 bezogen auf den Bereich dieser Reihe, damit unterschiedliche Einheiten in einem Diagramm passen.
  double norm(double y) => max <= floor ? 0.5 : ((y - floor) / (max - floor)).clamp(0.0, 1.0).toDouble();
}

/// Alle gewaehlten Messreihen in einem Diagramm. Jede Reihe ist auf ihren eigenen Bereich skaliert; die Werte stehen in der Anzeige.
class CombinedChart extends StatefulWidget {
  const CombinedChart({super.key, required this.series, this.highlight, this.view, this.onGesture});
  final List<ChartSeries> series;
  final Highlight? highlight;
  final ViewRange? view;
  final void Function(double factor, double anchor, double pan)? onGesture;

  @override
  State<CombinedChart> createState() => _CombinedChartState();
}

class _CombinedChartState extends State<CombinedChart> {
  late Set<String> _shown = {for (final s in widget.series) s.key};
  double? _touchX; // Zeit (Minuten) der zuletzt beruehrten Stelle
  Map<String, double> _touchValues = {};

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final cs = ChartStyle(context);
    final active = [for (final s in widget.series) if (_shown.contains(s.key)) s];
    // Zeichenreihenfolge von hinten nach vorn: Hoehe (graue Flaeche), Trittfrequenz, Herzfrequenz, Leistung ganz vorn
    const back = ['altitude', 'cadence', 'heartrate', 'watts'];
    int rank(ChartSeries s) => back.contains(s.key) ? back.indexOf(s.key) : back.length;
    final drawn = [...active]..sort((a, b) => rank(a).compareTo(rank(b)));
    final h = widget.highlight;
    final v = widget.view;

    void toggle(String key) => setState(() {
          _touchX = null;
          _touchValues = {};
          if (_shown.contains(key)) {
            if (_shown.length > 1) _shown = {..._shown}..remove(key); // mindestens eine Reihe bleibt sichtbar
          } else {
            _shown = {..._shown, key};
          }
        });

    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionHeader(
          title: 'Alle Daten in einem Diagramm',
          subtitle: 'Jede Reihe ist auf ihren eigenen Bereich skaliert. Die echten Werte zeigt die Anzeige beim Berühren.',
        ),
        ChipRow(children: [
          for (final s in widget.series)
            FilterChip(
              avatar: Icon(s.icon, size: 16, color: _shown.contains(s.key) ? s.color : t.colorScheme.onSurfaceVariant),
              label: Text(s.title),
              selected: _shown.contains(s.key),
              showCheckmark: false,
              selectedColor: s.color.withValues(alpha: 0.16),
              side: BorderSide(color: _shown.contains(s.key) ? s.color : t.colorScheme.outlineVariant),
              onSelected: (_) => toggle(s.key),
            ),
        ]),
        const SizedBox(height: Gap.md),
        _Readout(active: active, x: _touchX, values: _touchValues),
        const SizedBox(height: Gap.sm),
        ZoomListener(
          leftInset: 8,
          onGesture: widget.onGesture,
          child: SizedBox(
            height: 260,
            child: LineChart(LineChartData(
              minY: -0.05,
              maxY: 1.05,
              minX: v?.min,
              maxX: v?.max,
              clipData: const FlClipData.all(),
              lineBarsData: [
                for (final s in drawn)
                  LineChartBarData(
                    spots: [for (final p in s.spots) FlSpot(p.x, s.norm(p.y))],
                    color: s.color,
                    barWidth: 1.6,
                    dotData: const FlDotData(show: false),
                    belowBarData: s.key == 'altitude'
                        ? BarAreaData(show: true, color: s.color.withValues(alpha: 0.22))
                        : BarAreaData(show: false),
                  ),
              ],
              gridData: cs.grid(interval: 0.25),
              borderData: FlBorderData(show: false),
              rangeAnnotations: h == null
                  ? null
                  : RangeAnnotations(verticalRangeAnnotations: [
                      VerticalRangeAnnotation(x1: h.startMin, x2: h.endMin, color: AppColors.power.withValues(alpha: 0.2)),
                    ]),
              titlesData: FlTitlesData(
                topTitles: const AxisTitles(),
                rightTitles: const AxisTitles(),
                leftTitles: const AxisTitles(sideTitles: SideTitles(reservedSize: 8)),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 26,
                    interval: axisInterval(v?.span ?? (active.first.spots.last.x - active.first.spots.first.x)),
                    getTitlesWidget: (x, meta) =>
                        (x == meta.min || x == meta.max) ? const SizedBox.shrink() : cs.axisLabel(axisTimeLabel(x, meta.appliedInterval)),
                  ),
                ),
              ),
              lineTouchData: LineTouchData(
                touchSpotThreshold: 24,
                distanceCalculator: (touch, spot) => (touch.dx - spot.dx).abs(), // nur waagerechter Abstand, alle Reihen an dieser Stelle
                touchCallback: (event, response) {
                  final hits = response?.lineBarSpots;
                  if (hits == null || hits.isEmpty) return;
                  final values = {for (final sp in hits) drawn[sp.barIndex].key: drawn[sp.barIndex].spots[sp.spotIndex].y};
                  final x = hits.first.x;
                  if (x != _touchX) {
                    setState(() {
                      _touchX = x;
                      _touchValues = values;
                    });
                  }
                },
                getTouchedSpotIndicator: (bar, idx) => [
                  for (final _ in idx)
                    TouchedSpotIndicatorData(
                      FlLine(color: cs.scheme.outline, strokeWidth: 1, dashArray: const [3, 3]),
                      const FlDotData(show: false),
                    ),
                ],
                // Die Werte stehen ueber dem Diagramm, damit nichts im Graphen verdeckt wird
                touchTooltipData: LineTouchTooltipData(getTooltipItems: (spots) => List.filled(spots.length, null)),
              ),
            )),
          ),
        ),
      ]),
    );
  }
}

/// Werte an der beruehrten Stelle, ausserhalb des Diagramms.
class _Readout extends StatelessWidget {
  const _Readout({required this.active, required this.x, required this.values});
  final List<ChartSeries> active;
  final double? x;
  final Map<String, double> values;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final shown = [for (final s in active) if (values.containsKey(s.key)) s];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: Gap.md, vertical: Gap.sm),
      decoration: BoxDecoration(color: t.colorScheme.surfaceContainer.withValues(alpha: 0.6), borderRadius: BorderRadius.circular(Radii.md)),
      child: x == null || shown.isEmpty
          ? Text('Berühre oder fahre mit der Maus über das Diagramm, um die Werte zu sehen.', style: t.textTheme.bodySmall?.copyWith(color: muted))
          : Wrap(spacing: Gap.lg, runSpacing: Gap.xs, crossAxisAlignment: WrapCrossAlignment.center, children: [
              for (final s in shown)
                Text.rich(TextSpan(children: [
                  TextSpan(text: '${s.title} ', style: t.textTheme.bodySmall?.copyWith(color: muted)),
                  TextSpan(text: '${values[s.key]!.round()} ${s.unit}', style: t.textTheme.titleSmall?.copyWith(color: s.color)),
                ])),
            ]),
    );
  }
}
