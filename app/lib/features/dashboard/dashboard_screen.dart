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

DateTime _today() {
  final n = DateTime.now();
  return DateTime(n.year, n.month, n.day);
}

DateTime _monday(DateTime d) => DateTime(d.year, d.month, d.day - (d.weekday - 1));

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pmc = ref.watch(pmcProvider);

    Future<void> refresh() async {
      ref
        ..invalidate(pmcProvider)
        ..invalidate(activitiesProvider)
        ..invalidate(calendarProvider)
        ..invalidate(formHintProvider);
      await ref.read(pmcProvider.future);
    }

    return Scaffold(
      body: PageBody(
        onRefresh: refresh,
        children: [
          PageHeader(
            subtitle: DateFormat('EEEE, d. MMMM', 'de').format(DateTime.now()),
            title: greeting(),
          ),
          pmc.when(
            loading: () => const Column(children: [
              LoadingBlock(height: 150),
              SizedBox(height: Gap.md),
              LoadingBlock(height: 300),
            ]),
            error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: refresh),
            data: (d) => d['current'] == null
                ? StatusMessage(
                    icon: Icons.insights_rounded,
                    title: 'Noch keine Trainingsdaten',
                    message: 'Verbinde Strava im Profil und starte die Synchronisierung. '
                        'Danach siehst Du hier Deine Fitness, Ermüdung und Form.',
                    actionLabel: 'Zum Profil',
                    onAction: () => context.go('/profile'),
                  )
                : _Overview(data: d),
          ),
        ],
      ),
    );
  }
}

/// Zwei Spalten auf breiten Bildschirmen, sonst untereinander.
class _Columns extends StatelessWidget {
  const _Columns({required this.left, required this.right, this.leftFlex = 3, this.rightFlex = 2});
  final Widget left;
  final Widget right;
  final int leftFlex;
  final int rightFlex;

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        if (c.maxWidth < 860) {
          return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [left, const SizedBox(height: Gap.md), right]);
        }
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(flex: leftFlex, child: left),
          const SizedBox(width: Gap.md),
          Expanded(flex: rightFlex, child: right),
        ]);
      });
}

class _Overview extends StatelessWidget {
  const _Overview({required this.data});
  final Json data;

  @override
  Widget build(BuildContext context) {
    final cur = data['current'] as Map;
    final rows = [for (final r in data['rows'] as List) Json.from(r as Map)];
    num weekAgo(String k) => rows.length > 7 ? rows[rows.length - 8][k] as num : rows.first[k] as num;
    final ctl = cur['ctl'] as num, atl = cur['atl'] as num, tsb = cur['tsb'] as num;
    final ramp = cur['ramp_rate'] as num?;

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _FormHero(tsb: tsb),
      const SizedBox(height: Gap.md),
      ResponsiveGrid(minItemWidth: MediaQuery.sizeOf(context).width < 600 ? 100 : 200, children: [
        MetricTile(
          label: 'Fitness',
          value: ctl.toStringAsFixed(0),
          unit: 'CTL',
          icon: Icons.favorite_rounded,
          color: AppColors.ctl,
          delta: ctl - weekAgo('ctl'),
          caption: ramp == null ? 'Langfristige Belastung (42 Tage)' : 'Rampe ${ramp > 0 ? '+' : ''}${ramp.toStringAsFixed(1)} pro Woche',
          help: 'Fitness (Chronic Training Load): gewichteter Schnitt Deiner täglichen TSS der letzten 42 Tage. '
              'Steigt langsam, wenn Du regelmäßig trainierst. Eine Rampe von 3–7 pro Woche gilt als nachhaltig.',
        ),
        MetricTile(
          label: 'Ermüdung',
          value: atl.toStringAsFixed(0),
          unit: 'ATL',
          icon: Icons.local_fire_department_rounded,
          color: AppColors.atl,
          delta: atl - weekAgo('atl'),
          caption: 'Kurzfristige Belastung (7 Tage)',
          help: 'Ermüdung (Acute Training Load): gewichteter Schnitt Deiner TSS der letzten 7 Tage. '
              'Reagiert schnell auf harte Einheiten und Ruhetage.',
        ),
        MetricTile(
          label: 'Form',
          value: '${tsb > 0 ? '+' : ''}${tsb.toStringAsFixed(0)}',
          unit: 'TSB',
          icon: Icons.speed_rounded,
          color: AppColors.tsb,
          delta: tsb - weekAgo('tsb'),
          caption: 'Fitness minus Ermüdung',
          help: 'Form (Training Stress Balance) = Fitness − Ermüdung. Positiv heißt erholt, '
              'zwischen −10 und −30 liegt der produktive Trainingsbereich.',
        ),
      ]),
      const SizedBox(height: Gap.md),
      _Columns(
        left: _PmcCard(rows: rows),
        right: _WeekCard(rows: rows),
      ),
      const SizedBox(height: Gap.xl),
      const _Columns(
        leftFlex: 1,
        rightFlex: 1,
        left: _UpcomingWorkouts(),
        right: _RecentActivities(),
      ),
    ]);
  }
}

