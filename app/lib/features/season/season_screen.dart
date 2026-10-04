import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart' hide TextDirection;

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

/// Saisonplan (ATP): Phasen, Wochenziele und Events als Jahresuebersicht mit Fitness-Prognose.
class SeasonScreen extends ConsumerWidget {
  const SeasonScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final range = seasonRange();
    final plan = ref.watch(atpProvider(range));

    Future<void> refresh() async {
      ref.invalidate(atpProvider);
      await ref.read(atpProvider(range).future);
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Saisonplan'),
        leading: BackButton(onPressed: () => context.canPop() ? context.pop() : context.go('/calendar')),
        actions: [
          TextButton.icon(
            onPressed: () => showEventDialog(context, ref),
            icon: const Icon(Icons.flag_outlined, size: 18),
            label: const Text('Event'),
          ),
          PopupMenuButton<String>(
            tooltip: 'Mehr',
            onSelected: (v) => _clearPlan(context, ref),
            itemBuilder: (_) => const [PopupMenuItem(value: 'clear', child: Text('Alle Wochen löschen'))],
          ),
          const SizedBox(width: Gap.sm),
        ],
      ),
      body: PageBody(
        maxWidth: 1100,
        onRefresh: refresh,
        children: [
          plan.when(
            loading: () => const Column(
              children: [
                LoadingBlock(height: 120),
                SizedBox(height: Gap.md),
                LoadingBlock(height: 340),
              ],
            ),
            error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: refresh),
            data: (d) => _SeasonBody(data: d),
          ),
        ],
      ),
    );
  }

  Future<void> _clearPlan(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Alle Wochen löschen?'),
        content: const Text(
          'Der gesamte Saisonplan (Phasen und Wochenziele) wird gelöscht. Events und geplante Trainings bleiben bestehen.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Löschen')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref
          .read(apiProvider)
          .dio
          .delete('/atp/weeks', queryParameters: {'start': isoDay(DateTime(2000)), 'end': isoDay(DateTime(2100))});
      ref.invalidate(atpProvider);
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessage(e))));
    }
  }
}

class _SeasonBody extends StatefulWidget {
  const _SeasonBody({required this.data});
  final Json data;

  @override
  State<_SeasonBody> createState() => _SeasonBodyState();
}

class _SeasonBodyState extends State<_SeasonBody> {
  int? _selected;
  final _scroll = ScrollController();
  bool _scrolled = false;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  List<Json> get _weeks => [for (final w in widget.data['weeks'] as List) Json.from(w as Map)];
  List<Json> get _events => [for (final e in widget.data['events'] as List) Json.from(e as Map)];

