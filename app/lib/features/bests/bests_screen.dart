import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

const _standardDurations = [5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 5400];

/// Schluessel: Zeitraum (ISO oder null) und Dauern, kommagetrennt.
typedef _BestsKey = (String?, String?, String);

final _bestsProvider = FutureProvider.autoDispose.family<Json, _BestsKey>((ref, key) async {
  final r = await ref.watch(apiProvider).dio.get('/metrics/bests', queryParameters: {
    'start': ?key.$1,
    'end': ?key.$2,
    'durations': key.$3,
  });
  return Json.from(r.data as Map);
});

const _levelColors = {
  'hobby': Colors.blueGrey,
  'amateur': Colors.blue,
  'elite': Colors.teal,
  'pro': Colors.orange,
  'worldtour': Colors.purple,
};

enum _Period { week, month, year, all, custom }

/// Bestwerte (beste Durchschnittsleistung je Dauer) in einem Zeitraum, mit Einordnung nach W/kg.
class BestsScreen extends ConsumerStatefulWidget {
  const BestsScreen({super.key});

  @override
  ConsumerState<BestsScreen> createState() => _BestsScreenState();
}

class _BestsScreenState extends ConsumerState<BestsScreen> {
  _Period _period = _Period.year;
  DateTimeRange? _range;
  final List<int> _custom = [];
  final _input = TextEditingController();
  String? _inputError;

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  (DateTime, DateTime)? get _span {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return switch (_period) {
      _Period.week => (today.subtract(Duration(days: today.weekday - 1)), today),
      _Period.month => (DateTime(now.year, now.month), today),
      _Period.year => (DateTime(now.year), today),
      _Period.all => null,
      _Period.custom => _range == null ? null : (_range!.start, _range!.end),
    };
  }

  /// "90", "2:30" (min:s) oder "1:05:00" (h:min:s); eine einzelne Zahl sind Minuten.
  int? _parse(String text) {
    final parts = text.trim().split(':');
    if (parts.isEmpty || parts.length > 3 || parts.any((p) => int.tryParse(p) == null)) return null;
    final n = [for (final p in parts) int.parse(p)];
    return switch (n.length) {
      1 => n[0] * 60,
      2 => n[0] * 60 + n[1],
      _ => n[0] * 3600 + n[1] * 60 + n[2],
    };
  }

  void _add() {
    final s = _parse(_input.text);
    if (s == null || s < 1 || s > 86400) {
      setState(() => _inputError = 'Format: Minuten (20), min:s (2:30) oder h:min:s');
      return;
    }
    setState(() {
      _inputError = null;
      if (!_standardDurations.contains(s) && !_custom.contains(s) && _custom.length < 4) _custom.add(s);
      _input.clear();
    });
  }

