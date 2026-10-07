import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

/// Diese Woche auf einen Blick: Ist gegen Soll (Wochenziel aus dem Saisonplan, sonst Summe der geplanten Trainings),
/// Phase, Zeit, Distanz, Fahrten und das naechste Ziel. Ersetzt Wochen- und Saisonplan-Karte.
class WeekCard extends ConsumerWidget {
  const WeekCard({super.key, this.now});

  /// Fuer Tests: festes "Jetzt".
  final DateTime? now;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final n = now ?? DateTime.now();
    final monday = mondayOf(DateTime(n.year, n.month, n.day));
    final sunday = monday.add(const Duration(days: 6));
    final week = ref.watch(calendarProvider((monday, sunday))).value;
    final atp = ref.watch(atpProvider(seasonRange(n))).value;
    if (week == null) return const LoadingBlock(height: 170);

    var planned = 0.0, done = 0.0, secs = 0.0, meters = 0.0, rides = 0;
    for (final w in week['workouts'] as List) {
      if ((w as Map)['status'] != 'skipped') planned += ((w['planned_tss'] as num?) ?? 0).toDouble();
    }
    for (final a in week['activities'] as List) {
      done += (((a as Map)['tss'] as num?) ?? 0).toDouble();
      secs += (a['duration_s'] as num).toDouble();
      meters += (a['distance_m'] as num).toDouble();
      rides++;
    }

    final weeks = [for (final w in (atp?['weeks'] as List? ?? const [])) Json.from(w as Map)];
    final events = [for (final e in (atp?['events'] as List? ?? const [])) Json.from(e as Map)]
        .where((e) => (e['days_to_go'] as int) >= 0)
        .toList();
    final cur = weeks.where((w) => w['week_start'] == isoDay(monday) && w['phase'] != null).firstOrNull;
    final nextEvent = events.where((e) => e['priority'] == 'A').firstOrNull ?? events.firstOrNull;
    final phase = cur?['phase'] as String?;
    final target = (cur?['tss_target'] as num?)?.toDouble() ?? (planned > 0 ? planned : null);
    final progress = target != null && target > 0 ? (done / target).clamp(0.0, 1.0) : (done > 0 ? 1.0 : 0.0);
    final color = phase != null ? Phases.color(phase) : t.colorScheme.primary;
    final hasPlan = weeks.any((w) => w['phase'] != null);

    return SurfaceCard(
      onTap: hasPlan || nextEvent != null ? () => context.push('/season') : null,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Diese Woche', style: t.textTheme.titleMedium),
              Text('${DateFormat('d. MMM', 'de').format(monday)} – ${DateFormat('d. MMM', 'de').format(sunday)}',
                  style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
            ]),
          ),
          if (phase != null) Pill(label: Phases.label(phase), color: color),
          if (cur?['recovery'] == true) ...[
            const SizedBox(width: Gap.sm),
            const Pill(label: 'Entlastung', color: AppColors.completed),
          ],
        ]),
        const SizedBox(height: Gap.md),
        Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
          Text(done.round().toString(), style: t.textTheme.headlineMedium),
          const SizedBox(width: 6),
          Text(target != null ? 'von ${target.round()} TSS' : 'TSS',
              style: t.textTheme.titleSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
          const Spacer(),
          if (target != null && target > 0)
            Text('${(done / target * 100).round()} %', style: t.textTheme.titleSmall?.copyWith(color: color)),
        ]),
        const SizedBox(height: Gap.sm),
        ClipRRect(
          borderRadius: BorderRadius.circular(Radii.pill),
          child: LinearProgressIndicator(
            value: progress,
            minHeight: 10,
            color: color,
            backgroundColor: t.colorScheme.surfaceContainerHigh,
          ),
        ),
        const SizedBox(height: Gap.md),
        Row(children: [
          _MiniStat(icon: Icons.schedule_rounded, value: formatDuration(secs), label: 'Zeit'),
          _MiniStat(icon: Icons.route_rounded, value: formatKm(meters), label: 'Distanz'),
          _MiniStat(icon: Icons.directions_bike_rounded, value: '$rides', label: 'Fahrten'),
        ]),
        if (nextEvent != null) ...[
          const Padding(padding: EdgeInsets.symmetric(vertical: Gap.md), child: Divider()),
          Row(children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: EventPriority.color(nextEvent['priority'] as String),
                borderRadius: BorderRadius.circular(Radii.sm),
              ),
              child: const Icon(Icons.flag_rounded, color: Colors.white, size: 18),
            ),
            const SizedBox(width: Gap.md),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(nextEvent['name'] as String, style: t.textTheme.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                Text(
                  [
                    '${nextEvent['priority']}-Event in ${nextEvent['days_to_go']} Tagen',
                    if (nextEvent['form_tsb'] != null)
                      'Form laut Plan ${(nextEvent['form_tsb'] as num) > 0 ? '+' : ''}${(nextEvent['form_tsb'] as num).round()}',
                  ].join(' · '),
                  style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant),
                ),
              ]),
            ),
          ]),
        ] else if (!hasPlan) ...[
          const Padding(padding: EdgeInsets.symmetric(vertical: Gap.sm), child: Divider()),
          InkWell(
            onTap: () => context.push('/season'),
            child: Row(children: [
              Icon(Icons.timeline_rounded, size: 18, color: t.colorScheme.primary),
              const SizedBox(width: Gap.sm),
              Expanded(
                child: Text('Saisonplan anlegen: Nenne dem Coach Deine Events.',
                    style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.primary)),
              ),
            ]),
          ),
        ],
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
