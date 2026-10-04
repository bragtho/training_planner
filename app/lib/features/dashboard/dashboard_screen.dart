import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/data.dart';

const ctlColor = Color(0xFF2E7DD7);
const atlColor = Color(0xFFD6336C);
const tsbColor = Color(0xFFE0A100);

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pmc = ref.watch(pmcProvider);
    final acts = ref.watch(activitiesProvider);

    Future<void> refresh() async {
      ref
        ..invalidate(pmcProvider)
        ..invalidate(activitiesProvider);
      await ref.read(pmcProvider.future);
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Dashboard')),
      body: RefreshIndicator(
        onRefresh: refresh,
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              children: [
                pmc.when(
                  loading: () => const SizedBox(
                      height: 200, child: Center(child: CircularProgressIndicator())),
                  error: (e, _) => _ErrorBox(message: errorMessage(e), onRetry: refresh),
                  data: (d) => d['current'] == null
                      ? const _EmptyState()
                      : _PmcSection(data: d),
                ),
                const SizedBox(height: 24),
                const _UpcomingWorkouts(),
                Text('Letzte Aktivitäten', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                acts.when(
                  loading: () => const SizedBox.shrink(),
                  error: (e, _) => Text(errorMessage(e)),
                  data: (list) => Column(
                    children: [for (final a in list) _ActivityTile(a: a)],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorBox extends StatelessWidget {
  const _ErrorBox({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Column(children: [
        Text(message),
        TextButton(onPressed: onRetry, child: const Text('Erneut versuchen')),
      ]);
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 48),
        child: Column(children: [
          Icon(Icons.show_chart, size: 64, color: Theme.of(context).colorScheme.outline),
          const SizedBox(height: 16),
          const Text(
            'Noch keine Trainingsdaten.\nVerbinde Strava im Profil und starte die Synchronisierung.',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          FilledButton(
              onPressed: () => context.go('/profile'), child: const Text('Zum Profil')),
        ]),
      );
}

class _PmcSection extends StatelessWidget {
  const _PmcSection({required this.data});
  final Json data;

  @override
  Widget build(BuildContext context) {
    final cur = data['current'] as Map;
    final rows = [for (final r in data['rows'] as List) Json.from(r as Map)];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        _Stat('Fitness (CTL)', cur['ctl'], ctlColor),
        _Stat('Ermüdung (ATL)', cur['atl'], atlColor),
        _Stat('Form (TSB)', cur['tsb'], tsbColor, signed: true),
      ]),
      const SizedBox(height: 16),
      SizedBox(height: 240, child: _PmcChart(rows: rows)),
      const SizedBox(height: 8),
      const Wrap(spacing: 16, children: [
        _Legend('Fitness', ctlColor),
        _Legend('Ermüdung', atlColor),
        _Legend('Form', tsbColor),
      ]),
    ]);
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value, this.color, {this.signed = false});
  final String label;
  final num value;
  final Color color;
  final bool signed;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final text = '${signed && value > 0 ? '+' : ''}${value.toStringAsFixed(0)}';
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: t.textTheme.labelMedium),
            const SizedBox(height: 4),
            Text(text,
                style: t.textTheme.headlineSmall?.copyWith(color: color, fontWeight: FontWeight.w600)),
          ]),
        ),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend(this.label, this.color);
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 12, height: 3, color: color),
        const SizedBox(width: 6),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ]);
}

class _PmcChart extends StatelessWidget {
  const _PmcChart({required this.rows});
  final List<Json> rows;

  LineChartBarData _line(String key, Color c) => LineChartBarData(
        spots: [for (var i = 0; i < rows.length; i++) FlSpot(i.toDouble(), (rows[i][key] as num).toDouble())],
        color: c,
        barWidth: 2,
        dotData: const FlDotData(show: false),
      );

  @override
  Widget build(BuildContext context) {
    final fmt = DateFormat('d.M.');
    final step = (rows.length / 5).ceilToDouble().clamp(1, 1000).toDouble();
    return LineChart(LineChartData(
      lineBarsData: [_line('ctl', ctlColor), _line('atl', atlColor), _line('tsb', tsbColor)],
      gridData: const FlGridData(drawVerticalLine: false),
      borderData: FlBorderData(show: false),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(),
        rightTitles: const AxisTitles(),
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 32,
            getTitlesWidget: (v, meta) => (v == meta.min || v == meta.max)
                ? const SizedBox.shrink()
                : Text(v.round().toString(), style: Theme.of(context).textTheme.labelSmall),
          ),
        ),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            interval: step,
            getTitlesWidget: (v, meta) {
              final i = v.round();
              if (i < 0 || i >= rows.length) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(fmt.format(DateTime.parse(rows[i]['date'] as String)),
                    style: Theme.of(context).textTheme.labelSmall),
              );
            },
          ),
        ),
      ),
      lineTouchData: LineTouchData(
        touchTooltipData: LineTouchTooltipData(
          getTooltipItems: (spots) => [
            for (final s in spots)
              LineTooltipItem(
                s.barIndex == 0
                    ? '${fmt.format(DateTime.parse(rows[s.x.toInt()]['date'] as String))}\n'
                      'CTL ${s.y.toStringAsFixed(0)}'
                    : '${const ['', 'ATL', 'TSB'][s.barIndex]} ${s.y.toStringAsFixed(0)}',
                TextStyle(color: s.bar.color, fontWeight: FontWeight.w600),
              ),
          ],
        ),
      ),
    ));
  }
}

class _ActivityTile extends StatelessWidget {
  const _ActivityTile({required this.a});
  final Json a;

  @override
  Widget build(BuildContext context) {
    final date = DateFormat('E d.M.yyyy', 'de').format(DateTime.parse(a['start_time'] as String));
    final tss = a['tss'];
    return Card(
      child: ListTile(
        onTap: () => context.push('/activity/${a['id']}'),
        title: Text(a['name'] as String? ?? 'Fahrt'),
        subtitle: Text('$date · ${formatDuration(a['duration_s'] as num)} · ${formatKm(a['distance_m'] as num)}'),
        trailing: tss == null
            ? const Text('–')
            : Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text('${(tss as num).round()} TSS', style: const TextStyle(fontWeight: FontWeight.w600)),
                if (a['norm_power'] != null) Text('${(a['norm_power'] as num).round()} W NP'),
              ]),
      ),
    );
  }
}

/// Geplante Trainings der naechsten 7 Tage.
class _UpcomingWorkouts extends ConsumerWidget {
  const _UpcomingWorkouts();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final data = ref.watch(calendarProvider((today, today.add(const Duration(days: 7)))));
    final upcoming = [
      for (final w in (data.value?['workouts'] as List?) ?? const [])
        if ((w as Map)['status'] == 'planned') Json.from(w),
    ];
    if (upcoming.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Nächste Trainings', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      for (final w in upcoming)
        Card(
          child: ListTile(
            onTap: () => context.push('/workout/${w['id']}'),
            leading: const Icon(Icons.event_note),
            title: Text(w['title'] as String),
            subtitle: Text([
              DateFormat('E d.M.', 'de').format(DateTime.parse(w['date'] as String)),
              if (w['planned_duration_s'] != null) formatDuration(w['planned_duration_s'] as num),
            ].join(' · ')),
            trailing: w['planned_tss'] == null ? null : Text('${(w['planned_tss'] as num).round()} TSS'),
          ),
        ),
      const SizedBox(height: 24),
    ]);
  }
}
