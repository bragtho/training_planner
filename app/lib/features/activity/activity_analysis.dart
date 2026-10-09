import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

const _executionLabels = {
  'as_planned': 'Wie geplant',
  'harder': 'Härter als geplant',
  'easier': 'Lockerer als geplant',
  'partial': 'Teilweise umgesetzt',
  'unplanned': 'Ohne Plan',
  'race': 'Rennen',
};

/// Einordnung der Belastung einer Fahrt: Beschriftung und Farbe.
(String, Color) loadFitStyle(String? v) => switch (v) {
      'fits' => ('Belastung passt', AppColors.completed),
      'too_much' => ('Zu viel', const Color(0xFFEF4444)),
      'too_little' => ('Zu wenig', const Color(0xFF0EA5E9)),
      _ => ('Belastung unklar', const Color(0xFF94A3B8)),
    };

/// Abschnitte der Analyse (Feedback des Coaches, Soll/Ist, weitere Kennzahlen) fuer [TopDown].
/// Erst nach den Sensordaten, damit sie nicht doppelt bei Strava geholt werden; [waiting] steht bis dahin.
List<TopDownSection> analysisSections(WidgetRef ref, int id, {required double gap, required Widget waiting}) {
  if (!loaded(ref.watch(streamsProvider(id)))) {
    return [TopDownSection(ready: false, gap: gap, loading: waiting, child: const SizedBox.shrink())];
  }
  final analysis = ref.watch(activityAnalysisProvider(id));
  final a = analysis.value;
  return [
    // Das KI-Feedback ist eingeklappt und laedt im Hintergrund (gleiche Hoehe), es haelt nichts darunter auf
    TopDownSection(
      ready: loaded(analysis),
      gap: gap,
      placeholder: 160,
      child: analysis.when(
        loading: () => const SizedBox.shrink(),
        error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(activityAnalysisProvider(id))),
        data: (a) => CoachFeedbackCard(id: id, analysis: a),
      ),
    ),
    if (a?['compliance'] != null)
      TopDownSection(
        ready: true,
        child: ComplianceCard(compliance: Json.from(a!['compliance'] as Map), plan: Json.from((a['plan'] ?? const {}) as Map)),
      ),
    if (a?['metrics'] != null)
      TopDownSection(
        ready: true,
        child: RideDetails(metrics: Json.from(a!['metrics'] as Map), bests: (a['personal_bests_90d'] as List?) ?? const []),
      ),
  ];
}

/// Feedback des Coaches zur Fahrt. Fehlt es, wird es automatisch erstellt (wenn der Coach eingerichtet ist).
class CoachFeedbackCard extends ConsumerStatefulWidget {
  const CoachFeedbackCard({super.key, required this.id, required this.analysis});
  final int id;
  final Json analysis;

  @override
  ConsumerState<CoachFeedbackCard> createState() => _CoachFeedbackCardState();
}

class _CoachFeedbackCardState extends ConsumerState<CoachFeedbackCard> {
  Json? _fresh; // neu erstelltes Feedback (nach "Neu erstellen")
  bool _regenerating = false;

  Future<void> _regenerate() async {
    setState(() => _regenerating = true);
    try {
      final r = await ref.read(apiProvider).dio.post('/activities/${widget.id}/feedback',
          queryParameters: {'force': true}, options: Options(receiveTimeout: const Duration(minutes: 2)));
      if (mounted) setState(() => _fresh = Json.from((r.data as Map)['feedback'] as Map));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(errorMessage(e))));
    } finally {
      if (mounted) setState(() => _regenerating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = widget.analysis;
    final stored = a['feedback'] as Map?;
    if (_fresh != null || stored != null) {
      return _FeedbackView(
          fb: _fresh ?? Json.from(stored!), analysis: a, busy: _regenerating, onRegenerate: _regenerate);
    }
    if (a['coach_configured'] != true) {
      return const StatusMessage(
        icon: Icons.auto_awesome_outlined,
        title: 'Kein Coach-Feedback',
        message: 'Der KI-Coach ist im Backend nicht eingerichtet (ANTHROPIC_API_KEY).',
      );
    }
    final fb = ref.watch(activityFeedbackProvider(widget.id));
    return fb.when(
      loading: () => _FeedbackView(analysis: a, busy: _regenerating, onRegenerate: _regenerate),
      error: (e, _) => _FeedbackView(
        analysis: a,
        busy: _regenerating,
        onRegenerate: _regenerate,
        error: errorMessage(e),
        onRetry: () => ref.invalidate(activityFeedbackProvider(widget.id)),
      ),
      data: (f) => _FeedbackView(fb: f, analysis: a, busy: _regenerating, onRegenerate: _regenerate),
    );
  }
}

