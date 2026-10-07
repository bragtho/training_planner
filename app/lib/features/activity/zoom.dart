import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'power_curve_card.dart' show formatClock;

/// Sichtbarer Zeitausschnitt aller Diagramme in Minuten seit Start. null = ganze Fahrt.
class ViewRange {
  const ViewRange(this.min, this.max);
  final double min;
  final double max;

  double get span => max - min;

  @override
  bool operator ==(Object other) => other is ViewRange && (other.min - min).abs() < 1e-6 && (other.max - max).abs() < 1e-6;

  @override
  int get hashCode => Object.hash(min.toStringAsFixed(4), max.toStringAsFixed(4));
}

/// Rechnet Zoom und Verschieben auf einen gueltigen Ausschnitt innerhalb [0, total] um. null, wenn alles sichtbar ist.
ViewRange? clampView(double lo, double hi, double total) {
  final minSpan = math.min(total, math.max(0.5, total / 200)); // nicht weiter als etwa 30 s
  var span = (hi - lo).clamp(minSpan, total).toDouble();
  var a = lo;
  if (a + span > total) a = total - span;
  if (a < 0) a = 0;
  if (span >= total - 1e-6) return null;
  return ViewRange(a, a + span);
}

/// Vergroessert (factor < 1) oder verkleinert (factor > 1) den Ausschnitt um dessen Mitte.
ViewRange? zoomView(ViewRange? v, double factor, double total) {
  final cur = v ?? ViewRange(0, total);
  final c = (cur.min + cur.max) / 2;
  final half = cur.span * factor / 2;
  return clampView(c - half, c + half, total);
}

/// Verschiebt den Ausschnitt um einen Anteil seiner Breite (negativ = nach links).
ViewRange? panView(ViewRange? v, double share, double total) {
  if (v == null) return null;
  final d = v.span * share;
  return clampView(v.min + d, v.max + d, total);
}

/// Werkzeugleiste fuer alle Diagramme: Zoom, Verschieben, Schieberegler fuer den Ausschnitt.
class ZoomBar extends StatelessWidget {
  const ZoomBar({super.key, required this.total, required this.view, required this.onChanged});
  final double total; // Fahrtdauer in Minuten
  final ViewRange? view;
  final ValueChanged<ViewRange?> onChanged;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final v = view ?? ViewRange(0, total);
    final zoomed = view != null;
    return SurfaceCard(
      padding: const EdgeInsets.symmetric(horizontal: Gap.md, vertical: Gap.sm),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(
              zoomed ? 'Ausschnitt ${formatClock((v.min * 60).round())} bis ${formatClock((v.max * 60).round())}' : 'Zoom: ganze Fahrt',
              style: t.textTheme.labelLarge,
            ),
          ),
          IconButton(
            tooltip: 'Nach links',
            onPressed: zoomed ? () => onChanged(panView(view, -0.25, total)) : null,
            icon: const Icon(Icons.chevron_left_rounded),
          ),
          IconButton(
            tooltip: 'Nach rechts',
            onPressed: zoomed ? () => onChanged(panView(view, 0.25, total)) : null,
            icon: const Icon(Icons.chevron_right_rounded),
          ),
          IconButton(
            tooltip: 'Herauszoomen',
            onPressed: zoomed ? () => onChanged(zoomView(view, 2, total)) : null,
            icon: const Icon(Icons.remove_rounded),
          ),
          IconButton(
            tooltip: 'Hineinzoomen',
            onPressed: () => onChanged(zoomView(view, 0.5, total)),
            icon: const Icon(Icons.add_rounded),
          ),
          TextButton(onPressed: zoomed ? () => onChanged(null) : null, child: const Text('Ganze Fahrt')),
        ]),
        RangeSlider(
          values: RangeValues(v.min.clamp(0, total).toDouble(), v.max.clamp(0, total).toDouble()),
          min: 0,
          max: total,
          labels: RangeLabels(formatClock((v.min * 60).round()), formatClock((v.max * 60).round())),
          onChanged: (r) => onChanged(clampView(r.start, r.end, total)),
        ),
        Text('Im Diagramm: Mausrad oder zwei Finger zoomen, mit der Maus ziehen verschiebt.',
            style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
      ]),
    );
  }
}

/// Wendet eine Zoom-/Verschiebe-Geste an: [factor] < 1 zoomt hinein, [anchor] (0..1) ist die Stelle im Diagramm, die
/// beim Zoomen stehen bleibt (Finger oder Mauszeiger), [pan] verschiebt danach um einen Anteil der Ausschnittbreite.
ViewRange? applyGesture(ViewRange? v, double total, {double factor = 1, double anchor = 0.5, double pan = 0}) {
  final cur = v ?? ViewRange(0, total);
  final a = anchor.clamp(0.0, 1.0).toDouble();
  final focus = cur.min + a * cur.span;
  final span = cur.span * factor;
  var lo = focus - a * span;
  lo += pan * span;
  return clampView(lo, lo + span, total);
}

