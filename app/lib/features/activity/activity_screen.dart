import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/charts.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'activity_analysis.dart';

class ActivityScreen extends ConsumerWidget {
  const ActivityScreen({super.key, required this.id});
  final int id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final act = ref.watch(activityProvider(id));
    final streams = ref.watch(streamsProvider(id));
    final ftp = ref.watch(profileProvider).value?['ftp'] as num?;

    // Streams berechnen NP/TSS exakt neu -> Kopfdaten danach aktualisieren
    ref.listen(streamsProvider(id), (_, next) {
      if (next.hasValue) {
        ref
          ..invalidate(activityProvider(id))
          ..invalidate(pmcProvider)
          ..invalidate(activitiesProvider);
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('Aktivität'),
        // Auch bei direktem Aufruf per Link gibt es einen Weg zurueck
        leading: BackButton(onPressed: () => context.canPop() ? context.pop() : context.go('/')),
      ),
      body: PageBody(
        maxWidth: 1000,
        children: [
          act.when(
            loading: () => const LoadingBlock(height: 220),
            error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(activityProvider(id))),
            data: (a) => _Header(a: a),
          ),
          const SizedBox(height: Gap.xl),
          ActivityAnalysisSection(id: id),
          streams.when(
            loading: () => SurfaceCard(
              child: Row(children: [
                const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: Gap.md),
                Expanded(
                  child: Text('Lade Sensordaten von Strava …',
                      style: Theme.of(context).textTheme.bodyMedium),
                ),
              ]),
            ),
            error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(streamsProvider(id))),
            data: (s) => _Details(streams: s, ftp: ftp),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.a});
  final Json a;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    String? n(String k, [int digits = 0]) => a[k] == null ? null : (a[k] as num).toStringAsFixed(digits);
    final date = DateTime.parse(a['start_time'] as String);
    final ifac = a['intensity_factor'] as num?;
    final zone = ifac == null ? null : AppColors.zoneIndex(ifac * 100);
    final tiles = <Widget>[
      MetricTile(compact: true, label: 'Dauer', value: formatDuration(a['duration_s'] as num), icon: Icons.schedule_rounded, color: t.colorScheme.primary),
      MetricTile(compact: true, label: 'Distanz', value: (((a['distance_m'] as num) / 1000)).toStringAsFixed(1), unit: 'km', icon: Icons.route_rounded, color: AppColors.accent),
      if (n('elevation_m') != null)
        MetricTile(compact: true, label: 'Höhenmeter', value: n('elevation_m')!, unit: 'm', icon: Icons.terrain_rounded, color: AppColors.altitude),
      if (n('avg_power') != null)
        MetricTile(compact: true, label: 'Ø Leistung', value: n('avg_power')!, unit: 'W', icon: Icons.bolt_rounded, color: AppColors.power),
      if (n('norm_power') != null)
        MetricTile(
          compact: true,
          label: 'NP',
          value: n('norm_power')!,
          unit: 'W',
          icon: Icons.electric_bolt_rounded,
          color: AppColors.power,
          help: 'Normalized Power: Leistung, die physiologisch einer gleichmäßigen Fahrt entspricht. '
              'Berücksichtigt, dass Spitzen mehr ermüden als konstantes Fahren.',
        ),
      if (n('intensity_factor', 2) != null)
        MetricTile(
          compact: true,
          label: 'IF',
          value: n('intensity_factor', 2)!,
          icon: Icons.speed_rounded,
          color: AppColors.zones[zone!],
          help: 'Intensity Factor = NP ÷ FTP. 0,75 ist eine lockere Ausfahrt, 1,0 entspricht einer Stunde Vollgas.',
        ),
      if (n('tss') != null)
        MetricTile(
          compact: true,
          label: 'TSS',
          value: n('tss')!,
          icon: Icons.fitness_center_rounded,
          color: AppColors.tsb,
          help: 'Training Stress Score: Belastung aus Dauer und Intensität. 100 TSS entsprechen einer Stunde an der FTP.',
        ),
      if (n('avg_hr') != null)
        MetricTile(compact: true, label: 'Ø Puls', value: n('avg_hr')!, unit: 'bpm', icon: Icons.favorite_rounded, color: AppColors.heart),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(DateFormat("EEEE, d. MMMM yyyy · HH:mm 'Uhr'", 'de').format(date).toUpperCase(),
          style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.primary, fontWeight: FontWeight.w700, letterSpacing: 1.1)),
      const SizedBox(height: 2),
      Text(a['name'] as String? ?? 'Fahrt', style: t.textTheme.headlineMedium),
      if (zone != null) ...[
        const SizedBox(height: Gap.sm),
        Pill(label: 'Intensität: ${_zoneNames[zone]}', color: AppColors.zones[zone], icon: Icons.local_fire_department_rounded),
      ],
      const SizedBox(height: Gap.lg),
      ResponsiveGrid(minItemWidth: 150, children: tiles),
    ]);
  }
}