/// Grosse Karte, die die aktuelle Form in Worte fasst und auf einer Skala zeigt.
class _FormHero extends ConsumerWidget {
  const _FormHero({required this.tsb});
  final num tsb;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final s = FormStatus.of(tsb);
    final hint = ref.watch(formHintProvider);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [s.color.withValues(alpha: 0.16), s.color.withValues(alpha: 0.02)],
          ),
        ),
        padding: const EdgeInsets.all(Gap.xl),
        child: LayoutBuilder(builder: (context, c) {
          final text = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: s.color, borderRadius: BorderRadius.circular(Radii.md)),
                child: Icon(s.icon, color: Colors.white, size: 22),
              ),
              const SizedBox(width: Gap.md),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Deine Form heute',
                      style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
                  Text(s.label, style: t.textTheme.headlineSmall?.copyWith(color: s.color)),
                ]),
              ),
            ]),
            const SizedBox(height: Gap.md),
            _Advice(fallback: s.advice, hint: hint),
          ]);
          final gauge = _FormGauge(tsb: tsb);
          if (c.maxWidth < 640) {
            return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              text,
              const SizedBox(height: Gap.xl),
              gauge,
            ]);
          }
          return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
            Expanded(flex: 5, child: text),
            const SizedBox(width: Gap.xxl),
            Expanded(flex: 4, child: gauge),
          ]);
        }),
      ),
    );
  }
}

/// Hinweis zur Form: Text vom Coach (kennt Gespraech und Ziele), sonst der Standardtext.
/// Waehrend des Ladens ein Platzhalter, damit kurz keine unpassende Standardmeldung steht.
class _Advice extends StatelessWidget {
  const _Advice({required this.fallback, required this.hint});
  final String fallback;
  final AsyncValue<String?> hint;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    if (hint.isLoading && !hint.hasValue) {
      Widget bar(double w) => Container(
            width: w,
            height: 12,
            margin: const EdgeInsets.only(bottom: 8),
            decoration: BoxDecoration(
              color: t.colorScheme.onSurface.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(Radii.pill),
            ),
          );
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        bar(double.infinity),
        bar(180),
      ]);
    }
    return Text(hint.value ?? fallback, style: t.textTheme.bodyMedium);
  }
}

/// Farbskala der Formbereiche mit Markierung des aktuellen Werts.
class _FormGauge extends StatelessWidget {
  const _FormGauge({required this.tsb});
  final num tsb;

