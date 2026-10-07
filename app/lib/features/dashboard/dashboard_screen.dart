import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/charts.dart';
import '../../core/data.dart';
import '../../core/sport.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'load_style.dart';
import 'today_card.dart';
import 'week_card.dart';

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
        ..invalidate(formHintProvider)
        ..invalidate(loadCheckProvider);
      await ref.read(pmcProvider.future);
    }

    return Scaffold(
      body: PageBody(
        onRefresh: refresh,
        children: [
          PageHeader(subtitle: DateFormat('EEEE, d. MMMM', 'de').format(DateTime.now()), title: greeting()),
          pmc.when(
            loading: () => const Column(
              children: [
                LoadingBlock(height: 150),
                SizedBox(height: Gap.md),
                LoadingBlock(height: 300),
              ],
            ),
            error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: refresh),
            data: (d) => d['current'] == null
                ? StatusMessage(
                    icon: Icons.insights_rounded,
                    title: 'Noch keine Trainingsdaten',
                    message:
                        'Verbinde Strava im Profil und starte die Synchronisierung. '
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
  const _Columns({required this.left, required this.right, this.leftFlex = 3, this.rightFlex = 2, this.equalHeight = false});
  final Widget left;
  final Widget right;
  final int leftFlex;
  final int rightFlex;
  final bool equalHeight;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) {
      if (c.maxWidth < 860) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            left,
            const SizedBox(height: Gap.md),
            right,
          ],
        );
      }
      final row = Row(
        crossAxisAlignment: equalHeight ? CrossAxisAlignment.stretch : CrossAxisAlignment.start,
        children: [
          Expanded(flex: leftFlex, child: left),
          const SizedBox(width: Gap.md),
          Expanded(flex: rightFlex, child: right),
        ],
      );
      // Beide Karten gleich hoch, damit unter der kuerzeren keine Luecke bleibt (nur fuer Karten ohne LayoutBuilder/Diagramm)
      return equalHeight ? StretchScope(child: IntrinsicHeight(child: row)) : row;
    },
  );
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

    // Reihenfolge nach Bedeutung: Zustand, heutiges Training, Woche, danach Verlauf und letzte Fahrten
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _FormHero(tsb: tsb, ctl: ctl, atl: atl, ctlDelta: ctl - weekAgo('ctl'), atlDelta: atl - weekAgo('atl')),
        const SizedBox(height: Gap.md),
        const _Columns(leftFlex: 1, rightFlex: 1, equalHeight: true, left: TodayCard(), right: WeekCard()),
        const SizedBox(height: Gap.md),
        _PmcCard(rows: rows),
        const SizedBox(height: Gap.xl),
        const _RecentActivities(),
      ],
    );
  }
}

/// Grosse Karte, die die aktuelle Form in Worte fasst und auf einer Skala zeigt.
class _FormHero extends ConsumerWidget {
  const _FormHero({required this.tsb, required this.ctl, required this.atl, this.ctlDelta, this.atlDelta});
  final num tsb;
  final num ctl;
  final num atl;
  final num? ctlDelta;
  final num? atlDelta;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final s = FormStatus.of(tsb);
    final hint = ref.watch(formHintProvider);
    final load = ref.watch(loadCheckProvider).value;
    final verdict = ((load?['coach'] as Map?)?['verdict'] ?? load?['verdict']) as String?;
    final loadText = (load?['coach'] as Map?)?['text'] as String?;
    final warn = verdict == 'too_much' || verdict == 'slightly_much';
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
        child: LayoutBuilder(
          builder: (context, c) {
            final text = Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(color: s.color, borderRadius: BorderRadius.circular(Radii.md)),
                      child: Icon(s.icon, color: Colors.white, size: 22),
                    ),
                    const SizedBox(width: Gap.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Deine Form heute',
                            style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
                          ),
                          Text(s.label, style: t.textTheme.headlineSmall?.copyWith(color: s.color)),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: Gap.md),
                _Advice(fallback: s.advice, hint: hint),
                if (warn && loadText != null) ...[
                  const SizedBox(height: Gap.md),
                  Container(
                    padding: const EdgeInsets.all(Gap.md),
                    decoration: BoxDecoration(
                      color: loadVerdictStyle(verdict).$2.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(Radii.md),
                    ),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(loadVerdictStyle(verdict).$3, size: 18, color: loadVerdictStyle(verdict).$2),
                      const SizedBox(width: Gap.sm),
                      Expanded(child: Text(loadText, style: t.textTheme.bodyMedium)),
                    ]),
                  ),
                ],
              ],
            );
            final chips = Wrap(spacing: Gap.sm, runSpacing: Gap.sm, children: [
              Pill(label: 'Fitness ${ctl.round()}${_trend(ctlDelta)}', color: AppColors.ctl, icon: Icons.favorite_rounded),
              Pill(label: 'Ermüdung ${atl.round()}${_trend(atlDelta)}', color: AppColors.atl, icon: Icons.local_fire_department_rounded),
              if (verdict != null)
                Pill(
                  label: 'Belastung: ${loadVerdictStyle(verdict).$1}',
                  color: loadVerdictStyle(verdict).$2,
                  icon: loadVerdictStyle(verdict).$3,
                ),
            ]);
            final gauge = Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [_FormGauge(tsb: tsb), const SizedBox(height: Gap.md), chips],
            );
            if (c.maxWidth < 640) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  text,
                  const SizedBox(height: Gap.xl),
                  gauge,
                ],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(flex: 5, child: text),
                const SizedBox(width: Gap.xxl),
                Expanded(flex: 4, child: gauge),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Veraenderung gegenueber der Vorwoche als Zahl mit Vorzeichen (Pfeile fehlen in manchen Schriften).
