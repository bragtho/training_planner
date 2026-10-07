import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/charts.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'highlight.dart';
import 'power_curve_card.dart' show formatClock;

/// Runden des Geraets (Lap-Taste oder Auto-Lap). Karte erscheint nur bei mindestens zwei Runden.
class LapsCard extends ConsumerWidget {
  const LapsCard({
    super.key,
    required this.id,
    required this.ftp,
    required this.selected,
    required this.onSelect,
    required this.zoomed,
    required this.onZoom,
  });
  final int id;
  final num? ftp;
  final Highlight? selected;
  final ValueChanged<Highlight?> onSelect;
  final bool zoomed;
  final ValueChanged<bool> onZoom;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final laps = ref.watch(lapsProvider(id));
    return laps.maybeWhen(
      data: (l) => l.length < 2
          ? const SizedBox.shrink()
          : Padding(
              padding: const EdgeInsets.only(bottom: Gap.md),
              child: LapsBody(laps: l, ftp: ftp, selected: selected, onSelect: onSelect, zoomed: zoomed, onZoom: onZoom),
            ),
      orElse: () => const SizedBox.shrink(),
    );
  }
}

/// Messgroesse, nach der die Balken gezeichnet werden: Leistung, sonst Herzfrequenz.
enum LapMetric {
  power('avg_watts', 'Leistung', 'W'),
  heart('avg_heartrate', 'Puls', 'bpm');

  const LapMetric(this.key, this.title, this.unit);
  final String key;
  final String title;
  final String unit;
}

double? _num(Json lap, String key) {
  final v = lap[key];
  return v is num && v > 0 ? v.toDouble() : null;
}

class LapsBody extends StatefulWidget {
  const LapsBody({
    super.key,
    required this.laps,
    required this.ftp,
    required this.selected,
    required this.onSelect,
    required this.zoomed,
    required this.onZoom,
  });
  final List<Json> laps;
  final num? ftp;
  final Highlight? selected;
  final ValueChanged<Highlight?> onSelect;
  final bool zoomed;
  final ValueChanged<bool> onZoom;

  @override
  State<LapsBody> createState() => _LapsBodyState();
}

class _LapsBodyState extends State<LapsBody> {
  static const _rowHeight = 48.0;
  static const _visibleRows = 6;
  final _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  List<Json> get laps => widget.laps;

  LapMetric get _metric =>
      laps.any((l) => _num(l, LapMetric.power.key) != null) ? LapMetric.power : LapMetric.heart;

  int _start(Json l) => (l['start_s'] as num).toInt();
  int _dur(Json l) => (l['duration_s'] as num).toInt();

  Highlight _highlight(Json l) => Highlight(
    startS: _start(l),
    durationS: _dur(l),
    watts: _num(l, 'avg_watts') ?? 0,
    label: 'Runde ${l['index']}',
  );

  /// Index der gewaehlten Runde (nur wenn die Auswahl eine Runde ist).
  int? get _selectedIndex {
    final s = widget.selected;
    if (s == null || s.label == null) return null;
    final i = laps.indexWhere((l) => _start(l) == s.startS && _dur(l) == s.durationS);
    return i < 0 ? null : i;
  }

