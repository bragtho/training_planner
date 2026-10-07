import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

const _completedColor = AppColors.completed;

DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

class CalendarScreen extends ConsumerStatefulWidget {
  const CalendarScreen({super.key});

  @override
  ConsumerState<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends ConsumerState<CalendarScreen> {
  late DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);

  /// Raster beginnt am Montag der Woche, in die der Monatserste faellt.
  DateTime get _gridStart => _month.subtract(Duration(days: _month.weekday - 1));
  int get _weeks {
    final lead = _month.weekday - 1;
    final days = DateUtils.getDaysInMonth(_month.year, _month.month);
    return ((lead + days) / 7).ceil();
  }

  void _shift(int months) => setState(() => _month = DateTime(_month.year, _month.month + months));

  @override
  Widget build(BuildContext context) {
    final start = _gridStart;
    final end = DateTime(start.year, start.month, start.day + _weeks * 7 - 1);
    final data = ref.watch(calendarProvider((start, end)));
    final value = data.value;

    // Saisonplan (ATP): Phase je Woche (Montag -> Woche) und Events je Tag
    final atp = ref.watch(atpProvider((start, end))).value;
    final atpWeeks = <String, Json>{};
    final atpEvents = <String, List<Json>>{};
    if (atp != null) {
      for (final w in atp['weeks'] as List) {
        final m = Json.from(w as Map);
        if (m['phase'] != null) atpWeeks[m['week_start'] as String] = m;
      }
      for (final e in atp['events'] as List) {
        final m = Json.from(e as Map);
        atpEvents.putIfAbsent(m['date'] as String, () => []).add(m);
      }
    }

    final workouts = <String, List<Json>>{};
    final loose = <String, List<Json>>{}; // Aktivitaeten ohne geplantes Training
    final matched = <int>{};
    final tssByDay = <String, double>{};
    if (value != null) {
      for (final w in value['workouts'] as List) {
        final m = Json.from(w as Map);
        workouts.putIfAbsent(m['date'] as String, () => []).add(m);
        if (m['activity_id'] != null) matched.add(m['activity_id'] as int);
      }
      for (final a in value['activities'] as List) {
        final m = Json.from(a as Map);
        final day = (m['start_time'] as String).substring(0, 10);
        tssByDay[day] = (tssByDay[day] ?? 0) + ((m['tss'] as num?) ?? 0).toDouble();
        if (!matched.contains(m['id'])) loose.putIfAbsent(day, () => []).add(m);
      }
    }

    final now = DateTime.now();
    final isCurrent = _month.year == now.year && _month.month == now.month;
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/workout/new?date=${isoDay(DateTime.now())}'),
        icon: const Icon(Icons.add_rounded),
        label: const Text('Training'),
      ),
      body: SafeArea(
        bottom: false,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: MediaQuery.sizeOf(context).width < compactWidth ? Gap.md : Gap.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Builder(builder: (context) {
                final phone = MediaQuery.sizeOf(context).width < compactWidth;
                final loading = data.isLoading
                    ? const Padding(
                        padding: EdgeInsets.only(right: Gap.md),
                        child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                      )
                    : null;
                final season = OutlinedButton.icon(
                  onPressed: () => context.push('/season'),
                  icon: const Icon(Icons.timeline_rounded, size: 18),
                  label: Text(phone ? 'Saison' : 'Saisonplan'),
                );
                final prev = IconButton.outlined(
                  tooltip: 'Voriger Monat',
                  onPressed: () => _shift(-1),
                  icon: const Icon(Icons.chevron_left_rounded),
                );
                final today = OutlinedButton(
                  onPressed: isCurrent ? null : () => setState(() => _month = DateTime(now.year, now.month)),
                  child: const Text('Heute'),
                );
                final next = IconButton.outlined(
                  tooltip: 'Nächster Monat',
                  onPressed: () => _shift(1),
                  icon: const Icon(Icons.chevron_right_rounded),
                );
                final title = DateFormat('MMMM yyyy', 'de').format(_month);
                if (!phone) {
                  return PageHeader(
                    subtitle: 'Kalender',
                    title: title,
                    trailing: [
                      ?loading,
                      season,
                      const SizedBox(width: Gap.sm),
                      prev,
                      const SizedBox(width: Gap.xs),
                      today,
                      const SizedBox(width: Gap.xs),
                      next,
                    ],
                  );
                }
                // Handy: Monat in einer Zeile, Bedienelemente darunter
                return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  PageHeader(subtitle: 'Kalender', title: title, trailing: [?loading]),
                  Padding(
                    padding: const EdgeInsets.only(bottom: Gap.md),
                    child: Row(children: [
                      season,
                      const Spacer(),
                      prev,
                      const SizedBox(width: Gap.xs),
                      today,
                      const SizedBox(width: Gap.xs),
                      next,
                    ]),
                  ),
                ]);
              }),
              _Legend(phases: {for (final w in atpWeeks.values) w['phase'] as String}),
              const SizedBox(height: Gap.md),
              Expanded(
                child: data.hasError && value == null
                    ? Center(
                        child: StatusMessage.error(
                          errorMessage(data.error!),
                          onRetry: () => ref.invalidate(calendarProvider),
                        ),
                      )
                    : LayoutBuilder(
                        builder: (context, c) {
                          final narrow = c.maxWidth < 600;
                          final line = Theme.of(context).colorScheme.outlineVariant;
                          return Card(
                            clipBehavior: Clip.antiAlias,
                            child: Column(
                              children: [
                                _WeekdayHeader(narrow: narrow),
                                Divider(height: 1, color: line),
                                for (var w = 0; w < _weeks; w++)
                                  Expanded(
                                    child: Container(
                                      decoration: BoxDecoration(
                                        border: w == 0 ? null : Border(top: BorderSide(color: line)),
                                      ),
                                      child: Row(
                                        crossAxisAlignment: CrossAxisAlignment.stretch,
                                        children: [
                                          for (var d = 0; d < 7; d++)
                                            Expanded(
                                              child: _DayCell(
                                                phase:
                                                    atpWeeks[isoDay(
                                                          DateTime(start.year, start.month, start.day + w * 7),
                                                        )]?['phase']
                                                        as String?,
                                                events:
                                                    atpEvents[isoDay(
                                                      DateTime(start.year, start.month, start.day + w * 7 + d),
                                                    )] ??
                                                    const [],
                                                day: DateTime(start.year, start.month, start.day + w * 7 + d),
                                                inMonth:
                                                    DateTime(start.year, start.month, start.day + w * 7 + d).month ==
                                                    _month.month,
                                                workouts: workouts,
                                                loose: loose,
                                                narrow: narrow,
                                              ),
                                            ),
                                          _WeekTotal(
                                            days: [
                                              for (var d = 0; d < 7; d++)
                                                isoDay(DateTime(start.year, start.month, start.day + w * 7 + d)),
                                            ],
                                            workouts: workouts,
                                            tssByDay: tssByDay,
                                            atpWeek:
                                                atpWeeks[isoDay(DateTime(start.year, start.month, start.day + w * 7))],
                                            narrow: narrow,
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          );
                        },
                      ),
              ),
              const SizedBox(height: 88), // Platz fuer den FAB
            ],
          ),
        ),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({required this.phases});
  final Set<String> phases; // Phasen, die im sichtbaren Zeitraum vorkommen

  @override
  Widget build(BuildContext context) {
    final s = Theme.of(context).colorScheme;
    return Wrap(
      spacing: Gap.lg,
      runSpacing: Gap.xs,
      children: [
        LegendDot(label: 'Geplant', color: s.primary),
        const LegendDot(label: 'Absolviert', color: _completedColor),
        LegendDot(label: 'Verpasst', color: s.error),
        LegendDot(label: 'Ausgelassen', color: s.outline),
        for (final k in Phases.all.keys)
          if (phases.contains(k)) LegendDot(label: Phases.label(k), color: Phases.color(k)),
      ],
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader({required this.narrow});
  final bool narrow;

  @override
  Widget build(BuildContext context) {
    const names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
    final t = Theme.of(context);
    final style = t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant, fontWeight: FontWeight.w700);
    return Container(
      color: t.colorScheme.surfaceContainer.withValues(alpha: 0.5),
      padding: const EdgeInsets.symmetric(vertical: Gap.sm),
      child: Row(
        children: [
          for (final n in names)
            Expanded(
              child: Center(child: Text(n, style: style)),
            ),
          SizedBox(
            width: narrow ? 44 : 84,
            child: Center(child: Text(narrow ? 'TSS' : 'Woche', style: style)),
          ),
        ],
      ),
    );
  }
}

Color _statusColor(BuildContext context, String status) {
  final s = Theme.of(context).colorScheme;
  return switch (status) {
    'completed' => _completedColor,
    'missed' => s.error,
    'skipped' => s.outline,
    _ => s.primary,
  };
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.phase,
    required this.events,
    required this.day,
    required this.inMonth,
    required this.workouts,
    required this.loose,
    required this.narrow,
  });
  final String? phase; // Trainingsphase der Woche (Saisonplan) oder null
  final List<Json> events;
  final DateTime day;
  final bool inMonth;
  final Map<String, List<Json>> workouts;
  final Map<String, List<Json>> loose;
  final bool narrow;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final key = isoDay(day);
    final isToday = _day(DateTime.now()) == day;
    final chips = [
      for (final w in workouts[key] ?? const <Json>[])
        _Chip(
          color: _statusColor(context, w['status'] as String),
          label: w['title'] as String,
          tss: (w['status'] == 'completed' ? w['actual_tss'] : w['planned_tss']) as num?,
          strike: w['status'] == 'skipped',
          check: w['status'] == 'completed',
          narrow: narrow,
        ),
      for (final a in loose[key] ?? const <Json>[])
        _Chip(
          color: _completedColor,
          label: a['name'] as String? ?? 'Fahrt',
          tss: a['tss'] as num?,
          check: true,
          outline: true,
          narrow: narrow,
        ),
    ];
    final eventChips = [for (final e in events) _EventChip(event: e, narrow: narrow)];
    return Material(
      // Phase schwach hinterlegt; Tage ausserhalb des Monats etwas blasser
      color: phase != null
          ? Phases.color(phase).withValues(alpha: inMonth ? 0.07 : 0.035)
          : inMonth
          ? Colors.transparent
          : t.colorScheme.surfaceContainer.withValues(alpha: 0.45),
      child: InkWell(
        onTap: () => _showDay(context),
        child: Container(
          decoration: BoxDecoration(
            border: Border(right: BorderSide(color: t.colorScheme.outlineVariant)),
          ),
          padding: EdgeInsets.all(narrow ? 3 : 6),
          child: SingleChildScrollView(
            physics: const NeverScrollableScrollPhysics(),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: narrow ? Alignment.center : Alignment.centerLeft,
                  child: Container(
                    width: 24,
                    height: 24,
                    alignment: Alignment.center,
                    decoration: isToday ? BoxDecoration(color: t.colorScheme.primary, shape: BoxShape.circle) : null,
                    child: Text(
                      '${day.day}',
                      style: t.textTheme.labelMedium?.copyWith(
                        fontWeight: isToday ? FontWeight.w800 : FontWeight.w600,
                        color: isToday
                            ? t.colorScheme.onPrimary
                            : inMonth
                            ? t.colorScheme.onSurface
                            : t.colorScheme.outline,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 2),
                if (narrow)
                  Wrap(alignment: WrapAlignment.center, spacing: 3, runSpacing: 3, children: [...eventChips, ...chips])
                else ...[
                  ...eventChips,
                  ...chips,
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showDay(BuildContext context) {
    final key = isoDay(day);
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (ctx) =>
          _DaySheet(day: day, workouts: workouts[key] ?? const [], activities: loose[key] ?? const [], parent: context),
    );
  }
}

/// Eintrag im Tagesfeld; auf schmalen Displays nur ein farbiger Punkt.
class _Chip extends StatelessWidget {
  const _Chip({
    required this.color,
    required this.label,
    required this.tss,
    this.strike = false,
    this.check = false,
    this.outline = false,
    this.narrow = false,
  });
  final Color color;
  final String label;
  final num? tss;
  final bool strike;
  final bool check;
  final bool outline;
  final bool narrow;

  @override
  Widget build(BuildContext context) {
    if (narrow) {
      return Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(
          color: outline ? null : color,
          shape: BoxShape.circle,
          border: Border.all(color: color, width: 1.6),
        ),
      );
    }
    final t = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(top: 3),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: outline ? null : color.withValues(alpha: 0.14),
        border: outline ? Border.all(color: color.withValues(alpha: 0.5)) : null,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        children: [
          if (check) ...[Icon(Icons.check_rounded, size: 12, color: color), const SizedBox(width: 2)],
          Expanded(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
              style: t.textTheme.labelSmall?.copyWith(
                fontWeight: FontWeight.w600,
                decoration: strike ? TextDecoration.lineThrough : null,
              ),
            ),
          ),
          if (tss != null)
            Text(
              ' ${tss!.round()}',
              style: t.textTheme.labelSmall?.copyWith(color: color, fontWeight: FontWeight.w800),
            ),
        ],
      ),
    );
  }
}

/// Event (Wettkampf) im Tagesfeld: Flagge in der Prioritaetsfarbe.
class _EventChip extends StatelessWidget {
  const _EventChip({required this.event, required this.narrow});
  final Json event;
  final bool narrow;

  @override
  Widget build(BuildContext context) {
    final c = EventPriority.color(event['priority'] as String);
    if (narrow) return Icon(Icons.flag_rounded, size: 12, color: c);
    return Container(
      margin: const EdgeInsets.only(top: 3),
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 3),
      decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(6)),
      child: Row(
        children: [
          const Icon(Icons.flag_rounded, size: 12, color: Colors.white),
          const SizedBox(width: 3),
          Expanded(
            child: Text(
              '${event['priority']} · ${event['name']}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }
}

/// Wochensumme: gefahrene gegenueber geplanter TSS mit Fortschrittsbalken.
class _WeekTotal extends StatelessWidget {
  const _WeekTotal({
    required this.days,
    required this.workouts,
    required this.tssByDay,
    required this.atpWeek,
    required this.narrow,
  });
  final Json? atpWeek; // Wochenziel aus dem Saisonplan
  final List<String> days;
  final Map<String, List<Json>> workouts;
  final Map<String, double> tssByDay;
  final bool narrow;

  @override
  Widget build(BuildContext context) {
    var planned = 0.0, actual = 0.0;
    for (final d in days) {
      actual += tssByDay[d] ?? 0;
      for (final w in workouts[d] ?? const <Json>[]) {
        if (w['status'] != 'skipped') planned += ((w['planned_tss'] as num?) ?? 0).toDouble();
      }
    }
    final t = Theme.of(context);
    final muted = t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant);
    final target = (atpWeek?['tss_target'] as num?)?.toDouble();
    final phase = atpWeek?['phase'] as String?;
    final goal = target ?? planned; // Fortschritt gegen das Wochenziel des Saisonplans, sonst gegen die Planung
    return Container(
      width: narrow ? 44 : 84,
      color: t.colorScheme.surfaceContainer.withValues(alpha: 0.5),
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (phase != null && !narrow)
            Text(
              Phases.label(phase) + (atpWeek?['recovery'] == true ? ' · E' : ''),
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: t.textTheme.labelSmall?.copyWith(color: Phases.color(phase), fontWeight: FontWeight.w800),
            ),
          Text(
            '${actual.round()}',
            textAlign: TextAlign.center,
            style: t.textTheme.titleSmall?.copyWith(color: _completedColor, fontWeight: FontWeight.w800),
          ),
          if (target != null)
            Text(narrow ? '/${target.round()}' : 'Ziel ${target.round()}', textAlign: TextAlign.center, style: muted)
          else if (planned > 0)
            Text(narrow ? '/${planned.round()}' : 'von ${planned.round()}', textAlign: TextAlign.center, style: muted),
          if (goal > 0) ...[
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(Radii.pill),
              child: LinearProgressIndicator(
                value: (actual / goal).clamp(0.0, 1.0),
                minHeight: 4,
                color: phase != null ? Phases.color(phase) : _completedColor,
                backgroundColor: t.colorScheme.outlineVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _DaySheet extends StatelessWidget {
  const _DaySheet({required this.day, required this.workouts, required this.activities, required this.parent});
  final DateTime day;
  final List<Json> workouts;
  final List<Json> activities;
  final BuildContext parent;

  static const _labels = {
    'planned': 'Geplant',
    'completed': 'Absolviert',
    'missed': 'Verpasst',
    'skipped': 'Ausgelassen',
  };

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    void go(String path) {
      Navigator.pop(context);
      parent.push(path);
    }

    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(Gap.xl, 0, Gap.xl, Gap.xl),
          children: [
            Text(
              DateFormat('EEEE', 'de').format(day).toUpperCase(),
              style: t.textTheme.labelMedium?.copyWith(
                color: t.colorScheme.primary,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.1,
              ),
            ),
            Text(DateFormat('d. MMMM yyyy', 'de').format(day), style: t.textTheme.headlineSmall),
            const SizedBox(height: Gap.lg),
            if (workouts.isEmpty && activities.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: Gap.lg),
                child: Text(
                  'Für diesen Tag ist nichts eingetragen.',
                  style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
                ),
              ),
            for (final w in workouts) ...[
              _SheetTile(
                color: _statusColor(context, w['status'] as String),
                icon: w['status'] == 'completed' ? Icons.check_circle_rounded : Icons.event_note_rounded,
                title: w['title'] as String,
                status: _labels[w['status']] ?? '',
                details: [
                  if (w['planned_duration_s'] != null) formatDuration(w['planned_duration_s'] as num),
                  if (w['planned_tss'] != null) '${(w['planned_tss'] as num).round()} TSS geplant',
                  if (w['actual_tss'] != null) '${(w['actual_tss'] as num).round()} TSS gefahren',
                ],
                onTap: () => go('/workout/${w['id']}'),
                trailing: w['activity_id'] != null
                    ? IconButton(
                        tooltip: 'Aktivität öffnen',
                        icon: const Icon(Icons.open_in_new_rounded),
                        onPressed: () => go('/activity/${w['activity_id']}'),
                      )
                    : null,
              ),
              const SizedBox(height: Gap.sm),
            ],
            for (final a in activities) ...[
              _SheetTile(
                color: _completedColor,
                icon: Icons.directions_bike_rounded,
                title: a['name'] as String? ?? 'Fahrt',
                status: 'Ungeplant',
                details: [
                  formatDuration(a['duration_s'] as num),
                  if (a['tss'] != null) '${(a['tss'] as num).round()} TSS',
                ],
                onTap: () => go('/activity/${a['id']}'),
              ),
              const SizedBox(height: Gap.sm),
            ],
            const SizedBox(height: Gap.sm),
            FilledButton.icon(
              onPressed: () => go('/workout/new?date=${isoDay(day)}'),
              icon: const Icon(Icons.add_rounded),
              label: const Text('Training hinzufügen'),
            ),
          ],
        ),
      ),
    );
  }
}

class _SheetTile extends StatelessWidget {
  const _SheetTile({
    required this.color,
    required this.icon,
    required this.title,
    required this.status,
    required this.details,
    required this.onTap,
    this.trailing,
  });
  final Color color;
  final IconData icon;
  final String title;
  final String status;
  final List<String> details;
  final VoidCallback onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return SurfaceCard(
      padding: const EdgeInsets.all(Gap.md),
      onTap: onTap,
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(Radii.md),
            ),
            child: Icon(icon, color: color),
          ),
          const SizedBox(width: Gap.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(title, style: t.textTheme.titleSmall, overflow: TextOverflow.ellipsis),
                    ),
                    const SizedBox(width: Gap.sm),
                    Pill(label: status, color: color),
                  ],
                ),
                if (details.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    details.join(' · '),
                    style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant),
                  ),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}
