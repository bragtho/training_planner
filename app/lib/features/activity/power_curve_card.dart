import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api.dart';
import '../../core/charts.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'highlight.dart';

const _axisDurations = {5, 60, 300, 1200, 3600, 10800};
const _chipDurations = [5, 60, 300, 1200, 3600];

/// Fahrzeit als Uhr: 1:05:30 oder 12:40.
String formatClock(int s) {
  final h = s ~/ 3600;
  final m = ((s % 3600) ~/ 60).toString().padLeft(2, '0');
  final sec = (s % 60).toString().padLeft(2, '0');
  return h > 0 ? '$h:$m:$sec' : '${s ~/ 60}:$sec';
}

/// Leistungskurve der Fahrt. Ein Tipp auf eine Dauer waehlt sie aus; die Fahrt zeigt dann, wo diese Leistung gefahren wurde.
class PowerCurveCard extends ConsumerWidget {
  const PowerCurveCard({
    super.key,
    required this.id,
    required this.selected,
    required this.onSelect,
    required this.zoomed,
    required this.onZoom,
  });
  final int id;
  final Highlight? selected;
  final ValueChanged<Highlight?> onSelect;
  final bool zoomed;
  final ValueChanged<bool> onZoom;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final curve = ref.watch(powerCurveProvider(id));
    return curve.when(
      loading: () => const LoadingBlock(height: 240),
      error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(powerCurveProvider(id))),
      data: (pts) => pts.length < 2 ? const SizedBox.shrink() : _Body(points: pts, selected: selected, onSelect: onSelect, zoomed: zoomed, onZoom: onZoom),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.points, required this.selected, required this.onSelect, required this.zoomed, required this.onZoom});
  final List<Json> points;
  final Highlight? selected;
  final ValueChanged<Highlight?> onSelect;
  final bool zoomed;
  final ValueChanged<bool> onZoom;

  int _dur(int i) => (points[i]['duration_s'] as num).toInt();

  Highlight _at(int i) {
    final p = points[i];
    return Highlight(startS: (p['start_s'] as num).toInt(), durationS: _dur(i), watts: (p['watts'] as num).toDouble());
  }

  int? get _selectedIndex {
    final s = selected;
    if (s == null) return null;
    final i = points.indexWhere((p) => p['duration_s'] == s.durationS);
    return i < 0 ? null : i;
  }

  void _toggle(int i) => onSelect(_selectedIndex == i ? null : _at(i));

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final cs = ChartStyle(context);
    const color = AppColors.power;
    final spots = [for (var i = 0; i < points.length; i++) FlSpot(i.toDouble(), (points[i]['watts'] as num).toDouble())];
    final maxW = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    final sel = _selectedIndex;
    final chips = [
      for (var i = 0; i < points.length; i++)
        if (_chipDurations.contains(_dur(i))) i,
    ];

    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            title: 'Leistungskurve',
            subtitle: sel == null
                ? 'Tippe auf eine Dauer, um zu sehen, wo Du diese Leistung gefahren bist'
                : 'Beste ${shortDuration(selected!.durationS)}: ${selected!.watts.round()} W, '
                      'von ${formatClock(selected!.startS)} bis ${formatClock(selected!.endS)}',
          ),
          SizedBox(
            height: 200,
            child: LineChart(
              LineChartData(
                minY: 0,
                maxY: (maxW * 1.1).ceilToDouble(),
                minX: 0,
                maxX: (points.length - 1).toDouble(),
                lineBarsData: [
                  LineChartBarData(
                    spots: spots,
                    color: color,
                    barWidth: 2.2,
                    isCurved: true,
                    curveSmoothness: 0.15,
                    preventCurveOverShooting: true,
                    dotData: FlDotData(
                      show: true,
                      checkToShowDot: (s, _) => s.x.round() == sel,
                      getDotPainter: (s, p, b, i) =>
                          FlDotCirclePainter(radius: 6, color: color, strokeColor: cs.scheme.surface, strokeWidth: 2.5),
                    ),
                    belowBarData: cs.area(color, opacity: 0.22),
                  ),
                ],
                gridData: cs.grid(),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(),
                  rightTitles: const AxisTitles(),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 40,
                      getTitlesWidget: (v, meta) =>
                          (v == meta.min || v == meta.max) ? const SizedBox.shrink() : Text(v.round().toString(), style: cs.axis),
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 26,
                      interval: 1,
                      getTitlesWidget: (v, meta) {
                        final i = v.round();
                        if (v != i || i < 0 || i >= points.length || !_axisDurations.contains(_dur(i))) return const SizedBox.shrink();
                        return cs.axisLabel(shortDuration(_dur(i)));
                      },
                    ),
                  ),
                ),
                lineTouchData: LineTouchData(
                  touchSpotThreshold: 40,
                  touchCallback: (event, response) {
                    final spot = response?.lineBarSpots?.firstOrNull;
                    if (event is FlTapUpEvent && spot != null) _toggle(spot.spotIndex);
                  },
                  touchTooltipData: LineTouchTooltipData(
                    getTooltipColor: (_) => cs.tooltipColor(),
                    tooltipBorderRadius: cs.tooltipRadius,
                fitInsideHorizontally: true,
                fitInsideVertically: true,
                    getTooltipItems: (spots) => [
                      for (final s in spots)
                        LineTooltipItem(
                          '${s.y.round()} W',
                          cs.tooltipText(color),
                          children: [TextSpan(text: '\nbeste ${shortDuration(_dur(s.spotIndex))}', style: cs.tooltipTitle)],
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: Gap.md),
          Wrap(
            spacing: Gap.sm,
            runSpacing: Gap.sm,
            children: [
              for (final i in chips)
                ChoiceChip(
                  label: Text('${shortDuration(_dur(i))} · ${(points[i]['watts'] as num).round()} W'),
                  selected: sel == i,
                  onSelected: (_) => _toggle(i),
                  labelStyle: t.textTheme.labelMedium,
                ),
            ],
          ),
          if (sel != null) ...[
            const SizedBox(height: Gap.md),
            Wrap(
              spacing: Gap.sm,
              runSpacing: Gap.xs,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                FilledButton.tonalIcon(
                  onPressed: () => onZoom(!zoomed),
                  icon: Icon(zoomed ? Icons.zoom_out_map_rounded : Icons.zoom_in_rounded, size: 18),
                  label: Text(zoomed ? 'Ganze Fahrt zeigen' : 'Auf Abschnitt zoomen'),
                ),
                TextButton(onPressed: () => onSelect(null), child: const Text('Auswahl aufheben')),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
