import 'dart:async';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import 'step_node.dart';

class WorkoutEditorScreen extends ConsumerStatefulWidget {
  const WorkoutEditorScreen({super.key, this.id, this.initialDate});
  final int? id;
  final DateTime? initialDate;

  @override
  ConsumerState<WorkoutEditorScreen> createState() => _WorkoutEditorScreenState();
}

class _WorkoutEditorScreenState extends ConsumerState<WorkoutEditorScreen> {
  final _title = TextEditingController();
  final _desc = TextEditingController();
  final _manualMin = TextEditingController();
  final _manualTss = TextEditingController();
  late DateTime _date = widget.initialDate ?? DateTime.now();
  List<StepNode> _steps = [];
  bool _skipped = false;
  bool _loading = false;
  bool _saving = false;
  String? _loadError;
  Json? _summary; // Ergebnis der Server-Vorschau (TSS, IF, NP, Dauer)
  Timer? _debounce;

  bool get _isEdit => widget.id != null;

  @override
  void initState() {
    super.initState();
    if (_isEdit) _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    for (final c in [_title, _desc, _manualMin, _manualTss]) {
      c.dispose();
    }
    for (final s in _steps) {
      s.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final r = await ref.read(apiProvider).dio.get('/workouts/${widget.id}');
      final w = Json.from(r.data as Map);
      _title.text = w['title'] as String;
      _desc.text = (w['description'] as String?) ?? '';
      _date = DateTime.parse(w['date'] as String);
      _skipped = w['status'] == 'skipped';
      final st = w['structure'] as List?;
      _steps = [for (final s in st ?? const []) StepNode.fromJson(Json.from(s as Map))];
      if (st == null) {
        if (w['planned_duration_s'] != null) _manualMin.text = ((w['planned_duration_s'] as num) / 60).round().toString();
        if (w['planned_tss'] != null) _manualTss.text = (w['planned_tss'] as num).round().toString();
      }
      _schedulePreview();
    } catch (e) {
      _loadError = errorMessage(e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<Map<String, dynamic>>? _structure() {
    final out = [for (final s in _steps) s.toJson()];
    return out.any((s) => s == null) ? null : out.cast<Map<String, dynamic>>();
  }

  void _changed() {
    setState(() {});
    _schedulePreview();
  }

  void _schedulePreview() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      final s = _structure();
      if (s == null || s.isEmpty) {
        if (mounted) setState(() => _summary = null);
        return;
      }
      try {
        final r = await ref.read(apiProvider).dio.post('/workouts/preview', data: {'structure': s});
        if (mounted) setState(() => _summary = Json.from(r.data as Map));
      } catch (_) {
        if (mounted) setState(() => _summary = null);
      }
    });
  }

  /// Zurueck zum Kalender, auch wenn die Seite direkt per Link geoeffnet wurde.
  void _close() => context.canPop() ? context.pop() : context.go('/calendar');