  @override
  Widget build(BuildContext context) {
    final weeks = _weeks, events = _events;
    final now = DateTime.now();
    final curKey = isoDay(mondayOf(now));
    final curIdx = weeks.indexWhere((w) => w['week_start'] == curKey);
    final hasPlan = weeks.any((w) => w['phase'] != null);
    final selected = (_selected ?? (curIdx >= 0 ? curIdx : 0)).clamp(0, math.max(weeks.length - 1, 0)).toInt();

    if (!hasPlan && events.isEmpty) return _EmptySeason();

    final upcoming = events.where((e) => (e['days_to_go'] as int) >= 0).toList();
    final next = upcoming.firstWhere(
      (e) => e['priority'] == 'A',
      orElse: () => upcoming.isEmpty ? <String, dynamic>{} : upcoming.first,
    );
    final cur = curIdx >= 0 ? weeks[curIdx] : null;
    final formTsb = (next['form_tsb'] as num?);
    final formOk = formTsb != null && formTsb >= 5 && formTsb <= 25;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ResponsiveGrid(
          minItemWidth: MediaQuery.sizeOf(context).width < 600 ? 150 : 200,
          children: [
            MetricTile(
              label: 'Aktuelle Phase',
              value: cur?['phase'] == null ? '–' : Phases.label(cur!['phase'] as String),
              color: cur?['phase'] == null ? null : Phases.color(cur!['phase'] as String),
              icon: Icons.timeline_rounded,
              caption: cur?['tss_target'] == null
                  ? 'Kein Plan für diese Woche'
                  : 'Wochenziel ${(cur!['tss_target'] as num).round()} TSS',
            ),
            MetricTile(
              label: 'Diese Woche',
              value: '${(cur?['actual_tss'] as num? ?? 0).round()}',
              unit: cur?['tss_target'] == null ? 'TSS' : 'von ${(cur!['tss_target'] as num).round()} TSS',
              icon: Icons.fitness_center_rounded,
              color: AppColors.completed,
              caption: 'Geplante Trainings: ${(cur?['planned_tss'] as num? ?? 0).round()} TSS',
            ),
            MetricTile(
              label: next['priority'] == 'A' ? 'Nächstes A-Event' : 'Nächstes Event',
              value: next.isEmpty ? '–' : '${next['days_to_go']}',
              unit: next.isEmpty ? null : 'Tage',
              icon: Icons.flag_rounded,
              color: next.isEmpty ? null : EventPriority.color(next['priority'] as String),
              caption: next.isEmpty ? 'Noch kein Event eingetragen' : next['name'] as String,
            ),
            MetricTile(
              label: 'Form am Event',
              value: formTsb == null ? '–' : '${formTsb > 0 ? '+' : ''}${formTsb.round()}',
              unit: formTsb == null ? null : 'TSB',
              icon: Icons.speed_rounded,
              color: formTsb == null ? null : (formOk ? AppColors.completed : AppColors.tsb),
              caption: formTsb == null
                  ? 'Prognose, sobald Plan und Event vorliegen'
                  : 'Prognose laut Plan, Ziel +5 bis +25',
              help:
                  'Die Prognose verteilt die Wochenziele gleichmäßig auf die Tage und rechnet daraus Fitness (CTL) und Form (TSB). '
                  'Für ein A-Event gelten +5 bis +25 als gute Rennform.',
            ),
          ],
        ),
        const SizedBox(height: Gap.md),
        if (hasPlan) ...[
          SurfaceCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(
                  title: 'Saison im Überblick',
                  subtitle:
                      'Blasse Balken: Wochenziel · grün: gefahrene TSS · blaue Linie: Fitness (gestrichelt = Prognose)',
                ),
                _chart(_trimmed(weeks, events), events, curIdx, selected),
                const SizedBox(height: Gap.md),
                Wrap(
                  spacing: Gap.lg,
                  runSpacing: Gap.xs,
                  children: [
                    for (final k in Phases.all.keys)
                      if (weeks.any((w) => w['phase'] == k)) LegendDot(label: Phases.label(k), color: Phases.color(k)),
                    const LegendDot(label: 'Gefahren', color: AppColors.completed),
                    const LegendDot(label: 'Fitness (CTL)', color: AppColors.ctl),
                  ],
                ),
                if (weeks.isNotEmpty) ...[
                  const Divider(height: Gap.xxl),
                  _WeekDetails(week: weeks[selected], onEdit: () => showWeekSheet(context, weeks[selected])),
                ],
              ],
            ),
          ),
          const SizedBox(height: Gap.md),
        ],
        _EventsCard(events: events),
        if (hasPlan) ...[
          const SizedBox(height: Gap.md),
          _WeeksCard(
            weeks: weeks,
            onPick: (i) {
              setState(() => _selected = i);
              showWeekSheet(context, weeks[i]);
            },
          ),
        ],
      ],
    );
  }

  /// Kuerzt den leeren Rest hinter dem letzten Planeintrag oder Event (vier Wochen Puffer); Indizes bleiben gleich.
  List<Json> _trimmed(List<Json> weeks, List<Json> events) {
    var last = weeks.lastIndexWhere((w) => w['phase'] != null);
    for (final e in events) {
      final i = weeks.indexWhere(
        (w) =>
            (e['date'] as String).compareTo(w['week_start'] as String) >= 0 &&
            DateTime.parse(e['date'] as String).difference(DateTime.parse(w['week_start'] as String)).inDays < 7,
      );
      last = math.max(last, i);
    }
    return weeks.sublist(0, math.min(weeks.length, math.max(last + 5, 12)));
  }

  Widget _chart(List<Json> weeks, List<Json> events, int curIdx, int selected) {
    return LayoutBuilder(
      builder: (context, c) {
        final t = Theme.of(context);
        final width = math.max(c.maxWidth, weeks.length * 15.0 + 2 * SeasonPainter.pad);
        if (!_scrolled && curIdx >= 0 && width > c.maxWidth) {
          _scrolled = true;
          final target = ((curIdx - 3) / weeks.length * (width - 2 * SeasonPainter.pad)).clamp(0.0, width - c.maxWidth);
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (_scroll.hasClients) _scroll.jumpTo(target.toDouble());
          });
        }
        void pick(Offset p) {
          final ww = (width - 2 * SeasonPainter.pad) / weeks.length;
          final i = ((p.dx - SeasonPainter.pad) / ww).floor();
          if (i >= 0 && i < weeks.length) setState(() => _selected = i);
        }

        return SingleChildScrollView(
          controller: _scroll,
          scrollDirection: Axis.horizontal,
          child: MouseRegion(
            child: GestureDetector(
              onTapDown: (d) => pick(d.localPosition),
              child: CustomPaint(
                size: Size(width, 340),
                painter: SeasonPainter(
                  weeks: weeks,
                  events: events,
                  currentIndex: curIdx,
                  selected: selected,
                  grid: t.colorScheme.outlineVariant,
                  muted: t.colorScheme.onSurfaceVariant,
                  text: t.colorScheme.onSurface,
                  primary: t.colorScheme.primary,
                  surface: t.colorScheme.surfaceContainerLow,
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _EmptySeason extends StatelessWidget {
  @override
  Widget build(BuildContext context) => StatusMessage(
    icon: Icons.timeline_rounded,
    title: 'Noch kein Saisonplan',
    message:
        'Der Coach baut Deinen Plan rückwärts von Deinen Hauptzielen auf: Wettkampf, Spitze, Aufbau, Grundlage. '
        'Nenne ihm Events mit Datum und Priorität und Deine verfügbare Zeit pro Woche. Du kannst Events auch selbst eintragen.',
    actionLabel: 'Mit dem Coach erstellen',
    onAction: () => context.go('/coach'),
  );
}

/// Details der angetippten Woche mit Knopf zum Bearbeiten.
class _WeekDetails extends StatelessWidget {
  const _WeekDetails({required this.week, required this.onEdit});
  final Json week;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final start = DateTime.parse(week['week_start'] as String);
    final phase = week['phase'] as String?;
    final muted = t.colorScheme.onSurfaceVariant;
    Widget stat(String label, String value) => Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: t.textTheme.labelSmall?.copyWith(color: muted)),
        Text(value, style: t.textTheme.titleSmall),
      ],
    );
    final target = week['tss_target'] as num?;
    final hours = week['hours_target'] as num?;
    final ctl = week['ctl'] as num?;
    final tsb = week['tsb'] as num?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Wrap(
                spacing: Gap.sm,
                runSpacing: Gap.xs,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(
                    'KW ${isoWeek(start)} · ${DateFormat('d. MMM', 'de').format(start)} – ${DateFormat('d. MMM', 'de').format(start.add(const Duration(days: 6)))}',
                    style: t.textTheme.titleMedium,
                  ),
                  if (phase != null) Pill(label: Phases.label(phase), color: Phases.color(phase)),
                  if (week['recovery'] == true)
                    Pill(label: 'Entlastung', color: AppColors.completed, icon: Icons.battery_charging_full_rounded),
                ],
              ),
            ),
            OutlinedButton.icon(
              onPressed: onEdit,
              icon: const Icon(Icons.edit_outlined, size: 18),
              label: Text(phase == null ? 'Planen' : 'Bearbeiten'),
            ),
          ],
        ),
        const SizedBox(height: Gap.md),
        Wrap(
          spacing: Gap.xxl,
          runSpacing: Gap.md,
          children: [
            stat(
              'Wochenziel',
              target == null
                  ? '–'
                  : '${target.round()} TSS${hours == null ? '' : ' · ${hours.toStringAsFixed(hours % 1 == 0 ? 0 : 1)} h'}',
            ),
            stat('Geplante Trainings', '${(week['planned_tss'] as num).round()} TSS'),
            stat('Gefahren', '${(week['actual_tss'] as num).round()} TSS'),
            stat(
              week['projected'] == true ? 'Fitness (Prognose)' : 'Fitness',
              ctl == null ? '–' : ctl.toStringAsFixed(0),
            ),
            stat('Form', tsb == null ? '–' : '${tsb > 0 ? '+' : ''}${tsb.round()}'),
          ],
        ),
        if ((week['note'] as String?) != null) ...[
          const SizedBox(height: Gap.md),
          Text(week['note'] as String, style: t.textTheme.bodyMedium?.copyWith(color: muted)),
        ],
      ],
    );
  }
}

