import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/data.dart';

const _completedColor = Color(0xFF2E9E5B);

DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

class CalendarScreen extends ConsumerStatefulWidget {
  const CalendarScreen({super.key});

  @override
  ConsumerState<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends ConsumerState<CalendarScreen> {
  late DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);

  /// Raster beginnt am Montag der Woche, in die der Monatserste faellt.
  DateTime get _gridStart =>
      _month.subtract(Duration(days: _month.weekday - 1));
  int get _weeks {
    final lead = _month.weekday - 1;
    final days = DateUtils.getDaysInMonth(_month.year, _month.month);
    return ((lead + days) / 7).ceil();
  }

  void _shift(int months) =>
      setState(() => _month = DateTime(_month.year, _month.month + months));

  @override
  Widget build(BuildContext context) {
    final start = _gridStart;
    final end = DateTime(start.year, start.month, start.day + _weeks * 7 - 1);
    final data = ref.watch(calendarProvider((start, end)));
    final value = data.value;

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

    final title = DateFormat('MMMM yyyy', 'de').format(_month);
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          IconButton(
              tooltip: 'Voriger Monat',
              onPressed: () => _shift(-1),
              icon: const Icon(Icons.chevron_left)),
          TextButton(
              onPressed: () => setState(() =>
                  _month = DateTime(DateTime.now().year, DateTime.now().month)),
              child: const Text('Heute')),
          IconButton(
              tooltip: 'Nächster Monat',
              onPressed: () => _shift(1),
              icon: const Icon(Icons.chevron_right)),
        ],
        bottom: data.isLoading
            ? const PreferredSize(
                preferredSize: Size.fromHeight(2), child: LinearProgressIndicator())
            : null,
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/workout/new?date=${isoDay(DateTime.now())}'),
        icon: const Icon(Icons.add),
        label: const Text('Training'),
      ),
      body: data.hasError && value == null
          ? Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(errorMessage(data.error!)),
                TextButton(
                    onPressed: () => ref.invalidate(calendarProvider),
                    child: const Text('Erneut versuchen')),
              ]),
            )
          : LayoutBuilder(builder: (context, c) {
              final narrow = c.maxWidth < 600;
              return Column(children: [
                _WeekdayHeader(narrow: narrow),
                for (var w = 0; w < _weeks; w++)
                  Expanded(
                    child: Row(children: [
                      for (var d = 0; d < 7; d++)
                        Expanded(
                          child: _DayCell(
                            day: DateTime(start.year, start.month, start.day + w * 7 + d),
                            inMonth: DateTime(start.year, start.month, start.day + w * 7 + d).month == _month.month,
                            workouts: workouts,
                            loose: loose,
                            narrow: narrow,
                          ),
                        ),
                      _WeekTotal(
                        days: [for (var d = 0; d < 7; d++) isoDay(DateTime(start.year, start.month, start.day + w * 7 + d))],
                        workouts: workouts,
                        tssByDay: tssByDay,
                        narrow: narrow,
                      ),
                    ]),
                  ),
                const SizedBox(height: 80), // Platz fuer den FAB
              ]);
            }),
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader({required this.narrow});
  final bool narrow;

  @override
  Widget build(BuildContext context) {
    const names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
    final style = Theme.of(context).textTheme.labelMedium;
    return Row(children: [
      for (final n in names)
        Expanded(child: Padding(padding: const EdgeInsets.all(6), child: Center(child: Text(n, style: style)))),
      SizedBox(width: narrow ? 44 : 76, child: Center(child: Text('Woche', style: style))),
    ]);
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
    required this.day,
    required this.inMonth,
    required this.workouts,
    required this.loose,
    required this.narrow,
  });
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
    final ws = workouts[key] ?? const [];
    final ls = loose[key] ?? const [];
    return InkWell(
      onTap: () => _showDay(context),
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(color: t.colorScheme.outlineVariant, width: 0.5),
          color: isToday ? t.colorScheme.primaryContainer.withValues(alpha: 0.35) : null,
        ),
        padding: const EdgeInsets.all(3),
        child: SingleChildScrollView(
          physics: const NeverScrollableScrollPhysics(),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('${day.day}',
                style: t.textTheme.labelSmall?.copyWith(
                  fontWeight: isToday ? FontWeight.bold : null,
                  color: inMonth ? null : t.colorScheme.outline,
                )),
            for (final w in ws)
              _Chip(
                color: _statusColor(context, w['status'] as String),
                label: narrow ? '' : w['title'] as String,
                tss: (w['status'] == 'completed' ? w['actual_tss'] : w['planned_tss']) as num?,
                strike: w['status'] == 'skipped',
                check: w['status'] == 'completed',
              ),
            for (final a in ls)
              _Chip(
                color: _completedColor,
                label: narrow ? '' : (a['name'] as String? ?? 'Fahrt'),
                tss: a['tss'] as num?,
                check: true,
                outline: true,
              ),
          ]),
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
      builder: (ctx) => _DaySheet(
        day: day,
        workouts: workouts[key] ?? const [],
        activities: loose[key] ?? const [],
        parent: context,
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({
    required this.color,
    required this.label,
    required this.tss,
    this.strike = false,
    this.check = false,
    this.outline = false,
  });
  final Color color;
  final String label;
  final num? tss;
  final bool strike;
  final bool check;
  final bool outline;

  @override
  Widget build(BuildContext context) {
    final text = [if (label.isNotEmpty) label, if (tss != null) tss!.round().toString()].join(' · ');
    return Container(
      margin: const EdgeInsets.only(top: 2),
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      decoration: BoxDecoration(
        color: outline ? null : color.withValues(alpha: 0.2),
        border: Border(left: BorderSide(color: color, width: 3)),
      ),
      child: Row(children: [
        if (check) Icon(Icons.check, size: 11, color: color),
        Expanded(
          child: Text(
            text.isEmpty ? '–' : text,
            overflow: TextOverflow.ellipsis,
            maxLines: 1,
            style: TextStyle(
              fontSize: 10.5,
              decoration: strike ? TextDecoration.lineThrough : null,
            ),
          ),
        ),
      ]),
    );
  }
}

