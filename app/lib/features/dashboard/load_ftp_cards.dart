import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

/// Urteil der Belastungsbewertung: Beschriftung, Farbe, Symbol.
(String, Color, IconData) loadVerdictStyle(String? v) => switch (v) {
      'too_much' => ('Zu viel', const Color(0xFFEF4444), Icons.warning_amber_rounded),
      'slightly_much' => ('Eher viel', const Color(0xFFF97316), Icons.trending_up_rounded),
      'ok' => ('Passend', AppColors.completed, Icons.check_circle_rounded),
      'too_little' => ('Zu wenig', const Color(0xFF0EA5E9), Icons.trending_down_rounded),
      'mixed' => ('Gemischt', const Color(0xFF94A3B8), Icons.compare_arrows_rounded),
      _ => ('Noch unklar', const Color(0xFF94A3B8), Icons.hourglass_empty_rounded),
    };

/// Ist die Trainingsbelastung zu hoch, passend oder zu gering? Mit Einordnung des Coaches (kennt Gespraech und Gedaechtnis).
class LoadCard extends ConsumerWidget {
  const LoadCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final load = ref.watch(loadCheckProvider);
    return load.when(
      loading: () => const LoadingBlock(height: 210),
      error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(loadCheckProvider)),
      data: (d) {
        final coach = d['coach'] as Map?;
        final verdict = (coach?['verdict'] ?? d['verdict']) as String?;
        final (label, color, icon) = loadVerdictStyle(verdict);
        final flags = [for (final f in (d['flags'] as List? ?? const [])) Json.from(f as Map)];
        final m = Json.from((d['metrics'] ?? const {}) as Map);
        final ctx = Json.from((d['context'] ?? const {}) as Map);
        final dist = d['intensity_distribution_28d'] as Map?;
        String signed(num? v) => v == null ? '–' : '${v > 0 ? '+' : ''}${v.toStringAsFixed(1)}';
        return SurfaceCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.md)),
                child: Icon(icon, color: color, size: 20),
              ),
              const SizedBox(width: Gap.md),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Trainingsbelastung', style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
                  Text(label, style: t.textTheme.titleLarge?.copyWith(color: color)),
                ]),
              ),
              const InfoHint(
                  'Bewertet CTL-Anstieg, Form, Lastspitzen, Monotonie, Soll/Ist und den Trend des Pulses bei gleicher Leistung. '
                  'Die Schwellen sind Praxisregeln; der Coach ordnet sie mit Deinem Gespräch und Gedächtnis ein.'),
            ]),
            const SizedBox(height: Gap.md),
            if (coach?['text'] != null)
              Text(coach!['text'] as String, style: t.textTheme.bodyMedium)
            else
              for (final f in flags.take(3))
                Padding(
                  padding: const EdgeInsets.only(bottom: Gap.xs),
                  child: Text('• ${f['text']}', style: t.textTheme.bodyMedium),
                ),
            if (coach?['text'] == null && flags.isEmpty)
              Text('Keine Auffälligkeiten: Anstieg, Form und Verteilung liegen im üblichen Rahmen.',
                  style: t.textTheme.bodyMedium),
            const SizedBox(height: Gap.md),
            Wrap(spacing: Gap.sm, runSpacing: Gap.sm, children: [
              if (m['ramp_7d'] != null) Pill(label: 'CTL ${signed(m['ramp_7d'] as num?)} / Woche', color: AppColors.ctl),
              if (m['tss_7d'] != null) Pill(label: '${m['tss_7d']} TSS in 7 Tagen', color: AppColors.tsb),
              if ((ctx['planned_tss_14d'] as num? ?? 0) > 0)
                Pill(label: 'Soll/Ist 14 T: ${ctx['actual_tss_14d']}/${ctx['planned_tss_14d']}', color: AppColors.accent),
              if (ctx['season_phase'] != null) Pill(label: ctx['season_phase'] as String, color: t.colorScheme.primary),
            ]),
            if (dist != null) ...[
              const SizedBox(height: Gap.md),
              _Distribution(dist: Json.from(dist)),
            ],
          ]),
        );
      },
    );
  }
}