  void _toggle(int i, {bool scroll = false}) {
    widget.onSelect(_selectedIndex == i ? null : _highlight(laps[i]));
    if (scroll && _scroll.hasClients) {
      // Wahl im Diagramm: Tabelle springt zur Zeile, das Diagramm bleibt stehen
      final max = _scroll.position.maxScrollExtent;
      _scroll.animateTo((i * _rowHeight).clamp(0.0, max), duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
    }
  }

  String _km(num m) => (m / 1000).toStringAsFixed(2).replaceAll('.', ',');

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final metric = _metric;
    final sel = _selectedIndex;
    final hasHeart = metric == LapMetric.power && laps.any((l) => _num(l, 'avg_heartrate') != null);

    String subtitle = 'Tippe auf eine Runde, um sie in den Graphen und auf der Karte zu sehen';
    if (sel != null) {
      final l = laps[sel];
      final v = _num(l, metric.key);
      subtitle =
          'Runde ${l['index']}: ${v == null ? '–' : '${v.round()} ${metric.unit}'}, '
          'von ${formatClock(_start(l))} bis ${formatClock(_start(l) + _dur(l))}';
    }

    final head = t.textTheme.labelMedium?.copyWith(color: muted, fontWeight: FontWeight.w600);
    final cell = t.textTheme.bodyMedium?.copyWith(fontFeatures: const [FontFeature.tabularFigures()]);

    Widget row(int i) {
      final l = laps[i];
      final on = sel == i;
      final v = _num(l, metric.key);
      final hr = _num(l, 'avg_heartrate');
      final c = _barColor(context, l, metric);
      return InkWell(
        onTap: () => _toggle(i),
        child: Container(
          decoration: BoxDecoration(
            color: on ? c.withValues(alpha: 0.12) : null,
            border: Border(bottom: BorderSide(color: t.colorScheme.outlineVariant)),
          ),
          padding: const EdgeInsets.symmetric(horizontal: Gap.sm),
          child: Row(children: [
            SizedBox(
              width: 34,
              child: Row(children: [
                Container(width: 4, height: 16, decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(2))),
                const SizedBox(width: 6),
                Text('${l['index']}', style: cell?.copyWith(fontWeight: FontWeight.w700)),
              ]),
            ),
            Expanded(flex: 3, child: Text('${_km(l['distance_m'] as num)} km', style: cell)),
            Expanded(flex: 2, child: Text(formatClock(_dur(l)), style: cell)),
            Expanded(flex: 3, child: Text(v == null ? '–' : '${v.round()} ${metric.unit}', style: cell?.copyWith(fontWeight: FontWeight.w600))),
            if (hasHeart) Expanded(flex: 2, child: Text(hr == null ? '–' : '${hr.round()}', style: cell)),
          ]),
        ),
      );
    }

    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionHeader(title: 'Runden', subtitle: subtitle),
        _LapBars(
          laps: laps,
          metric: metric,
          selected: sel,
          colorOf: (l) => _barColor(context, l, metric),
          onTap: (i) => _toggle(i, scroll: true),
        ),
        const SizedBox(height: Gap.md),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Gap.sm),
          child: Row(children: [
            SizedBox(width: 34, child: Text('Nr.', style: head)),
            Expanded(flex: 3, child: Text('Distanz', style: head)),
            Expanded(flex: 2, child: Text('Zeit', style: head)),
            Expanded(flex: 3, child: Text(metric.title, style: head)),
            if (hasHeart) Expanded(flex: 2, child: Text('Puls', style: head)),
          ]),
        ),
        const SizedBox(height: Gap.xs),
        Divider(color: t.colorScheme.outlineVariant),
        // Tabelle scrollt fuer sich, damit das Diagramm oben sichtbar bleibt
        SizedBox(
          height: _rowHeight * (laps.length < _visibleRows ? laps.length : _visibleRows),
          child: ListView.builder(
            controller: _scroll,
            itemExtent: _rowHeight,
            padding: EdgeInsets.zero,
            itemCount: laps.length,
            itemBuilder: (_, i) => row(i),
          ),
        ),
        if (sel != null) ...[
          const SizedBox(height: Gap.sm),
          Wrap(spacing: Gap.sm, runSpacing: Gap.xs, crossAxisAlignment: WrapCrossAlignment.center, children: [
            FilledButton.tonalIcon(
              onPressed: () => widget.onZoom(!widget.zoomed),
              icon: Icon(widget.zoomed ? Icons.zoom_out_map_rounded : Icons.zoom_in_rounded, size: 18),
              label: Text(widget.zoomed ? 'Ganze Fahrt zeigen' : 'Auf Runde zoomen'),
            ),
            TextButton(onPressed: () => widget.onSelect(null), child: const Text('Auswahl aufheben')),
          ]),
        ],
      ]),
    );
  }

  /// Leistung in der Farbe der Trainingszone (bezogen auf die FTP), sonst die Leistungsfarbe.
  Color _barColor(BuildContext context, Json lap, LapMetric metric) {
    final v = _num(lap, metric.key);
    if (v == null) return Theme.of(context).colorScheme.outline;
    if (metric == LapMetric.heart) return AppColors.heart;
    final ftp = widget.ftp;
    return ftp != null && ftp > 0 ? AppColors.zoneColor(v / ftp * 100) : AppColors.power;
  }
}

/// Balkendiagramm: Breite = Dauer der Runde, Hoehe = Messwert, gestrichelte Linie = Durchschnitt der Fahrt.
class _LapBars extends StatelessWidget {
  const _LapBars({required this.laps, required this.metric, required this.selected, required this.colorOf, required this.onTap});
  final List<Json> laps;
  final LapMetric metric;
  final int? selected;
  final Color Function(Json) colorOf;
  final ValueChanged<int> onTap;

  static const _axisW = 36.0;
  static const _bottomH = 22.0;
  static const _height = 170.0;

