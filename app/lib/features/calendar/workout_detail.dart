import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart' hide TextDirection;

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'step_node.dart';
import 'strength_plan.dart';
import 'workout_editor.dart';

/// Nur-Lesen-Uebersicht eines Trainings. Bearbeiten erst per Button oben rechts.
class WorkoutDetailScreen extends ConsumerStatefulWidget {
  const WorkoutDetailScreen({super.key, required this.id});
  final int id;

  @override
  ConsumerState<WorkoutDetailScreen> createState() => _WorkoutDetailScreenState();
}

class _WorkoutDetailScreenState extends ConsumerState<WorkoutDetailScreen> {
  Json? _w;
  Json? _summary;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final dio = ref.read(apiProvider).dio;
      final w = Json.from((await dio.get('/workouts/${widget.id}')).data as Map);
      Json? summary;
      final st = w['structure'] as List?;
      if (w['kind'] != 'strength' && st != null && st.isNotEmpty) {
        summary = Json.from((await dio.post('/workouts/preview', data: {'structure': st})).data as Map);
      } else if (w['planned_duration_s'] != null || w['planned_tss'] != null) {
        summary = {'duration_s': w['planned_duration_s'], 'tss': w['planned_tss']};
      }
      if (!mounted) return;
      setState(() {
        _w = w;
        _summary = summary;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
  }

  void _close() => context.canPop() ? context.pop() : context.go('/calendar');

  Future<void> _edit() async {
    await context.push('/workout/${widget.id}/edit');
    if (mounted) _load(); // Editor kann gespeichert oder geloescht haben
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final w = _w;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Training'),
        leading: BackButton(onPressed: _close),
        actions: [
          if (w != null)
            Padding(
              padding: const EdgeInsets.only(right: Gap.md),
              child: FilledButton.icon(
                style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
                onPressed: _edit,
                icon: const Icon(Icons.edit_rounded, size: 18),
                label: const Text('Bearbeiten'),
              ),
            ),
        ],
      ),
      body: _error != null
          ? Center(child: StatusMessage.error(_error!))
          : w == null
              ? const Center(child: CircularProgressIndicator())
              : _body(t, w),
    );
  }

  Widget _body(ThemeData t, Json w) {
    final st = [for (final s in (w['structure'] as List?) ?? const []) Map<String, dynamic>.from(s as Map)];
    final desc = w['description'] as String?;
    final s = _summary;
    return PageBody(
      maxWidth: 820,
      children: [
        Text(
          DateFormat('EEEE, d. MMMM yyyy', 'de').format(DateTime.parse(w['date'] as String)),
          style: t.textTheme.labelLarge?.copyWith(color: t.colorScheme.primary),
        ),
        Text(w['title'] as String, style: t.textTheme.headlineSmall),
        if (desc != null && desc.isNotEmpty) ...[
          const SizedBox(height: Gap.sm),
          Text(desc, style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        ],
        const SizedBox(height: Gap.lg),
        if (w['kind'] == 'strength')
          StrengthPlan(exercises: st, durationS: w['planned_duration_s'] as num?)
        else ...[
          if (s != null) ...[
            ResponsiveGrid(
              minItemWidth: 120,
              spacing: Gap.sm,
              children: [
                if (s['duration_s'] != null)
                  MetricTile(
                    compact: true,
                    label: 'Dauer',
                    value: formatDuration(s['duration_s'] as num),
                    icon: Icons.schedule_rounded,
                    color: t.colorScheme.primary,
                  ),
                if (s['tss'] != null)
                  MetricTile(
                    compact: true,
                    label: 'TSS',
                    value: '${(s['tss'] as num).round()}',
                    icon: Icons.fitness_center_rounded,
                    color: AppColors.tsb,
                  ),
                if (s['intensity_factor'] != null)
                  MetricTile(
                    compact: true,
                    label: 'IF',
                    value: (s['intensity_factor'] as num).toStringAsFixed(2),
                    icon: Icons.speed_rounded,
                    color: AppColors.zoneColor((s['intensity_factor'] as num) * 100),
                  ),
                if (s['np'] != null)
                  MetricTile(
                    compact: true,
                    label: 'NP',
                    value: '${(s['np'] as num).round()} W',
                    icon: Icons.electric_bolt_rounded,
                    color: AppColors.power,
                  ),
              ],
            ),
            const SizedBox(height: Gap.xl),
          ],
          if (st.isNotEmpty) ...[
            SurfaceCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SectionHeader(title: 'Profil', subtitle: 'Leistung in % der FTP, Farbe = Zone'),
                  SizedBox(height: 170, child: WorkoutProfile(structure: st)),
                ],
              ),
            ),
            const SizedBox(height: Gap.xl),
            const SectionHeader(title: 'Ablauf', subtitle: 'Zielwerte in % der FTP'),
            for (final n in st) _StepView(step: n),
          ],
        ],
      ],
    );
  }
}

class _StepView extends StatelessWidget {
  const _StepView({required this.step});
  final Map<String, dynamic> step;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    if (step['type'] == 'repeat') {
      return Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.all(Gap.md),
        decoration: BoxDecoration(
          color: t.colorScheme.primary.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(Radii.lg),
          border: Border.all(color: t.colorScheme.primary.withValues(alpha: 0.25)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(children: [
              Icon(Icons.repeat_rounded, color: t.colorScheme.primary),
              const SizedBox(width: Gap.sm),
              Text('${step['count']}× wiederholen', style: t.textTheme.titleSmall),
            ]),
            for (final s in step['steps'] as List) _StepView(step: Map<String, dynamic>.from(s as Map)),
          ],
        ),
      );
    }
    final p = (step['power_pct'] as List).cast<num>();
    final ramp = step['type'] == 'warmup' || step['type'] == 'cooldown';
    final color = AppColors.zoneColor((p[0] + p[1]) / 2);
    final target = ramp ? '${p[0].round()} → ${p[1].round()} %' : '${((p[0] + p[1]) / 2).round()} %';
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: t.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(Radii.md),
        border: Border.all(color: t.colorScheme.outlineVariant),
      ),
      child: Container(
        padding: const EdgeInsets.all(Gap.md),
        decoration: BoxDecoration(border: Border(left: BorderSide(color: color, width: 4))),
        child: Row(children: [
          Expanded(child: Text(StepNode.types[step['type']] ?? '${step['type']}', style: t.textTheme.titleSmall)),
          Text(formatDuration(step['duration_s'] as num), style: t.textTheme.bodyMedium),
          const SizedBox(width: Gap.lg),
          Text(target, style: t.textTheme.titleSmall?.copyWith(color: color)),
        ]),
      ),
    );
  }
}