  void _toast(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _save() async {
    if (_title.text.trim().isEmpty) return _toast('Bitte einen Titel eingeben');
    final structure = _structure();
    if (structure == null) return _toast('Bitte alle Schritte prüfen (Dauer ≥ 5 s, Leistung 20–250 %)');
    final body = <String, dynamic>{
      'date': isoDay(_date),
      'title': _title.text.trim(),
      'description': _desc.text.trim().isEmpty ? null : _desc.text.trim(),
      'status': _skipped ? 'skipped' : 'planned',
    };
    if (structure.isNotEmpty) {
      body['structure'] = structure;
    } else {
      final m = double.tryParse(_manualMin.text.replaceAll(',', '.'));
      final t = double.tryParse(_manualTss.text.replaceAll(',', '.'));
      if (m != null) body['planned_duration_s'] = (m * 60).round();
      if (t != null) body['planned_tss'] = t;
    }
    setState(() => _saving = true);
    try {
      final dio = ref.read(apiProvider).dio;
      await (_isEdit ? dio.put('/workouts/${widget.id}', data: body) : dio.post('/workouts', data: body));
      ref.invalidate(calendarProvider);
      if (mounted) _close();
    } catch (e) {
      if (mounted) _toast(errorMessage(e));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Training löschen?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Löschen')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(apiProvider).dio.delete('/workouts/${widget.id}');
      ref.invalidate(calendarProvider);
      if (mounted) _close();
    } catch (e) {
      if (mounted) _toast(errorMessage(e));
    }
  }

  Future<void> _duplicate() async {
    final d = await showDatePicker(
      context: context,
      initialDate: _date.add(const Duration(days: 7)),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
      helpText: 'Kopieren auf …',
    );
    if (d == null) return;
    try {
      await ref.read(apiProvider).dio.post('/workouts/${widget.id}/copy', queryParameters: {'date': isoDay(d)});
      ref.invalidate(calendarProvider);
      _toast('Kopiert auf ${DateFormat('d.M.yyyy').format(d)}');
    } catch (e) {
      _toast(errorMessage(e));
    }
  }

  void _applyPreset(String name, List<Map<String, dynamic>> json) {
    for (final s in _steps) {
      s.dispose();
    }
    _steps = [for (final j in json) StepNode.fromJson(j)];
    if (_title.text.trim().isEmpty) _title.text = name;
    _changed();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEdit ? 'Training bearbeiten' : 'Neues Training'),
        actions: [
          if (_isEdit) ...[
            IconButton(tooltip: 'Kopieren', onPressed: _duplicate, icon: const Icon(Icons.copy)),
            IconButton(tooltip: 'Löschen', onPressed: _delete, icon: const Icon(Icons.delete_outline)),
          ],
          TextButton(onPressed: _saving ? null : _save, child: const Text('Speichern')),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _loadError != null
              ? Center(child: Text(_loadError!))
              : Align(
                  alignment: Alignment.topCenter,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 720),
                    child: ListView(padding: const EdgeInsets.all(16), children: [
                      TextField(controller: _title, decoration: const InputDecoration(labelText: 'Titel')),
                      const SizedBox(height: 12),
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.event),
                        title: Text(DateFormat('EEEE, d. MMMM yyyy', 'de').format(_date)),
                        onTap: () async {
                          final d = await showDatePicker(
                              context: context, initialDate: _date, firstDate: DateTime(2000), lastDate: DateTime(2100));
                          if (d != null) setState(() => _date = d);
                        },
                      ),
                      TextField(
                          controller: _desc,
                          maxLines: 3,
                          decoration: const InputDecoration(labelText: 'Beschreibung (optional)')),
                      const SizedBox(height: 20),
                      Text('Vorlage', style: t.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      Wrap(spacing: 8, runSpacing: 8, children: [
                        for (final e in workoutPresets().entries)
                          ActionChip(label: Text(e.key), onPressed: () => _applyPreset(e.key, e.value)),
                      ]),
                      const SizedBox(height: 20),
                      Text('Ablauf (Leistung in % der FTP)', style: t.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      _StepList(
                        steps: _steps,
                        onChanged: _changed,
                        onRemoved: (s) {
                          _steps.remove(s);
                          s.dispose();
                          _changed();
                        },
                      ),
                      Wrap(spacing: 8, children: [
                        OutlinedButton.icon(
                            onPressed: () {
                              _steps.add(StepNode.leaf());
                              _changed();
                            },
                            icon: const Icon(Icons.add),
                            label: const Text('Schritt')),
                        OutlinedButton.icon(
                            onPressed: () {
                              _steps.add(StepNode.group(children: [
                                StepNode.leaf(type: 'interval', minutes: 5, low: 105),
                                StepNode.leaf(type: 'rest', minutes: 5, low: 55),
                              ]));
                              _changed();
                            },
                            icon: const Icon(Icons.repeat),
                            label: const Text('Wiederholung')),
                      ]),
                      const SizedBox(height: 20),
                      if (_steps.isEmpty) ...[
                        Text('Ohne Ablauf kannst du Dauer und Belastung selbst schätzen:', style: t.textTheme.bodySmall),
                        const SizedBox(height: 8),
                        Row(children: [
                          Expanded(
                              child: TextField(
                                  controller: _manualMin,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(labelText: 'Dauer (min)'))),
                          const SizedBox(width: 12),
                          Expanded(
                              child: TextField(
                                  controller: _manualTss,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(labelText: 'TSS (geschätzt)'))),
                        ]),
                      ] else ...[
                        SizedBox(height: 160, child: _Preview(structure: _structure())),
                        const SizedBox(height: 8),
                        _SummaryLine(summary: _summary),
                      ],
                      if (_isEdit)
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Ausgelassen'),
                          value: _skipped,
                          onChanged: (v) => setState(() => _skipped = v),
                        ),
                      const SizedBox(height: 24),
                      FilledButton(
                          onPressed: _saving ? null : _save,
                          child: _saving
                              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                              : const Text('Speichern')),
                    ]),
                  ),
                ),
    );
  }
}

class _SummaryLine extends StatelessWidget {
  const _SummaryLine({required this.summary});
  final Json? summary;

  @override
  Widget build(BuildContext context) {
    final s = summary;
    if (s == null) return Text('Vorschau wird berechnet …', style: Theme.of(context).textTheme.bodySmall);
    return Text(
      '${formatDuration(s['duration_s'] as num)} · ${(s['tss'] as num).round()} TSS · '
      'IF ${(s['intensity_factor'] as num).toStringAsFixed(2)} · NP ${(s['np'] as num).round()} W',
      style: Theme.of(context).textTheme.titleSmall,
    );
  }
}

class _StepList extends StatelessWidget {
  const _StepList({required this.steps, required this.onChanged, required this.onRemoved, this.nested = false});
  final List<StepNode> steps;
  final VoidCallback onChanged;
  final void Function(StepNode) onRemoved;
  final bool nested;

  @override
  Widget build(BuildContext context) => Column(children: [
        for (final s in steps)
          s.isGroup
              ? _GroupCard(node: s, onChanged: onChanged, onRemove: () => onRemoved(s))
              : _LeafRow(node: s, onChanged: onChanged, onRemove: () => onRemoved(s)),
      ]);
}