class _CoachMark extends StatelessWidget {
  const _CoachMark();

  @override
  Widget build(BuildContext context) => Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(Radii.md),
          gradient: const LinearGradient(colors: [AppColors.brand, AppColors.accent]),
        ),
        child: const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
      );
}

/// Eingeklappt (Standard) braucht die Karte immer gleich viel Platz, auch solange das Feedback noch laedt.
class _FeedbackView extends StatefulWidget {
  const _FeedbackView({
    this.fb,
    required this.analysis,
    required this.busy,
    required this.onRegenerate,
    this.error,
    this.onRetry,
  });
  final Json? fb; // null: wird noch erstellt (oder Fehler)
  final Json analysis;
  final bool busy;
  final VoidCallback onRegenerate;
  final String? error;
  final VoidCallback? onRetry;

  @override
  State<_FeedbackView> createState() => _FeedbackViewState();
}

class _FeedbackViewState extends State<_FeedbackView> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final analysis = widget.analysis, busy = widget.busy, onRegenerate = widget.onRegenerate;
    final ready = widget.fb != null;
    final open = _open && ready;
    final fb = widget.fb ?? const <String, dynamic>{};
    final (loadLabel, loadColor) = loadFitStyle(fb['load_fit'] as String?);
    final positives = [for (final p in (fb['positives'] as List? ?? const [])) p.toString()];
    final improvements = [for (final p in (fb['improvements'] as List? ?? const [])) p.toString()];
    final ftpHint = (fb['ftp_hint'] as String? ?? '').trim();
    final race = analysis['race'] == true;
    final accent = race ? const Color(0xFFA855F7) : AppColors.brand;

    Widget point(IconData icon, Color c, String s) => Padding(
          padding: const EdgeInsets.only(top: Gap.sm),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(padding: const EdgeInsets.only(top: 1), child: Icon(icon, size: 18, color: c)),
            const SizedBox(width: Gap.sm),
            Expanded(child: Text(s, style: t.textTheme.bodyMedium)),
          ]),
        );

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [accent.withValues(alpha: 0.14), accent.withValues(alpha: 0.02)],
          ),
        ),
        padding: const EdgeInsets.all(Gap.xl),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          InkWell(
            onTap: ready ? () => setState(() => _open = !_open) : null,
            child: Row(children: [
              const _CoachMark(),
              const SizedBox(width: Gap.md),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Feedback Deines Coaches',
                      style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
                  Text(
                    ready
                        ? fb['headline'] as String? ?? ''
                        : widget.error ?? 'Dein Coach analysiert die Fahrt im Hintergrund …',
                    maxLines: open ? null : 1,
                    overflow: open ? null : TextOverflow.ellipsis,
                    style: ready ? t.textTheme.titleLarge : t.textTheme.titleLarge?.copyWith(color: t.colorScheme.onSurfaceVariant),
                  ),
                ]),
              ),
              if (open || busy)
                IconButton(
                  tooltip: 'Neu erstellen',
                  onPressed: busy ? null : onRegenerate,
                  icon: busy
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.refresh_rounded),
                ),
              SizedBox(
                width: 48,
                height: 48,
                child: Center(
                  child: widget.error != null
                      ? IconButton(tooltip: 'Erneut versuchen', onPressed: widget.onRetry, icon: const Icon(Icons.refresh_rounded))
                      : ready
                      ? Icon(open ? Icons.expand_less_rounded : Icons.expand_more_rounded)
                      : const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                ),
              ),
            ]),
          ),
          if (open) ...[
          const SizedBox(height: Gap.md),
          Wrap(spacing: Gap.sm, runSpacing: Gap.sm, children: [
            if (analysis['type_label'] != null)
              Pill(
                  label: analysis['type_label'] as String,
                  color: race ? const Color(0xFFA855F7) : t.colorScheme.primary,
                  icon: race ? Icons.emoji_events_rounded : Icons.directions_bike_rounded),
            if (_executionLabels[fb['execution']] != null && fb['execution'] != 'race')
              Pill(label: _executionLabels[fb['execution']]!, color: AppColors.accent, icon: Icons.checklist_rounded),
            Pill(label: loadLabel, color: loadColor, icon: Icons.monitor_heart_outlined),
          ]),
          const SizedBox(height: Gap.md),
          Text(fb['summary'] as String? ?? '', style: t.textTheme.bodyMedium),
          if (positives.isNotEmpty) ...[
            const SizedBox(height: Gap.md),
            Text('Das war gut', style: t.textTheme.titleSmall),
            for (final p in positives) point(Icons.check_circle_rounded, AppColors.completed, p),
          ],
          if (improvements.isNotEmpty) ...[
            const SizedBox(height: Gap.md),
            Text('Darauf achten', style: t.textTheme.titleSmall),
            for (final p in improvements) point(Icons.trending_up_rounded, AppColors.tsb, p),
          ],
          if ((fb['next'] as String? ?? '').isNotEmpty) ...[
            const SizedBox(height: Gap.md),
            point(Icons.flag_rounded, t.colorScheme.primary, fb['next'] as String),
          ],
          if (ftpHint.isNotEmpty) ...[
            const SizedBox(height: Gap.md),
            Container(
              padding: const EdgeInsets.all(Gap.md),
              decoration: BoxDecoration(
                color: AppColors.power.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(Radii.md),
              ),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Icon(Icons.bolt_rounded, color: AppColors.power, size: 20),
                const SizedBox(width: Gap.sm),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(ftpHint, style: t.textTheme.bodyMedium),
                    TextButton(onPressed: () => context.go('/'), child: const Text('FTP-Check in der Übersicht')),
                  ]),
                ),
              ]),
            ),
          ],
          ],
        ]),
      ),
    );
  }
}