String _trend(num? d) => d == null || d.abs() < 1 ? '' : '  ${d > 0 ? '+' : '−'}${d.abs().round()}';

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
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [bar(double.infinity), bar(180)]);
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(
              '${tsb > 0 ? '+' : ''}${tsb.toStringAsFixed(0)}',
              style: t.textTheme.displaySmall?.copyWith(color: FormStatus.of(tsb).color),
            ),
            const SizedBox(width: Gap.sm),
            Text('TSB', style: t.textTheme.labelLarge?.copyWith(color: t.colorScheme.onSurfaceVariant)),
          ],
        ),
        const SizedBox(height: Gap.md),
        LayoutBuilder(
          builder: (context, c) {
            return SizedBox(
              height: 22,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  Positioned.fill(
                    top: 7,
                    bottom: 7,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(Radii.pill),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          for (final b in _bands)
                            Expanded(
                              flex: ((b.$2 - b.$1) * 10).round(),
                              child: ColoredBox(color: b.$3.withValues(alpha: 0.85)),
                            ),
                        ],
                      ),
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
                ],
              ),
            );
          },
        ),
        const SizedBox(height: Gap.sm),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Überlastet', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
            Text('Produktiv', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
            Text('Frisch', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
          ],
        ),
      ],
    );
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
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
          const Wrap(
            spacing: Gap.lg,
            runSpacing: Gap.sm,
            children: [
              LegendDot(label: 'Fitness', color: AppColors.ctl),
              LegendDot(label: 'Ermüdung', color: AppColors.atl),
              LegendDot(label: 'Form', color: AppColors.tsb),
            ],
          ),
        ],
      ),
    );
  }
}

class _PmcChart extends StatelessWidget {
  const _PmcChart({required this.rows});
  final List<Json> rows;

  List<FlSpot> _spots(String key) => [
    for (var i = 0; i < rows.length; i++) FlSpot(i.toDouble(), (rows[i][key] as num).toDouble()),
  ];

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
        extraLinesData: ExtraLinesData(
          horizontalLines: [HorizontalLine(y: 0, color: cs.scheme.outline.withValues(alpha: 0.6), strokeWidth: 1)],
        ),
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
                            text:
                                '\n${DateFormat('E, d. MMM', 'de').format(DateTime.parse(rows[s.x.toInt()]['date'] as String))}',
                            style: cs.tooltipTitle,
                          ),
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

class _TssBadge extends StatelessWidget {
  const _TssBadge({required this.tss, this.color});
  final num tss;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          '${tss.round()}',
          style: t.textTheme.titleMedium?.copyWith(color: color, fontWeight: FontWeight.w800),
        ),
        Text('TSS', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
      ],
    );
  }
}

/// Die drei letzten Fahrten mit Ueberschrift des Coach-Feedbacks; alle weiteren stehen im Kalender.
/// Breit nebeneinander in gleich hohen Karten, schmal untereinander.
class _RecentActivities extends ConsumerWidget {
  const _RecentActivities();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final acts = ref.watch(activitiesProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'Letzte Fahrten',
          subtitle: 'Mit Feedback Deines Coaches',
          trailing: TextButton(onPressed: () => context.go('/calendar'), child: const Text('Kalender')),
        ),
        acts.when(
          loading: () => const LoadingBlock(height: 80),
          error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(activitiesProvider)),
          data: (list) {
            if (list.isEmpty) return const SurfaceCard(child: Text('Noch keine Aktivitäten importiert.'));
            final tiles = [for (final a in list.take(3)) ActivityTile(a: a)];
            return LayoutBuilder(
              builder: (context, c) {
                if (c.maxWidth < 860) {
                  return Column(children: [for (final t in tiles) ...[t, const SizedBox(height: Gap.sm)]]);
                }
                return IntrinsicHeight(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      for (var i = 0; i < 3; i++) ...[
                        if (i > 0) const SizedBox(width: Gap.md),
                        Expanded(child: i < tiles.length ? tiles[i] : const SizedBox.shrink()),
                      ],
                    ],
                  ),
                );
              },
            );
          },
        ),
      ],
    );
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
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(color: c.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.md)),
            child: Icon(sportInfo(a['sport'] as String?).icon, color: c),
          ),
          const SizedBox(width: Gap.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  a['name'] as String? ?? sportInfo(a['sport'] as String?).label,
                  style: t.textTheme.titleSmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
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
                if ((a['feedback_headline'] as String?)?.isNotEmpty ?? false) ...[
                  const SizedBox(height: 2),
                  Row(children: [
                    Icon(Icons.auto_awesome, size: 12, color: t.colorScheme.primary),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        a['feedback_headline'] as String,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.primary),
                      ),
                    ),
                  ]),
                ],
              ],
            ),
          ),
          const SizedBox(width: Gap.sm),
          if (a['tss'] != null) _TssBadge(tss: a['tss'] as num, color: c),
        ],
      ),
    );
  }
}