class _EventsCard extends ConsumerWidget {
  const _EventsCard({required this.events});
  final List<Json> events;

  Future<void> _delete(BuildContext context, WidgetRef ref, Json e) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('„${e['name']}“ löschen?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Löschen')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(apiProvider).dio.delete('/atp/events/${e['id']}');
      ref.invalidate(atpProvider);
    } catch (err) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessage(err))));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            title: 'Events',
            subtitle: 'A = Hauptziel, B = wichtig, C = Trainingswettkampf',
            trailing: TextButton.icon(
              onPressed: () => showEventDialog(context, ref),
              icon: const Icon(Icons.add_rounded, size: 18),
              label: const Text('Neu'),
            ),
          ),
          if (events.isEmpty)
            Text(
              'Noch keine Events im Zeitraum. Trage Wettkämpfe ein oder nenne sie dem Coach.',
              style: t.textTheme.bodyMedium?.copyWith(color: muted),
            )
          else
            for (final e in events)
              Container(
                margin: const EdgeInsets.only(bottom: Gap.sm),
                padding: const EdgeInsets.fromLTRB(Gap.md, Gap.sm, Gap.xs, Gap.sm),
                decoration: BoxDecoration(
                  color: t.colorScheme.surfaceContainer.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(Radii.md),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: EventPriority.color(e['priority'] as String),
                        borderRadius: BorderRadius.circular(Radii.sm),
                      ),
                      child: Text(
                        e['priority'] as String,
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800),
                      ),
                    ),
                    const SizedBox(width: Gap.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            e['name'] as String,
                            style: t.textTheme.titleSmall,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          Text(
                            [
                              DateFormat('EEE, d. MMM yyyy', 'de').format(DateTime.parse(e['date'] as String)),
                              _inDays(e['days_to_go'] as int),
                              if (e['form_tsb'] != null)
                                'Form ${(e['form_tsb'] as num) > 0 ? '+' : ''}${(e['form_tsb'] as num).round()}',
                            ].join(' · '),
                            style: t.textTheme.bodySmall?.copyWith(color: muted),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: 'Bearbeiten',
                      onPressed: () => showEventDialog(context, ref, event: e),
                      icon: const Icon(Icons.edit_outlined, size: 18),
                    ),
                    IconButton(
                      tooltip: 'Löschen',
                      onPressed: () => _delete(context, ref, e),
                      icon: const Icon(Icons.close_rounded, size: 18),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }

  static String _inDays(int d) => d == 0
      ? 'heute'
      : d == 1
      ? 'morgen'
      : d > 0
      ? 'in $d Tagen'
      : 'vor ${-d} Tagen';
}