class _LeafRow extends StatelessWidget {
  const _LeafRow({required this.node, required this.onChanged, required this.onRemove});
  final StepNode node;
  final VoidCallback onChanged;
  final VoidCallback onRemove;

  InputDecoration _dec(String label) =>
      InputDecoration(labelText: label, isDense: true, border: const OutlineInputBorder());

  @override
  Widget build(BuildContext context) {
    final num = const TextInputType.numberWithOptions(decimal: true);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        SizedBox(
          width: 140,
          child: DropdownButtonFormField<String>(
            initialValue: node.type,
            isExpanded: true,
            decoration: _dec('Art'),
            items: [for (final e in StepNode.types.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
            onChanged: (v) {
              if (v == null) return;
              node.type = v;
              onChanged();
            },
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
            child: TextField(
                controller: node.dur,
                keyboardType: num,
                decoration: _dec('Minuten'),
                onChanged: (_) => onChanged())),
        const SizedBox(width: 8),
        Expanded(
            child: TextField(
                controller: node.low,
                keyboardType: num,
                decoration: _dec(node.isRamp ? 'von %' : '% FTP'),
                onChanged: (_) => onChanged())),
        if (node.isRamp) ...[
          const SizedBox(width: 8),
          Expanded(
              child: TextField(
                  controller: node.high,
                  keyboardType: num,
                  decoration: _dec('bis %'),
                  onChanged: (_) => onChanged())),
        ],
        IconButton(tooltip: 'Entfernen', onPressed: onRemove, icon: const Icon(Icons.close)),
      ]),
    );
  }
}

class _GroupCard extends StatelessWidget {
  const _GroupCard({required this.node, required this.onChanged, required this.onRemove});
  final StepNode node;
  final VoidCallback onChanged;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            const Icon(Icons.repeat),
            const SizedBox(width: 8),
            const Text('Wiederholen'),
            const SizedBox(width: 12),
            SizedBox(
              width: 70,
              child: TextField(
                controller: node.count,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(isDense: true, border: OutlineInputBorder(), suffixText: '×'),
                onChanged: (_) => onChanged(),
              ),
            ),
            const Spacer(),
            IconButton(tooltip: 'Gruppe entfernen', onPressed: onRemove, icon: const Icon(Icons.close)),
          ]),
          _StepList(
            steps: node.children,
            onChanged: onChanged,
            nested: true,
            onRemoved: (s) {
              node.children.remove(s);
              s.dispose();
              onChanged();
            },
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () {
                node.children.add(StepNode.leaf());
                onChanged();
              },
              icon: const Icon(Icons.add),
              label: const Text('Schritt in Gruppe'),
            ),
          ),
        ]),
      ),
    );
  }
}

/// Treppenprofil des Workouts (Zeit in Minuten, Leistung in % FTP).
class _Preview extends StatelessWidget {
  const _Preview({required this.structure});
  final List<Map<String, dynamic>>? structure;

  List<FlSpot> _spots() {
    final spots = <FlSpot>[];
    var t = 0.0;
    void leaf(Map<String, dynamic> l) {
      final secs = (l['duration_s'] as num).toDouble();
      final p = (l['power_pct'] as List).cast<num>();
      final ramp = l['type'] == 'warmup' || l['type'] == 'cooldown';
      final a = ramp ? p[0].toDouble() : (p[0] + p[1]) / 2;
      final b = ramp ? p[1].toDouble() : a;
      spots
        ..add(FlSpot(t / 60, a))
        ..add(FlSpot((t + secs) / 60, b));
      t += secs;
    }

    for (final s in structure ?? const []) {
      if (s['type'] == 'repeat') {
        for (var i = 0; i < (s['count'] as num); i++) {
          for (final l in s['steps'] as List) {
            leaf(Map<String, dynamic>.from(l as Map));
          }
        }
      } else {
        leaf(s);
      }
    }
    return spots;
  }

  @override
  Widget build(BuildContext context) {
    if (structure == null || structure!.isEmpty) {
      return const Center(child: Text('Ungültige Eingabe, bitte Schritte prüfen.'));
    }
    final c = Theme.of(context).colorScheme.primary;
    return LineChart(LineChartData(
      minY: 0,
      lineBarsData: [
        LineChartBarData(
          spots: _spots(),
          color: c,
          barWidth: 2,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(show: true, color: c.withValues(alpha: 0.25)),
        ),
      ],
      gridData: const FlGridData(drawVerticalLine: false),
      borderData: FlBorderData(show: false),
      lineTouchData: const LineTouchData(enabled: false),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(),
        rightTitles: const AxisTitles(),
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 40,
            getTitlesWidget: (v, meta) => v == meta.max
                ? const SizedBox.shrink()
                : Text('${v.round()}%', style: Theme.of(context).textTheme.labelSmall),
          ),
        ),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 22,
            getTitlesWidget: (v, meta) => v == meta.max
                ? const SizedBox.shrink()
                : Text('${v.round()}′', style: Theme.of(context).textTheme.labelSmall),
          ),
        ),
      ),
    ));
  }
}