  static const _min = -40.0, _max = 35.0;
  static const _bands = [
    (-40.0, -30.0, Color(0xFFEF4444)),
    (-30.0, -10.0, Color(0xFFF59E0B)),
    (-10.0, 5.0, Color(0xFF94A3B8)),
    (5.0, 25.0, Color(0xFF16A34A)),
    (25.0, 35.0, Color(0xFF0EA5E9)),
  ];

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final pos = ((tsb.clamp(_min, _max) - _min) / (_max - _min)).toDouble();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
        Text('${tsb > 0 ? '+' : ''}${tsb.toStringAsFixed(0)}',
            style: t.textTheme.displaySmall?.copyWith(color: FormStatus.of(tsb).color)),
        const SizedBox(width: Gap.sm),
        Text('TSB', style: t.textTheme.labelLarge?.copyWith(color: t.colorScheme.onSurfaceVariant)),
      ]),
      const SizedBox(height: Gap.md),
      LayoutBuilder(builder: (context, c) {
        return SizedBox(
          height: 22,
          child: Stack(clipBehavior: Clip.none, children: [
            Positioned.fill(
              top: 7,
              bottom: 7,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(Radii.pill),
                child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  for (final b in _bands)
                    Expanded(flex: ((b.$2 - b.$1) * 10).round(), child: ColoredBox(color: b.$3.withValues(alpha: 0.85))),
                ]),
              ),
            ),
            Positioned(
              left: (c.maxWidth * pos - 11).clamp(0, c.maxWidth - 22),
              child: Container(
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  color: t.colorScheme.surfaceContainerLowest,
                  shape: BoxShape.circle,
                  border: Border.all(color: t.colorScheme.onSurface, width: 3),
                  boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 6)],
                ),
              ),
            ),
          ]),
        );
      }),
      const SizedBox(height: Gap.sm),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text('Überlastet', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        Text('Produktiv', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        Text('Frisch', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
      ]),
    ]);
  }
}

class _PmcCard extends StatefulWidget {
  const _PmcCard({required this.rows});
  final List<Json> rows;

  @override
  State<_PmcCard> createState() => _PmcCardState();
}

class _PmcCardState extends State<_PmcCard> {
  int _days = 90;

  @override
  Widget build(BuildContext context) {
    final rows = widget.rows.length > _days ? widget.rows.sublist(widget.rows.length - _days) : widget.rows;
    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionHeader(
          title: 'Leistungsverlauf',
          subtitle: 'Fitness, Ermüdung und Form im Zeitverlauf',
          trailing: SegmentedButton<int>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: 42, label: Text('6 W')),
              ButtonSegment(value: 90, label: Text('3 M')),
              ButtonSegment(value: 120, label: Text('4 M')),
            ],
            selected: {_days},
            onSelectionChanged: (s) => setState(() => _days = s.first),
          ),
        ),
        SizedBox(height: 260, child: _PmcChart(rows: rows)),
        const SizedBox(height: Gap.md),
        const Wrap(spacing: Gap.lg, runSpacing: Gap.sm, children: [
          LegendDot(label: 'Fitness', color: AppColors.ctl),
          LegendDot(label: 'Ermüdung', color: AppColors.atl),
          LegendDot(label: 'Form', color: AppColors.tsb),
        ]),
      ]),
    );
  }
}

class _PmcChart extends StatelessWidget {
  const _PmcChart({required this.rows});
  final List<Json> rows;

  List<FlSpot> _spots(String key) =>
      [for (var i = 0; i < rows.length; i++) FlSpot(i.toDouble(), (rows[i][key] as num).toDouble())];