/// Alle Wochen mit Plan als Liste; antippen zum Bearbeiten.
class _WeeksCard extends StatelessWidget {
  const _WeeksCard({required this.weeks, required this.onPick});
  final List<Json> weeks;
  final void Function(int index) onPick;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final rows = [
      for (var i = 0; i < weeks.length; i++)
        if (weeks[i]['phase'] != null) i,
    ];
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'Wochen', subtitle: 'Antippen zum Bearbeiten'),
          for (final i in rows)
            Builder(
              builder: (context) {
                final w = weeks[i];
                final start = DateTime.parse(w['week_start'] as String);
                final phase = w['phase'] as String;
                final target = (w['tss_target'] as num).round();
                final hours = w['hours_target'] as num?;
                final actual = (w['actual_tss'] as num).round();
                return InkWell(
                  borderRadius: BorderRadius.circular(Radii.md),
                  onTap: () => onPick(i),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 10, horizontal: Gap.xs),
                    child: Row(
                      children: [
                        Container(
                          width: 4,
                          height: 36,
                          decoration: BoxDecoration(color: Phases.color(phase), borderRadius: BorderRadius.circular(2)),
                        ),
                        const SizedBox(width: Gap.md),
                        SizedBox(
                          width: 92,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('KW ${isoWeek(start)}', style: t.textTheme.titleSmall),
                              Text(
                                DateFormat('d. MMM', 'de').format(start),
                                style: t.textTheme.bodySmall?.copyWith(color: muted),
                              ),
                            ],
                          ),
                        ),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                Phases.label(phase) + (w['recovery'] == true ? ' · Entlastung' : ''),
                                style: t.textTheme.bodyMedium?.copyWith(
                                  color: Phases.color(phase),
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              if (w['note'] != null)
                                Text(
                                  w['note'] as String,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: t.textTheme.bodySmall?.copyWith(color: muted),
                                ),
                            ],
                          ),
                        ),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(
                              '$target TSS${hours == null ? '' : ' · ${hours.toStringAsFixed(hours % 1 == 0 ? 0 : 1)} h'}',
                              style: t.textTheme.titleSmall,
                            ),
                            Text(
                              actual > 0 ? 'gefahren $actual' : 'geplant ${(w['planned_tss'] as num).round()}',
                              style: t.textTheme.bodySmall?.copyWith(color: muted),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
        ],
      ),
    );
  }
}

