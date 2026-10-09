import 'dart:async';
import 'dart:math' as math;

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
  List<Json>? _strength; // Krafttraining: Uebungen (hier nur angezeigt, der Coach plant sie)
  num? _strengthDuration;
  bool _done = false; // Krafttraining von Hand als erledigt markiert
  bool _skipped = false;
  bool _heat = false;
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
      _heat = w['heat'] == true;
      _done = w['status'] == 'completed';
      final st = w['structure'] as List?;
      if (w['kind'] == 'strength') {
        _strength = [for (final s in st ?? const []) Json.from(s as Map)];
        _strengthDuration = w['planned_duration_s'] as num?;
        _steps = [];
        return;
      }
      _steps = [for (final s in st ?? const []) StepNode.fromJson(Json.from(s as Map))];
      if (st == null) {
        if (w['planned_duration_s'] != null) {
          _manualMin.text = ((w['planned_duration_s'] as num) / 60).round().toString();
        }
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

  void _moveStep(int from, int to) {
    _steps.insert(to, _steps.removeAt(from));
    _changed();
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
    final structure = _strength ?? _structure();
    if (structure == null) return _toast('Bitte alle Schritte prüfen (Dauer ≥ 5 s, Leistung 20–250 %)');
    final body = <String, dynamic>{
      'date': isoDay(_date),
      'title': _title.text.trim(),
      'description': _desc.text.trim().isEmpty ? null : _desc.text.trim(),
      'status': _skipped ? 'skipped' : (_strength != null && _done ? 'completed' : 'planned'),
      'heat': _heat,
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
      if (mounted) context.go('/calendar');
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
        title: Text(MediaQuery.sizeOf(context).width < 600
            ? (_isEdit ? 'Bearbeiten' : 'Neu')
            : (_isEdit ? 'Training bearbeiten' : 'Neues Training')),
        leading: BackButton(onPressed: _close),
        actions: [
          if (_isEdit) ...[
            IconButton(tooltip: 'Kopieren', onPressed: _duplicate, icon: const Icon(Icons.copy_rounded)),
            IconButton(tooltip: 'Löschen', onPressed: _delete, icon: const Icon(Icons.delete_outline_rounded)),
          ],
          Padding(
            padding: const EdgeInsets.only(right: Gap.md, left: Gap.xs),
            child: FilledButton(
              style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Speichern'),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _loadError != null
          ? Center(child: StatusMessage.error(_loadError!))
          : PageBody(
              maxWidth: 820,
              children: [
                SurfaceCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextField(
                        controller: _title,
                        style: t.textTheme.titleMedium,
                        decoration: const InputDecoration(labelText: 'Titel', prefixIcon: Icon(Icons.title_rounded)),
                      ),
                      const SizedBox(height: Gap.md),
                      InkWell(
                        borderRadius: BorderRadius.circular(Radii.md),
                        onTap: () async {
                          final d = await showDatePicker(
                            context: context,
                            initialDate: _date,
                            firstDate: DateTime(2000),
                            lastDate: DateTime(2100),
                          );
                          if (d != null) setState(() => _date = d);
                        },
                        child: InputDecorator(
                          decoration: const InputDecoration(labelText: 'Datum', prefixIcon: Icon(Icons.event_rounded)),
                          child: Text(DateFormat('EEEE, d. MMMM yyyy', 'de').format(_date)),
                        ),
                      ),
                      const SizedBox(height: Gap.md),
                      TextField(
                        controller: _desc,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Beschreibung (optional)',
                          alignLabelWithHint: true,
                        ),
                      ),
                      if (_strength == null) ...[
                        const SizedBox(height: Gap.sm),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Hitzetraining'),
                          subtitle: const Text('Einheit eines Hitze-Blocks: Die Analyse wertet den höheren Puls nicht als Ermüdung'),
                          value: _heat,
                          onChanged: (v) => setState(() => _heat = v),
                        ),
                      ],
                      if (_isEdit && _strength != null) ...[
                        const SizedBox(height: Gap.sm),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Erledigt'),
                          subtitle: const Text('Krafttraining kommt nicht von Strava, markiere es hier selbst'),
                          value: _done && !_skipped,
                          onChanged: (v) => setState(() {
                            _done = v;
                            if (v) _skipped = false;
                          }),
                        ),
                      ],
                      if (_isEdit) ...[
                        const SizedBox(height: Gap.sm),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Ausgelassen'),
                          subtitle: const Text('Zählt nicht mehr zur geplanten Wochenbelastung'),
                          value: _skipped,
                          onChanged: (v) => setState(() {
                            _skipped = v;
                            if (v) _done = false;
                          }),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: Gap.xl),
                if (_strength != null)
                  StrengthPlan(exercises: _strength!, durationS: _strengthDuration)
                else ...[
                const SectionHeader(title: 'Vorlagen', subtitle: 'Antippen, um den Ablauf zu übernehmen'),
                SizedBox(
                  height: 92,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    children: [
                      for (final e in workoutPresets().entries) ...[
                        _PresetCard(name: e.key, steps: e.value, onTap: () => _applyPreset(e.key, e.value)),
                        const SizedBox(width: Gap.sm),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: Gap.xl),
                if (_steps.isNotEmpty) ...[
                  SurfaceCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SectionHeader(title: 'Profil', subtitle: 'Leistung in % der FTP, Farbe = Zone'),
                        SizedBox(
                          height: 170,
                          child: WorkoutProfile(structure: _structure(), onMove: _moveStep),
                        ),
                        const SizedBox(height: Gap.lg),
                        WorkoutSummary(summary: _summary),
                      ],
                    ),
                  ),
                  const SizedBox(height: Gap.xl),
                ],
                SectionHeader(
                  title: 'Ablauf',
                  subtitle: 'Leistung in % der FTP',
                  trailing: Wrap(
                    spacing: Gap.sm,
                    children: [
                      OutlinedButton.icon(
                        onPressed: () {
                          _steps.add(StepNode.leaf());
                          _changed();
                        },
                        icon: const Icon(Icons.add_rounded, size: 18),
                        label: const Text('Schritt'),
                      ),
                      OutlinedButton.icon(
                        onPressed: () {
                          _steps.add(
                            StepNode.group(
                              children: [
                                StepNode.leaf(type: 'interval', minutes: 5, low: 105),
                                StepNode.leaf(type: 'rest', minutes: 5, low: 55),
                              ],
                            ),
                          );
                          _changed();
                        },
                        icon: const Icon(Icons.repeat_rounded, size: 18),
                        label: const Text('Wiederholung'),
                      ),
                    ],
                  ),
                ),
                if (_steps.isEmpty)
                  SurfaceCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Ohne Ablauf kannst Du Dauer und Belastung selbst schätzen:',
                          style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: Gap.md),
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: _manualMin,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(
                                  labelText: 'Dauer',
                                  suffixText: 'min',
                                  prefixIcon: Icon(Icons.schedule_rounded),
                                ),
                              ),
                            ),
                            const SizedBox(width: Gap.md),
                            Expanded(
                              child: TextField(
                                controller: _manualTss,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(
                                  labelText: 'TSS (geschätzt)',
                                  prefixIcon: Icon(Icons.fitness_center_rounded),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  )
                else
                  _StepList(
                    steps: _steps,
                    onChanged: _changed,
                    onRemoved: (s) {
                      _steps.remove(s);
                      s.dispose();
                      _changed();
                    },
                  ),
                ],
              ],
            ),
    );
  }
}