const _zoneNames = ['Erholung', 'Ausdauer', 'Tempo', 'Schwelle', 'VO2max', 'Anaerob', 'Neuromuskulär'];

class _Details extends StatelessWidget {
  const _Details({required this.streams, required this.ftp});
  final Json streams;
  final num? ftp;

  List<FlSpot> _spots(String key) {
    final t = (streams['time'] as List?) ?? const [];
    final v = (streams[key] as List?) ?? const [];
    return [
      for (var i = 0; i < v.length && i < t.length; i++)
        if (v[i] != null) FlSpot((t[i] as num) / 60, (v[i] as num).toDouble()),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final charts = <(String, String, String, Color, IconData)>[
      ('watts', 'Leistung', 'W', AppColors.power, Icons.bolt_rounded),
      ('heartrate', 'Puls', 'bpm', AppColors.heart, Icons.favorite_rounded),
      ('altitude', 'Höhenprofil', 'm', AppColors.altitude, Icons.terrain_rounded),
    ].where((c) => _spots(c.$1).isNotEmpty).toList();
    if (charts.isEmpty) {
      return const StatusMessage(
        icon: Icons.sensors_off_rounded,
        title: 'Keine Sensordaten',
        message: 'Für diese Aktivität wurden keine Leistungs-, Puls- oder Höhendaten aufgezeichnet.',
      );
    }
    final hasPower = charts.any((c) => c.$1 == 'watts');
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (hasPower && ftp != null && ftp! > 0) ...[
        _ZoneDistribution(streams: streams, ftp: ftp!),
        const SizedBox(height: Gap.md),
      ],
      for (final c in charts) ...[
        _StreamChart(spots: _spots(c.$1), title: c.$2, unit: c.$3, color: c.$4, icon: c.$5, ftp: c.$1 == 'watts' ? ftp : null),
        const SizedBox(height: Gap.md),
      ],
    ]);
  }
}

/// Zeit in den sieben Leistungszonen als horizontale Balken.
class _ZoneDistribution extends StatelessWidget {
  const _ZoneDistribution({required this.streams, required this.ftp});
  final Json streams;
  final num ftp;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final time = (streams['time'] as List).cast<num>();
    final watts = streams['watts'] as List;
    final secs = List.filled(7, 0.0);
    for (var i = 0; i < watts.length && i < time.length; i++) {
      if (watts[i] == null) continue;
      final dt = i + 1 < time.length ? (time[i + 1] - time[i]).toDouble() : 0.0;
      secs[AppColors.zoneIndex((watts[i] as num) / ftp * 100)] += dt;
    }
    final total = secs.fold(0.0, (a, b) => a + b);
    if (total <= 0) return const SizedBox.shrink();
    final maxShare = secs.reduce(math.max) / total;

    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionHeader(title: 'Zeit in Leistungszonen', subtitle: 'Bezogen auf Deine FTP von ${ftp.round()} W'),
        // Gestapelter Gesamtbalken
        ClipRRect(
          borderRadius: BorderRadius.circular(Radii.pill),
          child: SizedBox(
            height: 12,
            child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              for (var z = 0; z < 7; z++)
                if (secs[z] > 0) Expanded(flex: (secs[z] / total * 1000).round().clamp(1, 1000), child: ColoredBox(color: AppColors.zones[z])),
            ]),
          ),
        ),
        const SizedBox(height: Gap.lg),
        for (var z = 0; z < 7; z++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              SizedBox(
                width: 132,
                child: Row(children: [
                  Container(
                    width: 28,
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: AppColors.zones[z], borderRadius: BorderRadius.circular(6)),
                    child: Text('Z${z + 1}',
                        style: t.textTheme.labelSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.w800)),
                  ),
                  const SizedBox(width: Gap.sm),
                  Expanded(child: Text(_zoneNames[z], style: t.textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
                ]),
              ),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, c) => Align(
                    alignment: Alignment.centerLeft,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 400),
                      height: 10,
                      width: maxShare == 0 ? 0 : c.maxWidth * (secs[z] / total) / maxShare,
                      decoration: BoxDecoration(
                        color: AppColors.zones[z],
                        borderRadius: BorderRadius.circular(Radii.pill),
                      ),
                    ),
                  ),
                ),
              ),
              SizedBox(
                width: 96,
                child: Text(
                  '${formatDuration(secs[z])}  ${(secs[z] / total * 100).round()} %',
                  textAlign: TextAlign.right,
                  style: t.textTheme.labelMedium?.copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
                ),
              ),
            ]),
          ),
      ]),
    );
  }
}