// --------------------------------------------------------------- Diagramm ---

/// Zeichnet Phasenband, Wochenziele, gefahrene TSS, Fitness-Linie, Events und die heutige Woche.
class SeasonPainter extends CustomPainter {
  SeasonPainter({
    required this.weeks,
    required this.events,
    required this.currentIndex,
    required this.selected,
    required this.grid,
    required this.muted,
    required this.text,
    required this.primary,
    required this.surface,
  });

  static const pad = 38.0; // Platz fuer die Achsenbeschriftung links (TSS) und rechts (CTL)
  final List<Json> weeks;
  final List<Json> events;
  final int currentIndex;
  final int selected;
  final Color grid, muted, text, primary, surface;

  static const _phaseH = 20.0, _flagTop = 26.0, _plotTop = 58.0, _bottomH = 24.0;

  void _label(
    Canvas c,
    String s,
    Offset o, {
    Color? color,
    double size = 10,
    FontWeight? weight,
    double? maxWidth,
    bool center = false,
    bool right = false,
  }) {
    final tp = TextPainter(
      text: TextSpan(
        text: s,
        style: TextStyle(color: color ?? muted, fontSize: size, fontWeight: weight),
      ),
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )..layout(maxWidth: maxWidth ?? double.infinity);
    tp.paint(c, Offset(center ? o.dx - tp.width / 2 : (right ? o.dx - tp.width : o.dx), o.dy));
  }