/// Vorlage als kleine Karte mit Mini-Profil.
class _PresetCard extends StatelessWidget {
  const _PresetCard({required this.name, required this.steps, required this.onTap});
  final String name;
  final List<Map<String, dynamic>> steps;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 160,
    child: SurfaceCard(
      padding: const EdgeInsets.all(Gap.md),
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(name, style: Theme.of(context).textTheme.labelLarge, maxLines: 1, overflow: TextOverflow.ellipsis),
          const SizedBox(height: Gap.sm),
          Expanded(child: WorkoutProfile(structure: steps, mini: true)),
        ],
      ),
    ),
  );
}

class WorkoutSummary extends StatelessWidget {
  const WorkoutSummary({super.key, required this.summary});
  final Json? summary;

  @override
  Widget build(BuildContext context) {
    final s = summary;
    final t = Theme.of(context);
    if (s == null) {
      return Text(
        'Kennzahlen werden berechnet …',
        style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant),
      );
    }
    final items = [
      ('Dauer', formatDuration(s['duration_s'] as num), Icons.schedule_rounded, t.colorScheme.primary),
      ('TSS', '${(s['tss'] as num).round()}', Icons.fitness_center_rounded, AppColors.tsb),
      (
        'IF',
        (s['intensity_factor'] as num).toStringAsFixed(2),
        Icons.speed_rounded,
        AppColors.zoneColor((s['intensity_factor'] as num) * 100),
      ),
      ('NP', '${(s['np'] as num).round()} W', Icons.electric_bolt_rounded, AppColors.power),
    ];
    return ResponsiveGrid(
      minItemWidth: 120,
      spacing: Gap.sm,
      children: [for (final i in items) MetricTile(compact: true, label: i.$1, value: i.$2, icon: i.$3, color: i.$4)],
    );
  }
}