/// Bedienung wie bei einem Bild oder in CAD-Programmen: Mausrad zoomt zum Mauszeiger, Ziehen mit der Maus verschiebt,
/// zwei Finger zoomen und verschieben gleichzeitig. Ein Finger bleibt frei fuer Scrollen und die Wertanzeige.
class ZoomListener extends StatefulWidget {
  const ZoomListener({super.key, required this.child, required this.onGesture, this.leftInset = 0});
  final Widget child;
  final void Function(double factor, double anchor, double pan)? onGesture;
  final double leftInset; // Breite der Achsenbeschriftung links, gehoert nicht zur Zeichenflaeche

  @override
  State<ZoomListener> createState() => _ZoomListenerState();
}

class _ZoomListenerState extends State<ZoomListener> {
  final _pointers = <int, Offset>{};
  Offset? _lastMid;
  double? _lastDistance;
  double _lastPanZoomScale = 1;

  double get _plotWidth {
    final box = context.findRenderObject() as RenderBox?;
    return math.max(1, (box?.size.width ?? 1) - widget.leftInset);
  }

  double _anchor(double x) => ((x - widget.leftInset) / _plotWidth).clamp(0.0, 1.0).toDouble();

  void _emit(double factor, double x, double panPx) => widget.onGesture?.call(factor, _anchor(x), -panPx / _plotWidth);

  void _resetPinch() {
    if (_pointers.length == 2) {
      final p = _pointers.values.toList();
      _lastDistance = (p[0] - p[1]).distance;
      _lastMid = (p[0] + p[1]) / 2;
    } else {
      _lastDistance = null;
      _lastMid = null;
    }
  }

  @override
  Widget build(BuildContext context) => Listener(
        onPointerDown: (e) {
          _pointers[e.pointer] = e.localPosition;
          _resetPinch();
        },
        onPointerMove: (e) {
          if (!_pointers.containsKey(e.pointer)) return;
          _pointers[e.pointer] = e.localPosition;
          if (_pointers.length == 2) {
            final p = _pointers.values.toList();
            final d = (p[0] - p[1]).distance;
            final mid = (p[0] + p[1]) / 2;
            final lastD = _lastDistance, lastMid = _lastMid;
            if (lastD != null && lastMid != null && lastD > 0 && d > 0) {
              _emit(lastD / d, mid.dx, mid.dx - lastMid.dx);
            }
            _lastDistance = d;
            _lastMid = mid;
          } else if (_pointers.length == 1 && e.kind == PointerDeviceKind.mouse && e.buttons == kPrimaryMouseButton) {
            _emit(1, e.localPosition.dx, e.delta.dx); // Maus: Ziehen verschiebt
          }
        },
        onPointerUp: (e) {
          _pointers.remove(e.pointer);
          _resetPinch();
        },
        onPointerCancel: (e) {
          _pointers.remove(e.pointer);
          _resetPinch();
        },
        onPointerSignal: (e) {
          if (e is! PointerScrollEvent || widget.onGesture == null) return;
          GestureBinding.instance.pointerSignalResolver.register(e, (_) {
            if (e.scrollDelta.dx.abs() > e.scrollDelta.dy.abs()) {
              _emit(1, e.localPosition.dx, -e.scrollDelta.dx); // seitliches Wischen auf dem Trackpad verschiebt
            } else {
              _emit(math.exp(e.scrollDelta.dy * 0.002).clamp(0.5, 2.0), e.localPosition.dx, 0); // Mausrad: hinein / hinaus
            }
          });
        },
        onPointerPanZoomStart: (_) => _lastPanZoomScale = 1,
        onPointerPanZoomUpdate: (e) {
          _emit(_lastPanZoomScale / e.scale, e.localPosition.dx, e.panDelta.dx);
          _lastPanZoomScale = e.scale;
        },
        child: widget.child,
      );
}

/// Abstand der Zeitmarken (Minuten), sodass hoechstens etwa sechs Beschriftungen nebeneinander stehen.
double axisInterval(double spanMin) {
  const steps = <double>[1 / 12, 1 / 6, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 240];
  return steps.firstWhere((c) => spanMin / c <= 6, orElse: () => 240);
}

/// Zeitmarke fuer die Achse: unter einer Minute Abstand mit Sekunden (12:40), sonst wie bisher (45 min, 1:15 h).
String axisTimeLabel(double minutes, double interval) =>
    interval < 1 ? formatClock((minutes * 60).round()) : formatDuration(minutes * 60);

/// Ausschnitt fuer den gewaehlten Abschnitt: 15 % Rand je Seite.
ViewRange? sectionView(double startMin, double endMin, double total) {
  final pad = (endMin - startMin) * 0.15;
  return clampView(startMin - pad, endMin + pad, total);
}

/// Fahrtdauer in Minuten aus dem Zeit-Stream.
double totalMinutes(Json streams) {
  final t = (streams['time'] as List?) ?? const [];
  return t.isEmpty ? 0 : (t.last as num) / 60;
}