  void _dashed(Canvas c, Path path, Paint paint, {double dash = 6, double gap = 4}) {
    for (final m in path.computeMetrics()) {
      var d = 0.0;
      while (d < m.length) {
        c.drawPath(m.extractPath(d, math.min(d + dash, m.length)), paint);
        d += dash + gap;
      }
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    final n = weeks.length;
    if (n == 0 || size.width <= 2 * pad) return;
    final plotL = pad, plotR = size.width - pad, plotB = size.height - _bottomH;
    final ww = (plotR - plotL) / n;
    double xc(int i) => plotL + (i + 0.5) * ww;

    double maxT = 100, maxC = 40;
    for (final w in weeks) {
      maxT = math.max(
        maxT,
        math.max(((w['tss_target'] as num?) ?? 0).toDouble(), ((w['actual_tss'] as num?) ?? 0).toDouble()),
      );
      maxC = math.max(maxC, ((w['ctl'] as num?) ?? 0).toDouble());
    }
    maxT *= 1.15;
    maxC *= 1.2;
    double yT(double v) => plotB - v / maxT * (plotB - _plotTop);
    double yC(double v) => plotB - v / maxC * (plotB - _plotTop);

    // Auswahl der Woche
    if (selected >= 0 && selected < n) {
      canvas.drawRect(
        Rect.fromLTRB(plotL + selected * ww, _phaseH + 4, plotL + (selected + 1) * ww, plotB),
        Paint()..color = text.withValues(alpha: 0.06),
      );
    }

    // Gitter und Achsen: TSS links, CTL rechts
    final gp = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (var k = 0; k <= 4; k++) {
      final y = plotB - (plotB - _plotTop) * k / 4;
      canvas.drawLine(Offset(plotL, y), Offset(plotR, y), gp);
      _label(canvas, '${(maxT * k / 4).round()}', Offset(plotL - 6, y - 6), right: true);
      _label(canvas, '${(maxC * k / 4).round()}', Offset(plotR + 6, y - 6), color: AppColors.ctl);
    }
    _label(canvas, 'TSS', Offset(plotL - 6, _plotTop - 22), right: true, weight: FontWeight.w700);
    _label(canvas, 'CTL', Offset(plotR + 6, _plotTop - 22), color: AppColors.ctl, weight: FontWeight.w700);

    // Phasenband: aufeinanderfolgende Wochen gleicher Phase zu einem Block
    var i = 0;
    while (i < n) {
      final ph = weeks[i]['phase'] as String?;
      var j = i;
      while (j + 1 < n && weeks[j + 1]['phase'] == ph) {
        j++;
      }
      if (ph != null) {
        final r = RRect.fromRectAndRadius(
          Rect.fromLTRB(plotL + i * ww + 0.5, 0, plotL + (j + 1) * ww - 0.5, _phaseH),
          const Radius.circular(5),
        );
        canvas.drawRRect(r, Paint()..color = Phases.color(ph).withValues(alpha: 0.9));
        if ((j - i + 1) * ww > 52) {
          _label(
            canvas,
            Phases.label(ph),
            Offset(plotL + (i + (j - i + 1) / 2) * ww, 4),
            color: Colors.white,
            weight: FontWeight.w800,
            center: true,
            maxWidth: (j - i + 1) * ww - 6,
          );
        }
      }
      i = j + 1;
    }

    // Wochenziele (blass) und gefahrene TSS (gruen)
    for (var k = 0; k < n; k++) {
      final w = weeks[k];
      final ph = w['phase'] as String?;
      final target = (w['tss_target'] as num?)?.toDouble();
      if (ph != null && target != null) {
        final rect = Rect.fromLTRB(xc(k) - ww * 0.38, yT(target), xc(k) + ww * 0.38, plotB);
        final rr = RRect.fromRectAndCorners(
          rect,
          topLeft: const Radius.circular(3),
          topRight: const Radius.circular(3),
        );
        final recovery = w['recovery'] == true;
        canvas.drawRRect(rr, Paint()..color = Phases.color(ph).withValues(alpha: recovery ? 0.14 : 0.32));
        if (recovery) {
          canvas.drawRRect(
            rr,
            Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = 1
              ..color = Phases.color(ph).withValues(alpha: 0.7),
          );
        }
      }
      final actual = ((w['actual_tss'] as num?) ?? 0).toDouble();
      if (actual > 0) {
        final rect = Rect.fromLTRB(xc(k) - ww * 0.2, yT(actual), xc(k) + ww * 0.2, plotB);
        canvas.drawRRect(
          RRect.fromRectAndCorners(rect, topLeft: const Radius.circular(2), topRight: const Radius.circular(2)),
          Paint()..color = AppColors.completed,
        );
      }
    }

    // Fitness (CTL): durchgezogen fuer Ist, gestrichelt fuer die Prognose
    final solid = Path(), dashed = Path();
    Offset? prev;
    bool? prevProjected;
    for (var k = 0; k < n; k++) {
      final ctl = (weeks[k]['ctl'] as num?)?.toDouble();
      if (ctl == null) {
        prev = null;
        continue;
      }
      final p = Offset(xc(k), yC(ctl));
      final projected = weeks[k]['projected'] == true;
      if (prev != null) {
        final target = projected ? dashed : solid;
        target.moveTo(prev.dx, prev.dy);
        target.lineTo(p.dx, p.dy);
      }
      prev = p;
      prevProjected = projected;
    }
    final line = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..color = AppColors.ctl;
    canvas.drawPath(solid, line);
    _dashed(canvas, dashed, line..strokeWidth = 2.2);
    if (prev != null && prevProjected != null) {
      canvas.drawCircle(prev, 3.5, Paint()..color = AppColors.ctl);
    }

    // Heute
    if (currentIndex >= 0) {
      final now = DateTime.now();
      final x = plotL + (currentIndex + (now.weekday - 1 + now.hour / 24) / 7) * ww;
      final tp = Paint()
        ..color = primary
        ..strokeWidth = 1.4;
      for (var y = _phaseH + 4; y < plotB; y += 7) {
        canvas.drawLine(Offset(x, y), Offset(x, math.min(y + 4, plotB)), tp);
      }
      _label(
        canvas,
        'Heute',
        Offset(x, _phaseH + 4 + 14 + 2),
        color: primary,
        weight: FontWeight.w800,
        size: 9,
        center: true,
      );
    }

    // Events: Linie und Flagge mit Prioritaet
    final first = DateTime.parse(weeks.first['week_start'] as String);
    for (final e in events) {
      final date = DateTime.parse(e['date'] as String);
      final days = DateTime(
        date.year,
        date.month,
        date.day,
      ).difference(DateTime(first.year, first.month, first.day)).inDays;
      if (days < 0 || days >= n * 7) continue;
      final x = plotL + (days + 0.5) / 7 * ww;
      final color = EventPriority.color(e['priority'] as String);
      canvas.drawLine(
        Offset(x, _flagTop + 18),
        Offset(x, plotB),
        Paint()
          ..color = color.withValues(alpha: 0.55)
          ..strokeWidth = 1.4,
      );
      final box = RRect.fromRectAndRadius(
        Rect.fromCenter(center: Offset(x, _flagTop + 9), width: 18, height: 18),
        const Radius.circular(5),
      );
      canvas.drawRRect(box, Paint()..color = color);
      _label(
        canvas,
        e['priority'] as String,
        Offset(x, _flagTop + 4),
        color: Colors.white,
        weight: FontWeight.w800,
        center: true,
        size: 11,
      );
    }

    // Monate unten
    for (var k = 0; k < n; k++) {
      final d = DateTime.parse(weeks[k]['week_start'] as String);
      final isFirst = k == 0 || DateTime.parse(weeks[k - 1]['week_start'] as String).month != d.month;
      if (isFirst) {
        canvas.drawLine(Offset(plotL + k * ww, plotB), Offset(plotL + k * ww, plotB + 5), gp);
        _label(
          canvas,
          DateFormat(d.month == 1 ? 'MMM yy' : 'MMM', 'de').format(d),
          Offset(plotL + k * ww + 3, plotB + 7),
        );
      }
    }
  }

  @override
  bool shouldRepaint(SeasonPainter old) =>
      old.weeks != weeks ||
      old.events != events ||
      old.selected != selected ||
      old.currentIndex != currentIndex ||
      old.grid != grid ||
      old.text != text;
}

// ------------------------------------------------------- Bearbeiten: Woche ---

Future<void> showWeekSheet(BuildContext context, Json week) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (_) => _WeekSheet(week: week),
);