class _StepList extends StatelessWidget {
  const _StepList({required this.steps, required this.onChanged, required this.onRemoved});
  final List<StepNode> steps;
  final VoidCallback onChanged;
  final void Function(StepNode) onRemoved;

  @override
  Widget build(BuildContext context) => ReorderableListView(
    shrinkWrap: true,
    physics: const NeverScrollableScrollPhysics(),
    buildDefaultDragHandles: false,
    onReorderItem: (from, to) {
      steps.insert(to, steps.removeAt(from));
      onChanged();
    },
    children: [
      for (var i = 0; i < steps.length; i++)
        KeyedSubtree(
          key: ObjectKey(steps[i]),
          child: steps[i].isGroup
              ? _GroupCard(index: i, node: steps[i], onChanged: onChanged, onRemove: () => onRemoved(steps[i]))
              : _LeafRow(index: i, node: steps[i], onChanged: onChanged, onRemove: () => onRemoved(steps[i])),
        ),
    ],
  );
}

/// Anfasser zum Verschieben eines Blocks in der Liste.
Widget _dragHandle(int index) => ReorderableDragStartListener(
  index: index,
  child: const MouseRegion(
    cursor: SystemMouseCursors.grab,
    child: Padding(padding: EdgeInsets.all(Gap.xs), child: Icon(Icons.drag_indicator_rounded)),
  ),
);

class _LeafRow extends StatelessWidget {
  const _LeafRow({required this.index, required this.node, required this.onChanged, required this.onRemove});
  final int index;
  final StepNode node;
  final VoidCallback onChanged;
  final VoidCallback onRemove;

  InputDecoration _dec(String label, [String? suffix]) =>
      InputDecoration(labelText: label, isDense: true, suffixText: suffix);

  @override
  Widget build(BuildContext context) {
    final num = const TextInputType.numberWithOptions(decimal: true);
    final t = Theme.of(context);
    final lo = double.tryParse(node.low.text.replaceAll(',', '.'));
    final hi = node.isRamp ? double.tryParse(node.high.text.replaceAll(',', '.')) : lo;
    final color = (lo == null || hi == null) ? t.colorScheme.outline : AppColors.zoneColor((lo + hi) / 2);
    // Abgerundeter Rahmen aussen, farbiger Zonenstreifen innen (gemischte Rahmenfarben vertragen keinen Radius)
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: t.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(Radii.md),
        border: Border.all(color: t.colorScheme.outlineVariant),
      ),
      child: Container(
        padding: const EdgeInsets.fromLTRB(Gap.md, Gap.sm, Gap.xs, Gap.sm),
        decoration: BoxDecoration(
          border: Border(left: BorderSide(color: color, width: 4)),
        ),
        child: LayoutBuilder(
          builder: (context, c) {
            final type = DropdownButtonFormField<String>(
              initialValue: node.type,
              isExpanded: true,
              decoration: _dec('Art'),
              items: [for (final e in StepNode.types.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
              onChanged: (v) {
                if (v == null) return;
                node.type = v;
                onChanged();
              },
            );
            final remove = IconButton(tooltip: 'Entfernen', onPressed: onRemove, icon: const Icon(Icons.close_rounded));
            final values = _values(num);
            if (c.maxWidth < 480) {
              return Column(
                children: [
                  Row(
                    children: [
                      _dragHandle(index),
                      Expanded(child: type),
                      remove,
                    ],
                  ),
                  const SizedBox(height: Gap.sm),
                  Padding(
                    padding: const EdgeInsets.only(right: Gap.sm),
                    child: Row(children: values),
                  ),
                ],
              );
            }
            return Row(
              children: [
                _dragHandle(index),
                SizedBox(width: 150, child: type),
                const SizedBox(width: Gap.sm),
                ...values,
                remove,
              ],
            );
          },
        ),
      ),
    );
  }

  List<Widget> _values(TextInputType num) => [
    Expanded(
      child: TextField(
        controller: node.dur,
        keyboardType: num,
        decoration: _dec('Dauer', 'min'),
        onChanged: (_) => onChanged(),
      ),
    ),
    const SizedBox(width: Gap.sm),
    Expanded(
      child: TextField(
        controller: node.low,
        keyboardType: num,
        decoration: _dec(node.isRamp ? 'von' : 'Leistung', '%'),
        onChanged: (_) => onChanged(),
      ),
    ),
    if (node.isRamp) ...[
      const SizedBox(width: Gap.sm),
      Expanded(
        child: TextField(
          controller: node.high,
          keyboardType: num,
          decoration: _dec('bis', '%'),
          onChanged: (_) => onChanged(),
        ),
      ),
    ],
  ];
}