  @override
  Widget build(BuildContext context) {
    final cs = ChartStyle(context);
    final fmt = DateFormat('d. MMM', 'de');
    final step = (rows.length / 4).ceilToDouble().clamp(1, 1000).toDouble();
    return LineChart(
      duration: const Duration(milliseconds: 250),
      LineChartData(
        lineBarsData: [
          LineChartBarData(
            spots: _spots('ctl'),
            color: AppColors.ctl,
            barWidth: 3,
            isCurved: true,
            curveSmoothness: 0.2,
            preventCurveOverShooting: true,
            dotData: const FlDotData(show: false),
            belowBarData: cs.area(AppColors.ctl, opacity: 0.22),
          ),
          LineChartBarData(
            spots: _spots('atl'),
            color: AppColors.atl.withValues(alpha: 0.85),
            barWidth: 1.6,
            isCurved: true,
            curveSmoothness: 0.2,
            preventCurveOverShooting: true,
            dotData: const FlDotData(show: false),
          ),
          LineChartBarData(
            spots: _spots('tsb'),
            color: AppColors.tsb,
            barWidth: 2,
            isCurved: true,
            curveSmoothness: 0.2,
            preventCurveOverShooting: true,
            dashArray: const [6, 3],
            dotData: const FlDotData(show: false),
          ),
        ],
        gridData: cs.grid(),
        borderData: FlBorderData(show: false),
        extraLinesData: ExtraLinesData(horizontalLines: [
          HorizontalLine(y: 0, color: cs.scheme.outline.withValues(alpha: 0.6), strokeWidth: 1),
        ]),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(),
          rightTitles: const AxisTitles(),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 34,
              getTitlesWidget: (v, meta) => (v == meta.min || v == meta.max)
                  ? const SizedBox.shrink()
                  : Text(v.round().toString(), style: cs.axis),
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 26,
              interval: step,
              getTitlesWidget: (v, meta) {
                final i = v.round();
                if (i < 0 || i >= rows.length || v == meta.max) return const SizedBox.shrink();
                return cs.axisLabel(fmt.format(DateTime.parse(rows[i]['date'] as String)));
              },
            ),
          ),
        ),
        lineTouchData: LineTouchData(
          getTouchedSpotIndicator: (bar, idx) => [
            for (final _ in idx)
              TouchedSpotIndicatorData(
                FlLine(color: cs.scheme.outline, strokeWidth: 1, dashArray: const [3, 3]),
                FlDotData(
                  getDotPainter: (s, p, b, i) => FlDotCirclePainter(
                    radius: 4,
                    color: b.color ?? cs.scheme.primary,
                    strokeColor: cs.scheme.surface,
                    strokeWidth: 2,
                  ),
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
                  '${const ['Fitness', 'Ermüdung', 'Form'][s.barIndex]}  ${s.y.toStringAsFixed(0)}',
                  cs.tooltipText(s.bar.color ?? cs.scheme.primary),
                  children: s.barIndex == 0
                      ? [
                          TextSpan(
                              text: '\n${DateFormat('E, d. MMM', 'de').format(DateTime.parse(rows[s.x.toInt()]['date'] as String))}',
                              style: cs.tooltipTitle),
                        ]
                      : null,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Aktuelle Woche (Plan vs. Ist) und TSS der letzten Wochen als Balken.
class _WeekCard extends ConsumerWidget {
  const _WeekCard({required this.rows});
  final List<Json> rows;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final monday = _monday(_today());
    final data = ref.watch(calendarProvider((monday, monday.add(const Duration(days: 6))))).value;
    if (data == null) return const LoadingBlock(height: 360);

    var planned = 0.0, done = 0.0, secs = 0.0, meters = 0.0, rides = 0;
    for (final w in data['workouts'] as List) {
      if ((w as Map)['status'] != 'skipped') planned += ((w['planned_tss'] as num?) ?? 0).toDouble();
    }
    for (final a in data['activities'] as List) {
      done += (((a as Map)['tss'] as num?) ?? 0).toDouble();
      secs += (a['duration_s'] as num).toDouble();
      meters += (a['distance_m'] as num).toDouble();
      rides++;
    }
    final progress = planned > 0 ? (done / planned).clamp(0.0, 1.0) : (done > 0 ? 1.0 : 0.0);

    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionHeader(
          title: 'Diese Woche',
          subtitle: '${DateFormat('d. MMM', 'de').format(monday)} – ${DateFormat('d. MMM', 'de').format(monday.add(const Duration(days: 6)))}',
        ),
        Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
          Text(done.round().toString(), style: t.textTheme.headlineLarge),
          const SizedBox(width: 6),
          Text(planned > 0 ? 'von ${planned.round()} TSS' : 'TSS',
              style: t.textTheme.titleSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
          const Spacer(),
          if (planned > 0)
            Text('${(done / planned * 100).round()} %',
                style: t.textTheme.titleSmall?.copyWith(color: t.colorScheme.primary)),
        ]),
        const SizedBox(height: Gap.sm),
        ClipRRect(
          borderRadius: BorderRadius.circular(Radii.pill),
          child: LinearProgressIndicator(
            value: progress,
            minHeight: 10,
            backgroundColor: t.colorScheme.surfaceContainerHigh,
          ),
        ),
        const SizedBox(height: Gap.lg),
        Row(children: [
          _MiniStat(icon: Icons.schedule_rounded, value: formatDuration(secs), label: 'Zeit'),
          _MiniStat(icon: Icons.route_rounded, value: formatKm(meters), label: 'Distanz'),
          _MiniStat(icon: Icons.directions_bike_rounded, value: '$rides', label: 'Fahrten'),
        ]),
        const SizedBox(height: Gap.xl),
        Text('TSS pro Woche', style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        const SizedBox(height: Gap.sm),
        SizedBox(height: 120, child: _WeeklyBars(rows: rows)),
      ]),
    );
  }
}

class _MiniStat extends StatelessWidget {
  const _MiniStat({required this.icon, required this.value, required this.label});
  final IconData icon;
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Expanded(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 18, color: t.colorScheme.onSurfaceVariant),
        const SizedBox(height: 4),
        Text(value, style: t.textTheme.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
        Text(label, style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
      ]),
    );
  }
}