class _WeekSheet extends ConsumerStatefulWidget {
  const _WeekSheet({required this.week});
  final Json week;

  @override
  ConsumerState<_WeekSheet> createState() => _WeekSheetState();
}

class _WeekSheetState extends ConsumerState<_WeekSheet> {
  late String _phase = (widget.week['phase'] as String?) ?? 'base';
  late bool _recovery = widget.week['recovery'] == true;
  late final _tss = TextEditingController(
    text: widget.week['tss_target'] == null ? '' : (widget.week['tss_target'] as num).round().toString(),
  );
  late final _hours = TextEditingController(
    text: widget.week['hours_target'] == null ? '' : '${widget.week['hours_target']}',
  );
  late final _note = TextEditingController(text: (widget.week['note'] as String?) ?? '');
  bool _busy = false;
  String? _error;

  bool get _exists => widget.week['phase'] != null;

  @override
  void dispose() {
    _tss.dispose();
    _hours.dispose();
    _note.dispose();
    super.dispose();
  }

  double? _num(TextEditingController c) => double.tryParse(c.text.trim().replaceAll(',', '.'));

  Future<void> _save() async {
    final tss = _num(_tss);
    if (tss == null) return setState(() => _error = 'Bitte ein Wochenziel in TSS eingeben');
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(apiProvider)
          .dio
          .put(
            '/atp/weeks',
            data: {
              'weeks': [
                {
                  'week_start': widget.week['week_start'],
                  'phase': _phase,
                  'tss_target': tss,
                  'hours_target': _num(_hours),
                  'recovery': _recovery,
                  'note': _note.text.trim().isEmpty ? null : _note.text.trim(),
                },
              ],
            },
          );
      ref.invalidate(atpProvider);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    setState(() => _busy = true);
    try {
      final d = widget.week['week_start'] as String;
      await ref.read(apiProvider).dio.delete('/atp/weeks', queryParameters: {'start': d, 'end': d});
      ref.invalidate(atpProvider);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final start = DateTime.parse(widget.week['week_start'] as String);
    return Padding(
      padding: EdgeInsets.fromLTRB(Gap.xl, 0, Gap.xl, Gap.xl + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'KW ${isoWeek(start)} · ab ${DateFormat('d. MMMM yyyy', 'de').format(start)}',
              style: t.textTheme.titleLarge,
            ),
            const SizedBox(height: Gap.lg),
            Text('Phase', style: t.textTheme.labelLarge),
            const SizedBox(height: Gap.sm),
            Wrap(
              spacing: Gap.sm,
              runSpacing: Gap.sm,
              children: [
                for (final k in Phases.all.keys)
                  ChoiceChip(
                    label: Text(Phases.label(k)),
                    selected: _phase == k,
                    selectedColor: Phases.color(k).withValues(alpha: 0.25),
                    side: BorderSide(color: _phase == k ? Phases.color(k) : t.colorScheme.outlineVariant),
                    onSelected: (_) => setState(() => _phase = k),
                  ),
              ],
            ),
            const SizedBox(height: Gap.lg),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _tss,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Wochenziel',
                      suffixText: 'TSS',
                      prefixIcon: Icon(Icons.fitness_center_rounded),
                    ),
                  ),
                ),
                const SizedBox(width: Gap.md),
                Expanded(
                  child: TextField(
                    controller: _hours,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Stunden',
                      suffixText: 'h',
                      prefixIcon: Icon(Icons.schedule_rounded),
                    ),
                  ),
                ),
              ],
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Entlastungswoche'),
              value: _recovery,
              onChanged: (v) => setState(() => _recovery = v),
            ),
            TextField(
              controller: _note,
              maxLength: 200,
              decoration: const InputDecoration(labelText: 'Schwerpunkt (optional)'),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: Gap.sm),
                child: Text(_error!, style: TextStyle(color: t.colorScheme.error)),
              ),
            const SizedBox(height: Gap.sm),
            Row(
              children: [
                if (_exists)
                  TextButton(
                    style: TextButton.styleFrom(foregroundColor: t.colorScheme.error),
                    onPressed: _busy ? null : _delete,
                    child: const Text('Woche entfernen'),
                  ),
                const Spacer(),
                TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Abbrechen')),
                const SizedBox(width: Gap.sm),
                FilledButton(onPressed: _busy ? null : _save, child: const Text('Speichern')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ----------------------------------------------------- Bearbeiten: Event ---

Future<void> showEventDialog(BuildContext context, WidgetRef ref, {Json? event}) => showDialog<void>(
  context: context,
  builder: (_) => _EventDialog(event: event),
);

class _EventDialog extends ConsumerStatefulWidget {
  const _EventDialog({this.event});
  final Json? event;

  @override
  ConsumerState<_EventDialog> createState() => _EventDialogState();
}

class _EventDialogState extends ConsumerState<_EventDialog> {
  late final _name = TextEditingController(text: (widget.event?['name'] as String?) ?? '');
  late final _notes = TextEditingController(text: (widget.event?['notes'] as String?) ?? '');
  late DateTime _date = widget.event == null
      ? DateTime.now().add(const Duration(days: 60))
      : DateTime.parse(widget.event!['date'] as String);
  late String _priority = (widget.event?['priority'] as String?) ?? 'A';
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty) return setState(() => _error = 'Bitte einen Namen eingeben');
    setState(() {
      _busy = true;
      _error = null;
    });
    final body = {
      'name': _name.text.trim(),
      'date': isoDay(_date),
      'priority': _priority,
      'notes': _notes.text.trim().isEmpty ? null : _notes.text.trim(),
    };
    try {
      final dio = ref.read(apiProvider).dio;
      await (widget.event == null
          ? dio.post('/atp/events', data: body)
          : dio.put('/atp/events/${widget.event!['id']}', data: body));
      ref.invalidate(atpProvider);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return AlertDialog(
      title: Text(widget.event == null ? 'Neues Event' : 'Event bearbeiten'),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _name,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Name', prefixIcon: Icon(Icons.flag_outlined)),
              ),
              const SizedBox(height: Gap.md),
              InkWell(
                borderRadius: BorderRadius.circular(Radii.md),
                onTap: () async {
                  final d = await showDatePicker(
                    context: context,
                    initialDate: _date,
                    firstDate: DateTime(2000),
                    lastDate: DateTime(2100),
                  );
                  if (d != null) setState(() => _date = d);
                },
                child: InputDecorator(
                  decoration: const InputDecoration(labelText: 'Datum', prefixIcon: Icon(Icons.event_rounded)),
                  child: Text(DateFormat('EEEE, d. MMMM yyyy', 'de').format(_date)),
                ),
              ),
              const SizedBox(height: Gap.lg),
              Text('Priorität', style: t.textTheme.labelLarge),
              const SizedBox(height: Gap.sm),
              SegmentedButton<String>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: 'A', label: Text('A · Hauptziel')),
                  ButtonSegment(value: 'B', label: Text('B')),
                  ButtonSegment(value: 'C', label: Text('C')),
                ],
                selected: {_priority},
                onSelectionChanged: (s) => setState(() => _priority = s.first),
              ),
              const SizedBox(height: Gap.md),
              TextField(
                controller: _notes,
                maxLength: 300,
                maxLines: 2,
                decoration: const InputDecoration(labelText: 'Notizen (optional)'),
              ),
              if (_error != null) Text(_error!, style: TextStyle(color: t.colorScheme.error)),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Abbrechen')),
        FilledButton(onPressed: _busy ? null : _save, child: const Text('Speichern')),
      ],
    );
  }
}