class _WeekTotal extends StatelessWidget {
  const _WeekTotal({
    required this.days,
    required this.workouts,
    required this.tssByDay,
    required this.narrow,
  });
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
    final t = Theme.of(context).textTheme.labelSmall;
    return SizedBox(
      width: narrow ? 44 : 76,
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Text(narrow ? '${planned.round()}' : 'Plan ${planned.round()}', style: t),
        Text(narrow ? '${actual.round()}' : 'Ist ${actual.round()}',
            style: t?.copyWith(fontWeight: FontWeight.bold, color: _completedColor)),
      ]),
    );
  }
}

class _DaySheet extends StatelessWidget {
  const _DaySheet({
    required this.day,
    required this.workouts,
    required this.activities,
    required this.parent,
  });
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
        child: ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(16, 0, 16, 16), children: [
          Text(DateFormat('EEEE, d. MMMM', 'de').format(day), style: t.textTheme.titleMedium),
          const SizedBox(height: 8),
          if (workouts.isEmpty && activities.isEmpty)
            const Padding(padding: EdgeInsets.symmetric(vertical: 16), child: Text('Nichts geplant.')),
          for (final w in workouts)
            Card(
              child: ListTile(
                leading: Icon(Icons.event_note, color: _statusColor(context, w['status'] as String)),
                title: Text(w['title'] as String),
                subtitle: Text([
                  _labels[w['status']] ?? '',
                  if (w['planned_duration_s'] != null) formatDuration(w['planned_duration_s'] as num),
                  if (w['planned_tss'] != null) '${(w['planned_tss'] as num).round()} TSS geplant',
                  if (w['actual_tss'] != null) '${(w['actual_tss'] as num).round()} TSS gefahren',
                ].where((s) => s.isNotEmpty).join(' · ')),
                trailing: w['activity_id'] != null
                    ? IconButton(
                        tooltip: 'Aktivität öffnen',
                        icon: const Icon(Icons.open_in_new),
                        onPressed: () => go('/activity/${w['activity_id']}'),
                      )
                    : null,
                onTap: () => go('/workout/${w['id']}'),
              ),
            ),
          for (final a in activities)
            Card(
              child: ListTile(
                leading: const Icon(Icons.directions_bike, color: _completedColor),
                title: Text(a['name'] as String? ?? 'Fahrt'),
                subtitle: Text([
                  formatDuration(a['duration_s'] as num),
                  if (a['tss'] != null) '${(a['tss'] as num).round()} TSS',
                ].join(' · ')),
                onTap: () => go('/activity/${a['id']}'),
              ),
            ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: () => go('/workout/new?date=${isoDay(day)}'),
            icon: const Icon(Icons.add),
            label: const Text('Training hinzufügen'),
          ),
        ]),
      ),
    );
  }
}