/// Zeitanteile nach Intensitaet der letzten 28 Tage als gestapelter Balken.
class _Distribution extends StatelessWidget {
  const _Distribution({required this.dist});
  final Json dist;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final parts = <(String, num, Color)>[
      ('Z1–2', dist['low_z1_z2_pct'] as num, AppColors.zones[1]),
      ('Z3', dist['tempo_z3_pct'] as num, AppColors.zones[2]),
      ('Z4', dist['threshold_z4_pct'] as num, AppColors.zones[3]),
      ('Z5+', dist['high_z5plus_pct'] as num, AppColors.zones[5]),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Intensität der letzten 4 Wochen (${dist['rides_with_data']} von ${dist['rides_total']} Fahrten ausgewertet)',
          style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
      const SizedBox(height: Gap.xs),
      ClipRRect(
        borderRadius: BorderRadius.circular(Radii.pill),
        child: SizedBox(
          height: 10,
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            for (final p in parts)
              if (p.$2 > 0) Expanded(flex: p.$2.round().clamp(1, 100), child: ColoredBox(color: p.$3)),
          ]),
        ),
      ),
      const SizedBox(height: Gap.xs),
      Wrap(spacing: Gap.md, children: [for (final p in parts) LegendDot(label: '${p.$1} ${p.$2} %', color: p.$3)]),
    ]);
  }
}

/// Passt die FTP? Bei einem Vorschlag laesst sie sich mit einem Tippen uebernehmen (TSS und Zonen werden neu berechnet).
class FtpCard extends ConsumerStatefulWidget {
  const FtpCard({super.key});

  @override
  ConsumerState<FtpCard> createState() => _FtpCardState();
}

class _FtpCardState extends ConsumerState<FtpCard> {
  bool _saving = false;

  Future<void> _accept(num ftp) async {
    setState(() => _saving = true);
    try {
      await ref.read(apiProvider).dio.post('/metrics/ftp-check/accept', data: {'ftp': ftp});
      ref
        ..invalidate(profileProvider)
        ..invalidate(ftpCheckProvider)
        ..invalidate(loadCheckProvider)
        ..invalidate(pmcProvider)
        ..invalidate(activitiesProvider)
        ..invalidate(calendarProvider)
        ..invalidate(atpProvider)
        ..invalidate(formHintProvider);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('FTP auf ${ftp.round()} W gesetzt, TSS und Zonen neu berechnet.')));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(errorMessage(e))));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final check = ref.watch(ftpCheckProvider);
    return check.when(
      loading: () => const LoadingBlock(height: 210),
      error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(ftpCheckProvider)),
      data: (d) {
        final rec = d['recommendation'] as String?;
        final (title, color, icon) = switch (rec) {
          'raise' => ('FTP anheben?', AppColors.power, Icons.trending_up_rounded),
          'hold' => ('FTP vorerst halten', AppColors.tsb, Icons.pause_circle_outline_rounded),
          'ok' => ('FTP passt', AppColors.completed, Icons.check_circle_rounded),
          _ => ('FTP unbestätigt', const Color(0xFF94A3B8), Icons.help_outline_rounded),
        };
        final best = Json.from((d['best_efforts'] ?? const {}) as Map);
        return SurfaceCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.md)),
                child: Icon(icon, color: color, size: 20),
              ),
              const SizedBox(width: Gap.md),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('FTP-Check · eingestellt ${d['ftp']} W',
                      style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
                  Text(title, style: t.textTheme.titleLarge?.copyWith(color: color)),
                ]),
              ),
              const InfoHint('Schätzt die FTP aus den besten 20, 30 und 60 Minuten, der NP langer harter Fahrten und der '
                  'Critical Power der letzten 6 Wochen (Median, Praxisregeln). Sinkt die Fitness stark, wird nicht angehoben.'),
            ]),
            const SizedBox(height: Gap.md),
            Text(d['reason'] as String? ?? '', style: t.textTheme.bodyMedium),
            if (best.isNotEmpty) ...[
              const SizedBox(height: Gap.md),
              Wrap(spacing: Gap.sm, runSpacing: Gap.sm, children: [
                for (final k in const ['5 min', '20 min', '60 min'])
                  if (best[k] != null) Pill(label: '$k  ${(best[k] as Map)['watts']} W', color: AppColors.power),
                if (d['critical_power'] != null)
                  Pill(label: 'CP ${(d['critical_power'] as Map)['cp']} W', color: AppColors.accent),
              ]),
            ],
            const SizedBox(height: Gap.md),
            if (rec == 'raise' && d['suggested_ftp'] != null)
              FilledButton.icon(
                onPressed: _saving ? null : () => _accept(d['suggested_ftp'] as num),
                icon: _saving
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.bolt_rounded),
                label: Text('Auf ${d['suggested_ftp']} W setzen'),
              )
            else if (rec == 'test' || rec == 'hold')
              OutlinedButton.icon(
                onPressed: () => context.go('/coach'),
                icon: const Icon(Icons.auto_awesome_outlined),
                label: const Text('FTP-Test mit dem Coach planen'),
              ),
          ]),
        );
      },
    );
  }
}