  @override
  Widget build(BuildContext context) {
    final cs = ChartStyle(context);
    final total = laps.fold<double>(0, (a, l) => a + (l['duration_s'] as num));
    final values = [for (final l in laps) _num(l, metric.key)];
    final top = values.whereType<double>().fold<double>(0, (a, b) => a > b ? a : b);
    final step = _niceStep(top);
    final maxY = (top / step).ceil() * step;
    // Durchschnitt der Fahrt, gewichtet nach Dauer
    var weighted = 0.0, weight = 0.0;
    for (var i = 0; i < laps.length; i++) {
      final v = values[i];
      if (v == null) continue;
      final d = (laps[i]['duration_s'] as num).toDouble();
      weighted += v * d;
      weight += d;
    }
    final avg = weight > 0 ? weighted / weight : null;

    return LayoutBuilder(builder: (context, box) {
      final plotW = box.maxWidth - _axisW;
      final starts = <double>[];
      var acc = 0.0;
      for (final l in laps) {
        starts.add(acc / total * plotW);
        acc += (l['duration_s'] as num).toDouble();
      }
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapUp: (d) {
          final x = d.localPosition.dx - _axisW;
          if (x < 0) return;
          for (var i = laps.length - 1; i >= 0; i--) {
            if (x >= starts[i]) {
              onTap(i);
              return;
            }
          }
        },
        child: CustomPaint(
          size: Size(box.maxWidth, _height),
          painter: _LapPainter(
            values: values,
            durations: [for (final l in laps) (l['duration_s'] as num).toDouble()],
            indexes: [for (final l in laps) (l['index'] as num).toInt()],
            colors: [for (final l in laps) colorOf(l)],
            maxY: maxY <= 0 ? 1 : maxY,
            step: step,
            avg: avg,
            selected: selected,
            axis: cs.axis,
            grid: cs.scheme.outlineVariant,
            avgColor: cs.scheme.onSurfaceVariant,
          ),
        ),
      );
    });
  }

  static double _niceStep(double top) {
    if (top <= 0) return 1;
    for (final s in const [10.0, 20.0, 25.0, 50.0, 100.0, 200.0]) {
      if (top / s <= 5) return s;
    }
    return 250;
  }
}

class _LapPainter extends CustomPainter {
  _LapPainter({
    required this.values,
    required this.durations,
    required this.indexes,
    required this.colors,
    required this.maxY,
    required this.step,
    required this.avg,
    required this.selected,
    required this.axis,
    required this.grid,
    required this.avgColor,
  });
  final List<double?> values;
  final List<double> durations;
  final List<int> indexes;
  final List<Color> colors;
  final double maxY;
  final double step;
  final double? avg;
  final int? selected;
  final TextStyle axis;
  final Color grid;
  final Color avgColor;

  void _text(Canvas canvas, String s, Offset at, {bool center = false, bool right = false}) {
    final tp = TextPainter(text: TextSpan(text: s, style: axis), textDirection: TextDirection.ltr)..layout();
    final dx = center ? tp.width / 2 : (right ? tp.width : 0);
    tp.paint(canvas, Offset(at.dx - dx, at.dy - tp.height / 2));
  }

  void _dashed(Canvas canvas, double y, double x1, double x2, Paint p) {
    for (var x = x1; x < x2; x += 8) {
      canvas.drawLine(Offset(x, y), Offset((x + 4).clamp(x1, x2), y), p);
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    const axisW = _LapBars._axisW;
    final plot = Rect.fromLTRB(axisW, 4, size.width, size.height - _LapBars._bottomH);
    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (var v = 0.0; v <= maxY + 0.001; v += step) {
      final y = plot.bottom - v / maxY * plot.height;
      if (v > 0) _dashed(canvas, y, plot.left, plot.right, gridPaint);
      _text(canvas, v.round().toString(), Offset(axisW - 6, y), right: true);
    }
    canvas.drawLine(Offset(plot.left, plot.bottom), Offset(plot.right, plot.bottom), gridPaint);

    final total = durations.fold<double>(0, (a, b) => a + b);
    var x = plot.left;
    var lastLabelRight = -100.0;
    for (var i = 0; i < values.length; i++) {
      final w = durations[i] / total * plot.width;
      final v = values[i];
      final dim = selected != null && selected != i;
      if (v != null) {
        final h = v / maxY * plot.height;
        final r = RRect.fromRectAndCorners(
          Rect.fromLTWH(x + 0.75, plot.bottom - h, (w - 1.5).clamp(1.0, double.infinity), h),
          topLeft: const Radius.circular(3),
          topRight: const Radius.circular(3),
        );
        canvas.drawRRect(r, Paint()..color = colors[i].withValues(alpha: dim ? 0.3 : 1));
      }
      if (selected == i) {
        canvas.drawRect(
          Rect.fromLTWH(x, plot.top, w, plot.height),
          Paint()..color = colors[i].withValues(alpha: 0.10),
        );
      }
      // Nummer nur, wenn sie ohne Ueberlappung Platz hat
      final label = '${indexes[i]}';
      final needed = label.length * 7.0 + 4;
      if (x + w / 2 - needed / 2 > lastLabelRight) {
        _text(canvas, label, Offset(x + w / 2, size.height - _LapBars._bottomH / 2 + 1), center: true);
        lastLabelRight = x + w / 2 + needed / 2;
      }
      x += w;
    }

    final a = avg;
    if (a != null) {
      final y = plot.bottom - a / maxY * plot.height;
      _dashed(
        canvas,
        y,
        plot.left,
        plot.right,
        Paint()
          ..color = avgColor
          ..strokeWidth = 1.4,
      );
    }
  }

  @override
  bool shouldRepaint(_LapPainter o) =>
      o.values != values || o.selected != selected || o.maxY != maxY || o.avg != avg || o.colors != colors;
}
