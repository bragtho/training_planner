import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import 'theme.dart';

/// Einheitlicher Stil fuer alle Diagramme (Gitter, Achsen, Tooltips).
class ChartStyle {
  ChartStyle(BuildContext context)
      : scheme = Theme.of(context).colorScheme,
        axis = Theme.of(context).textTheme.labelSmall!.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              fontFeatures: const [FontFeature.tabularFigures()],
            );

  final ColorScheme scheme;
  final TextStyle axis;

  FlGridData grid({double? interval}) => FlGridData(
        drawVerticalLine: false,
        horizontalInterval: interval,
        getDrawingHorizontalLine: (_) =>
            FlLine(color: scheme.outlineVariant, strokeWidth: 1, dashArray: const [4, 4]),
      );

  Color tooltipColor() => scheme.inverseSurface;

  TextStyle tooltipText(Color accent) => TextStyle(
        color: Color.lerp(accent, scheme.onInverseSurface, 0.35),
        fontWeight: FontWeight.w700,
        fontSize: 12,
      );

  TextStyle get tooltipTitle =>
      TextStyle(color: scheme.onInverseSurface, fontWeight: FontWeight.w500, fontSize: 11);

  BorderRadius get tooltipRadius => BorderRadius.circular(Radii.sm);

  /// Vertikaler Verlauf unter einer Linie.
  BarAreaData area(Color c, {double opacity = 0.28}) => BarAreaData(
        show: true,
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [c.withValues(alpha: opacity), c.withValues(alpha: 0)],
        ),
      );

  Widget axisLabel(String text) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Text(text, style: axis),
      );
}
