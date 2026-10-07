import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

/// Sagt Karten, dass sie auf die Hoehe der Nachbarkarte gestreckt werden; der Inhalt verteilt sich dann (Hauptinhalt oben,
/// Profil oder Knopf unten), statt unten eine Luecke zu lassen.
class StretchScope extends InheritedWidget {
  const StretchScope({super.key, required super.child});

  static bool of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<StretchScope>() != null;

  @override
  bool updateShouldNotify(StretchScope oldWidget) => false;
}

/// Die Karte der Uebersicht, die zuerst beantwortet: Was steht heute an (oder war schon)?
/// Heute absolviert: die Fahrt mit der Ueberschrift des Coach-Feedbacks. Sonst das geplante Training von heute,
/// sonst das naechste der kommenden 14 Tage. Ohne Plan ein Hinweis zum Coach.
class TodayCard extends ConsumerWidget {
  const TodayCard({super.key, this.now});

  /// Fuer Tests: festes "Jetzt".
  final DateTime? now;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final n = now ?? DateTime.now();
    final today = DateTime(n.year, n.month, n.day);
    final data = ref.watch(calendarProvider((today, today.add(const Duration(days: 14)))));
    final acts = ref.watch(activitiesProvider).value ?? const <Json>[];
    if (data.isLoading && data.value == null) return const LoadingBlock(height: 170);
    if (data.hasError && data.value == null) {
      return StatusMessage.error(errorMessage(data.error!), onRetry: () => ref.invalidate(calendarProvider));
    }
    final d = data.value ?? const <String, dynamic>{};
    final workouts = [for (final w in (d['workouts'] as List? ?? const [])) Json.from(w as Map)];
    final todayKey = isoDay(today);
    final doneToday = [
      for (final a in (d['activities'] as List? ?? const []))
        if ((a as Map)['start_time'].toString().startsWith(todayKey)) Json.from(a),
    ];
    final plannedToday = workouts.where((w) => w['date'] == todayKey && w['status'] == 'planned').firstOrNull;
    final next = workouts.where((w) => w['status'] == 'planned' && (w['date'] as String).compareTo(todayKey) > 0).firstOrNull;

    if (doneToday.isNotEmpty) {
      final a = doneToday.last;
      final withFeedback = acts.where((x) => x['id'] == a['id']).firstOrNull;
      return _Done(activity: a, headline: withFeedback?['feedback_headline'] as String?, planned: plannedToday);
    }
    final w = plannedToday ?? next;
    if (w != null) return _Planned(w: w, today: today, isToday: plannedToday != null);
    return const _Empty();
  }
}

class _Frame extends StatelessWidget {
  const _Frame({required this.overline, required this.icon, required this.color, required this.child, this.onTap});
  final String overline;
  final IconData icon;
  final Color color;
  final Widget child;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return SurfaceCard(
      onTap: onTap,
      child: Column(mainAxisSize: MainAxisSize.max, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.sm)),
            child: Icon(icon, size: 16, color: color),
          ),
          const SizedBox(width: Gap.sm),
          Expanded(child: Text(overline, style: t.textTheme.titleMedium)),
          if (onTap != null) Icon(Icons.chevron_right_rounded, color: t.colorScheme.onSurfaceVariant),
        ]),
        const SizedBox(height: Gap.md),
        if (StretchScope.of(context)) Expanded(child: child) else child,
      ]),
    );
  }
}