class _GroupCard extends StatelessWidget {
  const _GroupCard({required this.index, required this.node, required this.onChanged, required this.onRemove});
  final int index;
  final StepNode node;
  final VoidCallback onChanged;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
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
          Row(
            children: [
              _dragHandle(index),
              Icon(Icons.repeat_rounded, color: t.colorScheme.primary),
              const SizedBox(width: Gap.sm),
              Text('Wiederholen', style: t.textTheme.titleSmall),
              const SizedBox(width: Gap.md),
              SizedBox(
                width: 80,
                child: TextField(
                  controller: node.count,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(isDense: true, suffixText: '×'),
                  onChanged: (_) => onChanged(),
                ),
              ),
              const Spacer(),
              IconButton(tooltip: 'Gruppe entfernen', onPressed: onRemove, icon: const Icon(Icons.close_rounded)),
            ],
          ),
          const SizedBox(height: Gap.xs),
          _StepList(
            steps: node.children,
            onChanged: onChanged,
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
              icon: const Icon(Icons.add_rounded),
              label: const Text('Schritt in Gruppe'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Ein Abschnitt des Profils: Start, Dauer (s) und Leistung am Anfang/Ende (% FTP).
/// `top` ist der Index des Blocks auf oberster Ebene (fuer Drag and Drop im Graph).
typedef _Seg = (double start, double secs, double from, double to, int top);

List<_Seg> _segments(List<Map<String, dynamic>> structure) {
  final out = <_Seg>[];
  var t = 0.0;
  var top = 0;
  void leaf(Map<String, dynamic> l) {
    final secs = (l['duration_s'] as num).toDouble();
    final p = (l['power_pct'] as List).cast<num>();
    final ramp = l['type'] == 'warmup' || l['type'] == 'cooldown';
    final a = ramp ? p[0].toDouble() : (p[0] + p[1]) / 2;
    final b = ramp ? p[1].toDouble() : a;
    out.add((t, secs, a.toDouble(), b.toDouble(), top));
    t += secs;
  }

  for (final s in structure) {
    if (s['type'] == 'repeat') {
      for (var i = 0; i < (s['count'] as num); i++) {
        for (final l in s['steps'] as List) {
          leaf(Map<String, dynamic>.from(l as Map));
        }
      }
    } else {
      leaf(s);
    }
    top++;
  }
  return out;
}

/// Blockprofil des Workouts; jede Stufe in der Farbe ihrer Leistungszone.
/// Mit [onMove] lassen sich Bloecke (auf oberster Ebene) per Ziehen verschieben.
class WorkoutProfile extends StatefulWidget {
  const WorkoutProfile({super.key, required this.structure, this.mini = false, this.onMove});
  final List<Map<String, dynamic>>? structure;
  final bool mini;
  final void Function(int from, int to)? onMove;

  @override
  State<WorkoutProfile> createState() => _WorkoutProfileState();
}

class _WorkoutProfileState extends State<WorkoutProfile> {
  int? _from; // gezogener Block
  int? _to; // Ziel-Block unter dem Finger

  /// Block auf oberster Ebene an Position [dx] (Pixel) ermitteln.
  int _topAt(List<_Seg> segs, double dx, double width) {
    final total = segs.last.$1 + segs.last.$2;
    final secs = (dx / width * total).clamp(0.0, total - 0.001);
    return segs.firstWhere((s) => secs >= s.$1 && secs < s.$1 + s.$2, orElse: () => segs.last).$5;
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final structure = widget.structure;
    if (structure == null || structure.isEmpty) {
      return Center(
        child: Text(
          'Ungültige Eingabe, bitte Schritte prüfen.',
          style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.error),
        ),
      );
    }
    final segs = _segments(structure);
    final total = segs.last.$1 + segs.last.$2;
    final painter = _ProfilePainter(
      segs: segs,
      grid: t.colorScheme.outlineVariant,
      ftpLine: t.colorScheme.onSurfaceVariant,
      mini: widget.mini,
      accent: t.colorScheme.primary,
      dragFrom: _from,
      dragTo: _to,
    );
    if (widget.mini) return CustomPaint(painter: painter, size: Size.infinite);

    Widget chart(double width) {
      final paint = CustomPaint(painter: painter, size: Size.infinite);
      if (widget.onMove == null) return paint;
      void end() {
        final from = _from, to = _to;
        setState(() => _from = _to = null);
        if (from != null && to != null && from != to) widget.onMove!(from, to);
      }

      return MouseRegion(
        cursor: _from != null ? SystemMouseCursors.grabbing : SystemMouseCursors.grab,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onHorizontalDragStart: (d) => setState(() => _from = _to = _topAt(segs, d.localPosition.dx, width)),
          onHorizontalDragUpdate: (d) => setState(() => _to = _topAt(segs, d.localPosition.dx, width)),
          onHorizontalDragEnd: (_) => end(),
          onHorizontalDragCancel: () => setState(() => _from = _to = null),
          child: paint,
        ),
      );
    }

    final axis = t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant);
    return Column(
      children: [
        Expanded(child: LayoutBuilder(builder: (_, box) => chart(box.maxWidth))),
        const SizedBox(height: 6),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('0′', style: axis),
            Text(formatDuration(total / 2), style: axis),
            Text(formatDuration(total), style: axis),
          ],
        ),
      ],
    );
  }
}