class _StreamChart extends StatelessWidget {
  const _StreamChart({
    required this.spots,
    required this.title,
    required this.unit,
    required this.color,
    required this.icon,
    this.ftp,
  });
  final List<FlSpot> spots;
  final String title;
  final String unit;
  final Color color;
  final IconData icon;
  final num? ftp;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final cs = ChartStyle(context);
    final ys = spots.map((s) => s.y);
    final avg = ys.reduce((a, b) => a + b) / spots.length;
    final maxV = ys.reduce(math.max);
    final minV = ys.reduce(math.min);
    final isAltitude = unit == 'm';

    Widget stat(String label, num v) => Padding(
          padding: const EdgeInsets.only(left: Gap.lg),
          child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text(label, style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
            Text('${v.round()} $unit', style: t.textTheme.titleSmall),
          ]),
        );

    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(Radii.sm)),
            child: Icon(icon, size: 16, color: color),
          ),
          const SizedBox(width: Gap.sm),
          Expanded(child: Text(title, style: t.textTheme.titleMedium)),
          if (isAltitude) ...[stat('Min', minV), stat('Max', maxV)] else ...[stat('Ø', avg), stat('Max', maxV)],
        ]),
        const SizedBox(height: Gap.lg),
        SizedBox(
          height: 180,
          child: LineChart(LineChartData(
            minY: isAltitude ? (minV - (maxV - minV) * 0.1).floorToDouble() : 0,
            lineBarsData: [
              LineChartBarData(
                spots: spots,
                color: color,
                barWidth: 1.6,
                dotData: const FlDotData(show: false),
                belowBarData: cs.area(color, opacity: isAltitude ? 0.35 : 0.25),
              ),
            ],
            gridData: cs.grid(),
            borderData: FlBorderData(show: false),
            extraLinesData: ftp == null
                ? null
                : ExtraLinesData(horizontalLines: [
                    HorizontalLine(
                      y: ftp!.toDouble(),
                      color: AppColors.zones[3],
                      strokeWidth: 1.2,
                      dashArray: const [6, 4],
                      label: HorizontalLineLabel(
                        show: true,
                        alignment: Alignment.topRight,
                        style: cs.axis.copyWith(color: AppColors.zones[3], fontWeight: FontWeight.w700),
                        labelResolver: (_) => 'FTP',
                      ),
                    ),
                  ]),
            titlesData: FlTitlesData(
              topTitles: const AxisTitles(),
              rightTitles: const AxisTitles(),
              leftTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 40,
                  getTitlesWidget: (v, meta) => (v == meta.min || v == meta.max)
                      ? const SizedBox.shrink()
                      : Text(v.round().toString(), style: cs.axis),
                ),
              ),
              bottomTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 26,
                  getTitlesWidget: (v, meta) => (v == meta.min || v == meta.max)
                      ? const SizedBox.shrink()
                      : cs.axisLabel(formatDuration(v * 60)),
                ),
              ),
            ),
            lineTouchData: LineTouchData(
              getTouchedSpotIndicator: (bar, idx) => [
                for (final _ in idx)
                  TouchedSpotIndicatorData(
                    FlLine(color: cs.scheme.outline, strokeWidth: 1, dashArray: const [3, 3]),
                    FlDotData(
                      getDotPainter: (s, p, b, i) =>
                          FlDotCirclePainter(radius: 4, color: color, strokeColor: cs.scheme.surface, strokeWidth: 2),
                    ),
                  ),
              ],
              touchTooltipData: LineTouchTooltipData(
                getTooltipColor: (_) => cs.tooltipColor(),
                tooltipBorderRadius: cs.tooltipRadius,
                fitInsideHorizontally: true,
                fitInsideVertically: true,
                getTooltipItems: (spots) => [
                  for (final s in spots)
                    LineTooltipItem(
                      '${s.y.round()} $unit',
                      cs.tooltipText(color),
                      children: [TextSpan(text: '\nbei ${formatDuration(s.x * 60)}', style: cs.tooltipTitle)],
                    ),
                ],
              ),
            ),
          )),
        ),
      ]),
    );
  }
}
