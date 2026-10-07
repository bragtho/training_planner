import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'exercise_figure.dart';

/// "3 × 10 Wiederholungen" oder "3 × 45 s halten".
String setsText(Map e) {
  final sets = (e['sets'] as num).toInt();
  final reps = e['reps'] as num?;
  return reps != null ? '$sets × ${reps.toInt()} Wiederholungen' : '$sets × ${(e['duration_s'] as num).toInt()} s halten';
}

/// "45 s" oder "1:30 min".
String restText(num s) {
  final v = s.toInt();
  return v < 60 ? '$v s' : '${v ~/ 60}:${(v % 60).toString().padLeft(2, '0')} min';
}

/// Krafttraining: Uebungen mit Saetzen, Wiederholungen bzw. Haltezeit, Pause und Last.
/// Uebungen aus dem Katalog lassen sich antippen: Bilder von Start und Ende, Anleitung, Muskeln und typische Fehler.
class StrengthPlan extends ConsumerStatefulWidget {
  const StrengthPlan({super.key, required this.exercises, this.durationS});
  final List<Json> exercises;
  final num? durationS;

  @override
  ConsumerState<StrengthPlan> createState() => _StrengthPlanState();
}

class _StrengthPlanState extends ConsumerState<StrengthPlan> {
  final _open = <int>{};

  List<Json> get exercises => widget.exercises;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final catalog = ref.watch(exerciseCatalogProvider).value ?? const <String, Json>{};
    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SectionHeader(
          title: 'Krafttraining',
          subtitle: [
            '${exercises.length} ${exercises.length == 1 ? 'Übung' : 'Übungen'}',
            if (widget.durationS != null) 'ca. ${formatDuration(widget.durationS!)}',
          ].join(' · '),
        ),
        for (var i = 0; i < exercises.length; i++) ...[
          if (i > 0) Divider(color: t.colorScheme.outlineVariant),
          InkWell(
            borderRadius: BorderRadius.circular(Radii.md),
            onTap: () => setState(() => _open.contains(i) ? _open.remove(i) : _open.add(i)),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: Gap.sm),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Container(
                    width: 28,
                    height: 28,
                    alignment: Alignment.center,
                    decoration:
                        BoxDecoration(color: AppColors.power.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(Radii.sm)),
                    child: Text('${i + 1}', style: t.textTheme.labelLarge?.copyWith(color: AppColors.power, fontWeight: FontWeight.w800)),
                  ),
                  const SizedBox(width: Gap.md),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(exercises[i]['name'] as String, style: t.textTheme.titleMedium),
                      const SizedBox(height: 2),
                      Text(setsText(exercises[i]), style: t.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600)),
                      const SizedBox(height: Gap.xs),
                      Wrap(spacing: Gap.sm, runSpacing: Gap.xs, children: [
                        if (((exercises[i]['rest_s'] as num?) ?? 0) > 0)
                          Pill(label: 'Pause ${restText(exercises[i]['rest_s'] as num)}', color: muted, icon: Icons.timer_outlined),
                        if (exercises[i]['load'] != null)
                          Pill(label: exercises[i]['load'] as String, color: AppColors.power, icon: Icons.fitness_center_rounded),
                      ]),
                      if (exercises[i]['note'] != null) ...[
                        const SizedBox(height: Gap.xs),
                        Text(exercises[i]['note'] as String, style: t.textTheme.bodySmall?.copyWith(color: muted)),
                      ],
                    ]),
                  ),
                  Icon(_open.contains(i) ? Icons.expand_less_rounded : Icons.expand_more_rounded, color: muted),
                ]),
                if (_open.contains(i)) _Guide(id: exercises[i]['exercise_id'] as String?, entry: catalog[exercises[i]['exercise_id']]),
              ]),
            ),
          ),
        ],
      ]),
    );
  }
}

/// Bilder, Schritte, Muskeln und typische Fehler einer Katalog-Uebung.
class _Guide extends StatelessWidget {
  const _Guide({required this.id, required this.entry});
  final String? id;
  final Json? entry;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final steps = (entry?['steps'] as List?)?.cast<String>() ?? const <String>[];
    final mistakes = (entry?['mistakes'] as List?)?.cast<String>() ?? const <String>[];
    final muscles = (entry?['muscles'] as List?)?.cast<String>() ?? const <String>[];
    return Padding(
      padding: const EdgeInsets.only(top: Gap.md),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (!ExerciseFigures.has(id))
          Text(
            'Zu dieser Übung gibt es noch keine Anleitung mit Bildern. Frag Deinen Coach, wenn Du sie erklärt haben möchtest.',
            style: t.textTheme.bodyMedium?.copyWith(color: muted),
          )
        else
          ExerciseFigures(exerciseId: id!),
        if (muscles.isNotEmpty) ...[
          const SizedBox(height: Gap.md),
          Wrap(spacing: Gap.sm, runSpacing: Gap.xs, children: [for (final m in muscles) Pill(label: m, color: AppColors.cadence)]),
        ],
        if (steps.isNotEmpty) ...[
          const SizedBox(height: Gap.md),
          Text('So geht\'s', style: t.textTheme.titleSmall),
          const SizedBox(height: Gap.xs),
          for (var i = 0; i < steps.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(width: 20, child: Text('${i + 1}.', style: t.textTheme.bodyMedium?.copyWith(color: muted, fontWeight: FontWeight.w700))),
                Expanded(child: Text(steps[i], style: t.textTheme.bodyMedium)),
              ]),
            ),
        ],
        if (mistakes.isNotEmpty) ...[
          const SizedBox(height: Gap.sm),
          Text('Häufige Fehler', style: t.textTheme.titleSmall),
          const SizedBox(height: Gap.xs),
          for (final m in mistakes)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(Icons.close_rounded, size: 16, color: t.colorScheme.error),
                const SizedBox(width: 4),
                Expanded(child: Text(m, style: t.textTheme.bodyMedium?.copyWith(color: muted))),
              ]),
            ),
        ],
      ]),
    );
  }
}