/// Soll/Ist gegen das geplante Training: TSS, Dauer und jedes Intervall.
class ComplianceCard extends StatelessWidget {
  const ComplianceCard({super.key, required this.compliance, required this.plan});
  final Json compliance;
  final Json plan;

  static Color statusColor(String? s) => switch (s) {
        'ok' => AppColors.completed,
        'over' => const Color(0xFFF97316),
        _ => const Color(0xFF0EA5E9),
      };

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final intervals = [for (final i in (compliance['intervals'] as List? ?? const [])) Json.from(i as Map)];
    Widget stat(String label, Map? m, String unit) {
      if (m == null) return const SizedBox.shrink();
      final pct = m['pct'] as num;
      final c = (pct - 100).abs() <= 10 ? AppColors.completed : const Color(0xFFF97316);
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        Text('${m['actual'] ?? m['actual_min']} / ${m['planned'] ?? m['planned_min']} $unit', style: t.textTheme.titleMedium),
        Text('$pct %', style: t.textTheme.labelMedium?.copyWith(color: c, fontWeight: FontWeight.w700)),
      ]);
    }

    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionHeader(
          title: 'Soll und Ist',
          subtitle: plan['title'] == null ? 'Vergleich mit dem geplanten Training' : 'Geplant: ${plan['title']}',
        ),
        Wrap(spacing: Gap.xxl, runSpacing: Gap.md, children: [
          stat('TSS', compliance['tss'] as Map?, ''),
          stat('Dauer', compliance['duration'] as Map?, 'min'),
          if (compliance['interval_count'] != null)
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Intervalle im Ziel', style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
              Text('${compliance['hit']} / ${compliance['interval_count']}', style: t.textTheme.titleMedium),
              Text('Ø ${compliance['avg_pct']} % vom Soll',
                  style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
            ]),
        ]),
        if (intervals.isNotEmpty) ...[
          const SizedBox(height: Gap.lg),
          for (final i in intervals)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(children: [
                Container(
                  width: 30,
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                      color: statusColor(i['status'] as String?).withValues(alpha: 0.14),
                      borderRadius: BorderRadius.circular(6)),
                  child: Text('${i['n']}',
                      style: t.textTheme.labelSmall
                          ?.copyWith(color: statusColor(i['status'] as String?), fontWeight: FontWeight.w800)),
                ),
                const SizedBox(width: Gap.md),
                SizedBox(width: 64, child: Text(formatDuration(i['duration_s'] as num), style: t.textTheme.bodySmall)),
                Expanded(
                  child: Text('Soll ${i['target_w']} W · Ist ${i['actual_w']} W',
                      style: t.textTheme.bodyMedium, overflow: TextOverflow.ellipsis),
                ),
                Text('${i['pct']} %',
                    style: t.textTheme.labelLarge?.copyWith(
                        color: statusColor(i['status'] as String?),
                        fontWeight: FontWeight.w700,
                        fontFeatures: const [FontFeature.tabularFigures()])),
              ]),
            ),
          if (compliance['fade_pct'] != null && (compliance['fade_pct'] as num) <= -5) ...[
            const SizedBox(height: Gap.sm),
            Text('Leistungsabfall über die Serie: ${compliance['fade_pct']} Prozentpunkte vom ersten zum letzten Drittel.',
                style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
          ],
        ],
      ]),
    );
  }
}

