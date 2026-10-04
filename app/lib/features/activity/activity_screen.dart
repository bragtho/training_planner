import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/data.dart';

class ActivityScreen extends ConsumerWidget {
  const ActivityScreen({super.key, required this.id});
  final int id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final act = ref.watch(activityProvider(id));
    final streams = ref.watch(streamsProvider(id));

    // Streams berechnen NP/TSS exakt neu -> Kopfdaten danach aktualisieren
    ref.listen(streamsProvider(id), (_, next) {
      if (next.hasValue) {
        ref
          ..invalidate(activityProvider(id))
          ..invalidate(pmcProvider)
          ..invalidate(activitiesProvider);
      }
    });

    return Scaffold(
      appBar: AppBar(title: Text(act.value?['name'] as String? ?? 'Aktivität')),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: ListView(padding: const EdgeInsets.all(16), children: [
            act.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Text(errorMessage(e)),
              data: (a) => _Facts(a: a),
            ),
            const SizedBox(height: 24),
            streams.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(32),
                child: Column(children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 12),
                  Text('Lade Details von Strava …'),
                ]),
              ),
              error: (e, _) => Text(errorMessage(e)),
              data: (s) => _Charts(streams: s),
            ),
          ]),
        ),
      ),
    );
  }
}

class _Facts extends StatelessWidget {
  const _Facts({required this.a});
  final Json a;

  @override
  Widget build(BuildContext context) {
    String n(String k, [String unit = '', int digits = 0]) =>
        a[k] == null ? '–' : '${(a[k] as num).toStringAsFixed(digits)}$unit';
    final date = DateFormat('EEEE, d. MMMM yyyy', 'de').format(DateTime.parse(a['start_time'] as String));
    final items = <(String, String)>[
      ('Dauer', formatDuration(a['duration_s'] as num)),
      ('Distanz', formatKm(a['distance_m'] as num)),
      ('Höhenmeter', n('elevation_m', ' m')),
      ('Ø Leistung', n('avg_power', ' W')),
      ('NP', n('norm_power', ' W')),
      ('IF', n('intensity_factor', '', 2)),
      ('TSS', n('tss')),
      ('Ø Puls', n('avg_hr', ' bpm')),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(date, style: Theme.of(context).textTheme.bodyMedium),
      const SizedBox(height: 12),
      Wrap(spacing: 12, runSpacing: 12, children: [
        for (final i in items)
          SizedBox(
            width: 130,
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(i.$1, style: Theme.of(context).textTheme.labelMedium),
                  const SizedBox(height: 4),
                  Text(i.$2, style: Theme.of(context).textTheme.titleMedium),
                ]),
              ),
            ),
          ),
      ]),
    ]);
  }
}

class _Charts extends StatelessWidget {
  const _Charts({required this.streams});
  final Json streams;

  List<FlSpot> _spots(String key) {
    final t = (streams['time'] as List?) ?? const [];
    final v = (streams[key] as List?) ?? const [];
    return [
      for (var i = 0; i < v.length && i < t.length; i++)
        if (v[i] != null) FlSpot((t[i] as num) / 60, (v[i] as num).toDouble()),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final charts = <(String, String, Color)>[
      ('watts', 'Leistung (W)', const Color(0xFF2E7DD7)),
      ('heartrate', 'Puls (bpm)', const Color(0xFFD6336C)),
      ('altitude', 'Höhe (m)', const Color(0xFF6B7B8C)),
    ].where((c) => _spots(c.$1).isNotEmpty).toList();
    if (charts.isEmpty) return const Text('Für diese Aktivität gibt es keine Sensordaten.');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final c in charts) ...[
        Text(c.$2, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        SizedBox(
          height: 160,
          child: LineChart(LineChartData(
            lineBarsData: [
              LineChartBarData(
                spots: _spots(c.$1),
                color: c.$3,
                barWidth: 1.5,
                dotData: const FlDotData(show: false),
              ),
            ],
            gridData: const FlGridData(drawVerticalLine: false),
            borderData: FlBorderData(show: false),
            titlesData: FlTitlesData(
              topTitles: const AxisTitles(),
              rightTitles: const AxisTitles(),
              leftTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 36,
                  getTitlesWidget: (v, meta) => (v == meta.min || v == meta.max)
                      ? const SizedBox.shrink()
                      : Text(v.round().toString(),
                          style: Theme.of(context).textTheme.labelSmall),
                ),
              ),
              bottomTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 24,
                  getTitlesWidget: (v, meta) => (v == meta.min || v == meta.max)
                      ? const SizedBox.shrink()
                      : Text(v.round().toString(),
                          style: Theme.of(context).textTheme.labelSmall),
                ),
              ),
            ),
          )),
        ),
        const SizedBox(height: 4),
        Text('Minuten', style: Theme.of(context).textTheme.labelSmall),
        const SizedBox(height: 20),
      ],
    ]);
  }
}