class _WeeklyBars extends StatelessWidget {
  const _WeeklyBars({required this.rows});
  final List<Json> rows;

  @override
  Widget build(BuildContext context) {
    final cs = ChartStyle(context);
    final thisMonday = _monday(_today());
    final weeks = List.generate(8, (i) => thisMonday.subtract(Duration(days: 7 * (7 - i))));
    final sums = List.filled(8, 0.0);
    for (final r in rows) {
      final d = DateTime.parse(r['date'] as String);
      final idx = weeks.indexOf(_monday(d));
      if (idx >= 0) sums[idx] += (r['tss'] as num).toDouble();
    }
    final maxY = math.max(50.0, sums.reduce(math.max) * 1.15);
    return BarChart(BarChartData(
      maxY: maxY,
      gridData: const FlGridData(show: false),
      borderData: FlBorderData(show: false),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(),
        rightTitles: const AxisTitles(),
        leftTitles: const AxisTitles(),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 22,
            getTitlesWidget: (v, _) => cs.axisLabel('KW ${_isoWeek(weeks[v.toInt()])}'),
          ),
        ),
      ),
      barTouchData: BarTouchData(
        touchTooltipData: BarTouchTooltipData(
          getTooltipColor: (_) => cs.tooltipColor(),
          tooltipBorderRadius: cs.tooltipRadius,
          fitInsideHorizontally: true,
          getTooltipItem: (g, _, rod, _) => BarTooltipItem('${rod.toY.round()} TSS', cs.tooltipText(cs.scheme.primary)),
        ),
      ),
      barGroups: [
        for (var i = 0; i < 8; i++)
          BarChartGroupData(x: i, barRods: [
            BarChartRodData(
              toY: sums[i],
              width: 18,
              color: i == 7 ? cs.scheme.primary : cs.scheme.primary.withValues(alpha: 0.35),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
              backDrawRodData: BackgroundBarChartRodData(show: true, toY: maxY, color: cs.scheme.surfaceContainer),
            ),
          ]),
      ],
    ));
  }
}

int _isoWeek(DateTime d) {
  // UTC, damit die Zeitumstellung die Tagesdifferenz nicht verfaelscht
  final thursday = DateTime.utc(d.year, d.month, d.day + 4 - d.weekday);
  final firstJan = DateTime.utc(thursday.year, 1, 1);
  return ((thursday.difference(firstJan).inDays) / 7).floor() + 1;
}