/// Weitere Kennzahlen der Fahrt: Variabilitaet, Entkopplung, Zeit ueber FTP, Antritte und Bestwerte.
class RideDetails extends StatelessWidget {
  const RideDetails({super.key, required this.metrics, required this.bests});
  final Json metrics;
  final List bests;

  @override
  Widget build(BuildContext context) {
    final m = metrics;
    final tiles = <Widget>[
      if (m['vi'] != null)
        MetricTile(
            compact: true,
            label: 'Variabilität',
            value: (m['vi'] as num).toStringAsFixed(2),
            unit: 'VI',
            icon: Icons.waves_rounded,
            color: AppColors.power,
            help: 'Variability Index = NP ÷ Ø Leistung. Bis etwa 1,05 gleichmäßig, über 1,15 sehr wechselhaft (Rennen, Gruppe).'),
      if (m['decoupling_pct'] != null)
        MetricTile(
            compact: true,
            label: 'Entkopplung',
            value: (m['decoupling_pct'] as num).toStringAsFixed(1),
            unit: '%',
            icon: Icons.call_split_rounded,
            color: AppColors.heart,
            help: 'Pw:HR-Entkopplung: Wie stark der Puls bei gleicher Leistung in der zweiten Hälfte steigt. '
                'Unter 5 % spricht für eine gute Grundlage (Praxisregel).'),
      if (m['time_above_ftp_s'] != null)
        MetricTile(
            compact: true,
            label: 'Über FTP',
            value: formatDuration(m['time_above_ftp_s'] as num),
            icon: Icons.local_fire_department_rounded,
            color: AppColors.zones[5]),
      if (m['matches'] != null && (m['matches'] as num) > 0)
        MetricTile(
            compact: true,
            label: 'Antritte',
            value: '${m['matches']}',
            icon: Icons.flash_on_rounded,
            color: AppColors.zones[6],
            help: 'Belastungen über 120 % FTP von mindestens 10 Sekunden.'),
      if (m['pacing'] != null && (m['pacing'] as Map)['change_pct'] != null)
        MetricTile(
            compact: true,
            label: 'Pacing',
            value: '${((m['pacing'] as Map)['change_pct'] as num) > 0 ? '+' : ''}${(m['pacing'] as Map)['change_pct']}',
            unit: '%',
            icon: Icons.timeline_rounded,
            color: AppColors.accent,
            help: 'Leistung im letzten gegenüber dem ersten Drittel der Fahrt.'),
      if (m['ef'] != null)
        MetricTile(
            compact: true,
            label: 'Effizienz',
            value: (m['ef'] as num).toStringAsFixed(2),
            unit: 'EF',
            icon: Icons.eco_rounded,
            color: AppColors.completed,
            help: 'Efficiency Factor = NP ÷ Ø Puls. Steigt er bei gleichen Fahrten, verbessert sich die Grundlage.'),
    ];
    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionHeader(title: 'Analyse', subtitle: 'Kennzahlen aus den Sensordaten'),
        if (tiles.isNotEmpty) ResponsiveGrid(minItemWidth: 140, children: tiles),
      ]),
    );
  }
}
