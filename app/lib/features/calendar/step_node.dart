import 'package:flutter/material.dart';

/// Bearbeitbarer Schritt eines Workouts. Format wie im Backend (app/metrics/workout.py):
/// Einzelschritt oder Wiederholungsgruppe ("repeat") mit Einzelschritten.
class StepNode {
  StepNode.leaf({this.type = 'steady', double minutes = 10, double low = 70, double? high})
      : count = TextEditingController(text: '1'),
        dur = TextEditingController(text: _fmt(minutes)),
        low = TextEditingController(text: _fmt(low)),
        high = TextEditingController(text: _fmt(high ?? low));

  StepNode.group({int count = 3, List<StepNode>? children})
      : type = 'repeat',
        count = TextEditingController(text: '$count'),
        dur = TextEditingController(),
        low = TextEditingController(),
        high = TextEditingController(),
        children = children ?? [];

  factory StepNode.fromJson(Map<String, dynamic> j) {
    if (j['type'] == 'repeat') {
      return StepNode.group(
        count: (j['count'] as num).toInt(),
        children: [for (final s in j['steps'] as List) StepNode.fromJson(Map<String, dynamic>.from(s as Map))],
      );
    }
    final p = (j['power_pct'] as List).cast<num>();
    return StepNode.leaf(
      type: j['type'] as String,
      minutes: (j['duration_s'] as num) / 60,
      low: p[0].toDouble(),
      high: p[1].toDouble(),
    );
  }

  static const types = {
    'warmup': 'Aufwärmen',
    'steady': 'Dauerleistung',
    'interval': 'Intervall',
    'rest': 'Erholung',
    'cooldown': 'Ausfahren',
  };

  String type;
  final TextEditingController count, dur, low, high;
  List<StepNode> children = [];

  bool get isGroup => type == 'repeat';
  bool get isRamp => type == 'warmup' || type == 'cooldown';

  static String _fmt(double v) => v % 1 == 0 ? v.toInt().toString() : v.toString();
  static double? _num(TextEditingController c) => double.tryParse(c.text.trim().replaceAll(',', '.'));

  /// null, wenn Eingaben ungueltig sind.
  Map<String, dynamic>? toJson() {
    if (isGroup) {
      final n = int.tryParse(count.text.trim());
      if (n == null || n < 1 || children.isEmpty) return null;
      final steps = [for (final c in children) c.toJson()];
      if (steps.any((s) => s == null)) return null;
      return {'type': 'repeat', 'count': n, 'steps': steps};
    }
    final m = _num(dur);
    final lo = _num(low);
    final hi = isRamp ? _num(high) : lo;
    if (m == null || lo == null || hi == null) return null;
    final secs = (m * 60).round();
    if (secs < 5) return null;
    return {'type': type, 'duration_s': secs, 'power_pct': [lo, hi]};
  }

  void dispose() {
    for (final c in [count, dur, low, high]) {
      c.dispose();
    }
    for (final c in children) {
      c.dispose();
    }
  }
}

/// Fertige Vorlagen zum schnellen Start (Prozent der FTP).
Map<String, List<Map<String, dynamic>>> workoutPresets() {
  Map<String, dynamic> leaf(String t, num min, num lo, [num? hi]) =>
      {'type': t, 'duration_s': (min * 60).round(), 'power_pct': [lo, hi ?? lo]};
  Map<String, dynamic> rep(int n, List<Map<String, dynamic>> s) => {'type': 'repeat', 'count': n, 'steps': s};
  return {
    'Erholung 45 min': [leaf('steady', 45, 50, 55)],
    'Grundlage 90 min': [leaf('warmup', 10, 50, 65), leaf('steady', 70, 65, 70), leaf('cooldown', 10, 65, 50)],
    'Sweetspot 3×15': [
      leaf('warmup', 15, 50, 75),
      rep(3, [leaf('interval', 15, 88, 93), leaf('rest', 5, 55)]),
      leaf('cooldown', 10, 60, 45),
    ],
    'Schwelle 2×20': [
      leaf('warmup', 15, 50, 75),
      rep(2, [leaf('interval', 20, 95, 100), leaf('rest', 8, 55)]),
      leaf('cooldown', 10, 60, 45),
    ],
    'VO2max 5×4': [
      leaf('warmup', 15, 50, 75),
      rep(5, [leaf('interval', 4, 115, 120), leaf('rest', 4, 55)]),
      leaf('cooldown', 10, 60, 45),
    ],
  };
}