  Future<void> _pickRange() async {
    final now = DateTime.now();
    final r = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: now,
      initialDateRange: _range,
    );
    if (r != null) setState(() => _range = r);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final span = _span;
    final durations = [..._standardDurations, ..._custom]..sort();
    final key = (
      span == null ? null : isoDay(span.$1),
      span == null ? null : isoDay(span.$2),
      durations.join(','),
    );
    final data = ref.watch(_bestsProvider(key));
    const labels = {
      _Period.week: 'Diese Woche',
      _Period.month: 'Dieser Monat',
      _Period.year: 'Dieses Jahr',
      _Period.all: 'Gesamt',
      _Period.custom: 'Benutzerdefiniert',
    };
    return Scaffold(
      appBar: AppBar(
        title: const Text('Bestwerte'),
        leading: BackButton(onPressed: () => context.canPop() ? context.pop() : context.go('/')),
      ),
      body: PageBody(
        maxWidth: 820,
        children: [
          Wrap(
            spacing: Gap.sm,
            runSpacing: Gap.sm,
            children: [
              for (final p in _Period.values)
                ChoiceChip(
                  label: Text(
                    p == _Period.custom && _range != null && _period == p
                        ? '${DateFormat('d.M.yy').format(_range!.start)} – ${DateFormat('d.M.yy').format(_range!.end)}'
                        : labels[p]!,
                  ),
                  selected: _period == p,
                  onSelected: (_) async {
                    setState(() => _period = p);
                    if (p == _Period.custom) await _pickRange();
                  },
                ),
            ],
          ),
          const SizedBox(height: Gap.md),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextField(
                  controller: _input,
                  keyboardType: TextInputType.datetime,
                  onSubmitted: (_) => _add(),
                  decoration: InputDecoration(
                    labelText: 'Eigene Dauer',
                    hintText: 'z. B. 8 oder 2:30',
                    isDense: true,
                    errorText: _inputError,
                    prefixIcon: const Icon(Icons.timer_outlined),
                  ),
                ),
              ),
              const SizedBox(width: Gap.sm),
              FilledButton.tonal(onPressed: _add, child: const Text('Hinzufügen')),
            ],
          ),
          if (_custom.isNotEmpty) ...[
            const SizedBox(height: Gap.sm),
            Wrap(
              spacing: Gap.sm,
              children: [
                for (final s in _custom)
                  InputChip(label: Text(shortDuration(s)), onDeleted: () => setState(() => _custom.remove(s))),
              ],
            ),
          ],
          const SizedBox(height: Gap.lg),
          data.when(
            loading: () => const LoadingBlock(height: 320),
            error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(_bestsProvider)),
            data: (d) {
              final efforts = [for (final e in d['efforts'] as List) Json.from(e as Map)];
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (d['weight_kg'] == null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Gap.md),
                      child: Text(
                        'Trage im Profil Dein Gewicht ein, dann zeigt die Seite W/kg und die Einordnung.',
                        style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.primary),
                      ),
                    ),
                  if (efforts.isEmpty)
                    const StatusMessage(
                      icon: Icons.bolt_rounded,
                      title: 'Keine Leistungsdaten',
                      message: 'In diesem Zeitraum gibt es keine Fahrten mit Leistungsmessung.',
                    )
                  else
                    SurfaceCard(
                      padding: EdgeInsets.zero,
                      child: Column(
                        children: [
                          for (var i = 0; i < efforts.length; i++) ...[
                            if (i > 0) Divider(height: 1, color: t.colorScheme.outlineVariant),
                            _EffortRow(e: efforts[i]),
                          ],
                        ],
                      ),
                    ),
                  const SizedBox(height: Gap.md),
                  Text(
                    'Einordnung: Coggan-Leistungsprofil (Training and Racing with a Power Meter, Werte für Männer), '
                    'nur für 5 s bis 60 min und grob auf Hobby bis Worldtour übertragen. '
                    'Zwischen den Stützstellen (5 s, 1, 5, 60 min) geschätzt. Eine weltweite Datenbasis gibt es nicht, '
                    'das ist eine Orientierung, kein Ranking.',
                    style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant),
                  ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _EffortRow extends StatelessWidget {
  const _EffortRow({required this.e});
  final Json e;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final level = e['level'] as String?;
    final color = _levelColors[level] ?? t.colorScheme.outline;
    final date = DateFormat('d. MMM yyyy', 'de').format(DateTime.parse(e['date'] as String));
    return InkWell(
      onTap: () => context.push('/activity/${e['activity_id']}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.md),
        child: Row(
          children: [
            SizedBox(
              width: 64,
              child: Text(shortDuration(e['duration_s'] as int), style: t.textTheme.titleSmall),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(text: '${e['watts']} W', style: t.textTheme.titleMedium),
                        if (e['wkg'] != null)
                          TextSpan(
                            text: '   ${(e['wkg'] as num).toStringAsFixed(2)} W/kg',
                            style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
                          ),
                      ],
                    ),
                  ),
                  Text(
                    date,
                    style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            if (level != null) Pill(label: e['level_label'] as String, color: color),
          ],
        ),
      ),
    );
  }
}