class _ProfilePainter extends CustomPainter {
  _ProfilePainter({
    required this.segs,
    required this.grid,
    required this.ftpLine,
    required this.mini,
    required this.accent,
    this.dragFrom,
    this.dragTo,
  });
  final List<_Seg> segs;
  final Color grid;
  final Color ftpLine;
  final bool mini;
  final Color accent;
  final int? dragFrom, dragTo;

  @override
  void paint(Canvas canvas, Size size) {
    if (segs.isEmpty || size.width <= 0) return;
    final total = segs.last.$1 + segs.last.$2;
    final peak = segs.map((s) => math.max(s.$3, s.$4)).reduce(math.max);
    final maxY = math.max(mini ? 120.0 : 130.0, peak * 1.1);
    double x(double secs) => secs / total * size.width;
    double y(double pct) => size.height - pct / maxY * size.height;

    if (!mini) {
      final gp = Paint()
        ..color = grid
        ..strokeWidth = 1;
      for (final pct in [50, 100, 150, 200]) {
        if (pct > maxY) break;
        canvas.drawLine(Offset(0, y(pct.toDouble())), Offset(size.width, y(pct.toDouble())), gp);
      }
    }

    final gap = mini ? 0.0 : math.min(1.5, size.width / segs.length * 0.15);
    for (final s in segs) {
      final l = x(s.$1) + gap / 2, r = x(s.$1 + s.$2) - gap / 2;
      if (r <= l) continue;
      final path = Path()
        ..moveTo(l, size.height)
        ..lineTo(l, y(s.$3))
        ..lineTo(r, y(s.$4))
        ..lineTo(r, size.height)
        ..close();
      final c = AppColors.zoneColor((s.$3 + s.$4) / 2);
      final alpha = mini ? 0.9 : (s.$5 == dragFrom ? 0.4 : 0.85);
      canvas.drawPath(path, Paint()..color = c.withValues(alpha: alpha));
    }

    // Einfuegemarke: vor dem Ziel-Block beim Ziehen nach links, dahinter beim Ziehen nach rechts
    if (dragFrom != null && dragTo != null && dragFrom != dragTo) {
      final target = segs.where((s) => s.$5 == dragTo);
      final secs = dragTo! > dragFrom! ? target.last.$1 + target.last.$2 : target.first.$1;
      final mx = x(secs).clamp(1.5, size.width - 1.5);
      canvas.drawLine(
        Offset(mx, 0),
        Offset(mx, size.height),
        Paint()
          ..color = accent
          ..strokeWidth = 3,
      );
    }

    if (!mini) {
      // FTP-Linie bei 100 %
      final fy = y(100);
      final dash = Paint()
        ..color = ftpLine.withValues(alpha: 0.7)
        ..strokeWidth = 1.2;
      for (var dx = 0.0; dx < size.width; dx += 9) {
        canvas.drawLine(Offset(dx, fy), Offset(math.min(dx + 5, size.width), fy), dash);
      }
      final tp = TextPainter(
        text: TextSpan(
          text: 'FTP',
          style: TextStyle(color: ftpLine, fontSize: 10, fontWeight: FontWeight.w700),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(size.width - tp.width, fy - tp.height - 2));
    }
  }

  @override
  bool shouldRepaint(_ProfilePainter old) =>
      old.segs != segs ||
      old.grid != grid ||
      old.ftpLine != ftpLine ||
      old.mini != mini ||
      old.dragFrom != dragFrom ||
      old.dragTo != dragTo;
}