class _Planned extends StatelessWidget {
  const _Planned({required this.w, required this.today, required this.isToday});
  final Json w;
  final DateTime today;
  final bool isToday;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final date = DateTime.parse(w['date'] as String);
    final diff = date.difference(today).inDays;
    final when = isToday
        ? 'Heute'
        : diff == 1
            ? 'Morgen'
            : DateFormat('EEEE, d. MMM', 'de').format(date);
    final structure = w['structure'] as List?;
    return _Frame(
      overline: isToday ? 'Heute' : 'Nächstes Training',
      icon: isToday ? Icons.today_rounded : Icons.event_rounded,
      color: isToday ? AppColors.tsb : t.colorScheme.primary,
      onTap: () => context.push('/workout/${w['id']}'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(w['title'] as String, style: t.textTheme.titleLarge, maxLines: 2, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Text(
            [
              if (!isToday) when,
              if (w['planned_duration_s'] != null) formatDuration(w['planned_duration_s'] as num),
              if (w['planned_tss'] != null) '${(w['planned_tss'] as num).round()} TSS',
            ].join(' · '),
            style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
          ),
        ]),
        if (structure != null && structure.isNotEmpty) ...[
          const SizedBox(height: Gap.md),
          WorkoutProfile(structure: structure, height: 54),
        ],
      ]),
    );
  }
}

class _Done extends StatelessWidget {
  const _Done({required this.activity, required this.headline, required this.planned});
  final Json activity;
  final String? headline;
  final Json? planned;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final tss = activity['tss'] as num?;
    return _Frame(
      overline: 'Heute geschafft',
      icon: Icons.check_circle_rounded,
      color: AppColors.completed,
      onTap: () => context.push('/activity/${activity['id']}'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(activity['name'] as String? ?? 'Fahrt', style: t.textTheme.titleLarge, maxLines: 2, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Text(
            [
              formatDuration(activity['duration_s'] as num),
              formatKm(activity['distance_m'] as num),
              if (tss != null) '${tss.round()} TSS',
            ].join(' · '),
            style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
          ),
        ]),
        const SizedBox(height: Gap.md),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(Icons.auto_awesome, size: 16, color: t.colorScheme.primary),
            const SizedBox(width: Gap.sm),
            Expanded(
              child: Text(
                headline ?? 'Feedback Deines Coaches ansehen',
                style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.primary, fontWeight: FontWeight.w600),
              ),
            ),
          ]),
          if (planned != null) ...[
            const SizedBox(height: Gap.sm),
            Text('Noch geplant: ${planned!['title']}',
                style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
          ],
        ]),
      ]),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return _Frame(
      overline: 'Training',
      icon: Icons.event_available_rounded,
      color: t.colorScheme.outline,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Nichts geplant', style: t.textTheme.titleLarge),
          const SizedBox(height: 2),
          Text('Lass Dir vom Coach die nächste Woche planen.',
              style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        ]),
        const SizedBox(height: Gap.md),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: () => context.go('/coach'),
            icon: const Icon(Icons.auto_awesome_outlined, size: 18),
            label: const Text('Zum Coach'),
          ),
        ),
      ]),
    );
  }
}

/// Kleines Profil eines strukturierten Trainings: Balkenhoehe = Leistung in % FTP, Breite = Dauer, Farbe = Zone.
class WorkoutProfile extends StatelessWidget {
  const WorkoutProfile({super.key, required this.structure, this.height = 54});
  final List structure;
  final double height;

  /// Flache Liste (Dauer in s, mittlere % FTP); Wiederholungsgruppen werden entfaltet.
  static List<(num, num)> flatten(List structure) {
    final out = <(num, num)>[];
    void leaf(Map s) {
      final p = (s['power_pct'] as List).cast<num>();
      out.add((s['duration_s'] as num, (p[0] + p[1]) / 2));
    }

    for (final s in structure) {
      final m = s as Map;
      if (m['type'] == 'repeat') {
        for (var i = 0; i < (m['count'] as num); i++) {
          for (final x in (m['steps'] as List)) {
            leaf(x as Map);
          }
        }
      } else {
        leaf(m);
      }
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final steps = flatten(structure);
    if (steps.isEmpty) return const SizedBox.shrink();
    return SizedBox(
      height: height,
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        for (final s in steps)
          Expanded(
            flex: (s.$1.toInt()).clamp(1, 1000000),
            child: FractionallySizedBox(
              heightFactor: ((s.$2.clamp(30, 150)) / 150).toDouble(),
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 0.5),
                decoration: BoxDecoration(
                  color: AppColors.zoneColor(s.$2),
                  borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                ),
              ),
            ),
          ),
      ]),
    );
  }
}