/// Geplante Trainings der naechsten 7 Tage.
class _UpcomingWorkouts extends ConsumerWidget {
  const _UpcomingWorkouts();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final today = _today();
    final data = ref.watch(calendarProvider((today, today.add(const Duration(days: 7)))));
    final upcoming = [
      for (final w in (data.value?['workouts'] as List?) ?? const [])
        if ((w as Map)['status'] == 'planned') Json.from(w),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SectionHeader(
        title: 'Nächste Trainings',
        subtitle: 'Geplant für die kommenden 7 Tage',
        trailing: TextButton(onPressed: () => context.go('/calendar'), child: const Text('Kalender')),
      ),
      if (data.isLoading && data.value == null)
        const LoadingBlock(height: 80)
      else if (upcoming.isEmpty)
        SurfaceCard(
          child: Row(children: [
            Icon(Icons.event_available_rounded, color: Theme.of(context).colorScheme.outline),
            const SizedBox(width: Gap.md),
            const Expanded(child: Text('Nichts geplant. Lass Dir vom Coach eine Woche planen.')),
            TextButton(onPressed: () => context.go('/coach'), child: const Text('Coach')),
          ]),
        )
      else
        for (final w in upcoming) ...[
          _WorkoutTile(w: w, today: today),
          const SizedBox(height: Gap.sm),
        ],
    ]);
  }
}

class _WorkoutTile extends StatelessWidget {
  const _WorkoutTile({required this.w, required this.today});
  final Json w;
  final DateTime today;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final date = DateTime.parse(w['date'] as String);
    final diff = date.difference(today).inDays;
    final when = diff == 0 ? 'Heute' : diff == 1 ? 'Morgen' : DateFormat('EEEE', 'de').format(date);
    return SurfaceCard(
      padding: const EdgeInsets.all(Gap.md),
      onTap: () => context.push('/workout/${w['id']}'),
      child: Row(children: [
        DateBadge(date: date, color: diff == 0 ? AppColors.tsb : null),
        const SizedBox(width: Gap.md),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(w['title'] as String, style: t.textTheme.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 2),
            Text(
              [when, if (w['planned_duration_s'] != null) formatDuration(w['planned_duration_s'] as num)].join(' · '),
              style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant),
            ),
          ]),
        ),
        if (w['planned_tss'] != null) _TssBadge(tss: w['planned_tss'] as num),
      ]),
    );
  }
}

class _TssBadge extends StatelessWidget {
  const _TssBadge({required this.tss, this.color});
  final num tss;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Text('${tss.round()}', style: t.textTheme.titleMedium?.copyWith(color: color, fontWeight: FontWeight.w800)),
      Text('TSS', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
    ]);
  }
}

class _RecentActivities extends ConsumerWidget {
  const _RecentActivities();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final acts = ref.watch(activitiesProvider);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionHeader(title: 'Letzte Aktivitäten', subtitle: 'Farbe zeigt die Intensität (IF)'),
      acts.when(
        loading: () => const LoadingBlock(height: 80),
        error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(activitiesProvider)),
        data: (list) => list.isEmpty
            ? const SurfaceCard(child: Text('Noch keine Aktivitäten importiert.'))
            : Column(children: [
                for (final a in list.take(10)) ...[
                  ActivityTile(a: a),
                  const SizedBox(height: Gap.sm),
                ],
              ]),
      ),
    ]);
  }
}

/// Aktivitaet als Listeneintrag; die Symbolfarbe entspricht der Zone des IF.
class ActivityTile extends StatelessWidget {
  const ActivityTile({super.key, required this.a});
  final Json a;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final date = DateTime.parse(a['start_time'] as String);
    final ifac = a['intensity_factor'] as num?;
    final c = ifac == null ? t.colorScheme.outline : AppColors.zoneColor(ifac * 100);
    return SurfaceCard(
      padding: const EdgeInsets.all(Gap.md),
      onTap: () => context.push('/activity/${a['id']}'),
      child: Row(children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(color: c.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.md)),
          child: Icon(Icons.directions_bike_rounded, color: c),
        ),
        const SizedBox(width: Gap.md),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(a['name'] as String? ?? 'Fahrt', style: t.textTheme.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 2),
            Text(
              [
                DateFormat('E, d. MMM', 'de').format(date),
                formatDuration(a['duration_s'] as num),
                formatKm(a['distance_m'] as num),
                if (a['norm_power'] != null) '${(a['norm_power'] as num).round()} W NP',
              ].join(' · '),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant),
            ),
          ]),
        ),
        const SizedBox(width: Gap.sm),
        if (a['tss'] != null) _TssBadge(tss: a['tss'] as num, color: c),
      ]),
    );
  }
}
