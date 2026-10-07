import 'package:flutter/material.dart';

import '../../core/theme.dart';

/// Urteil der Belastungsbewertung: Beschriftung, Farbe, Symbol.
(String, Color, IconData) loadVerdictStyle(String? v) => switch (v) {
      'too_much' => ('Zu viel', const Color(0xFFEF4444), Icons.warning_amber_rounded),
      'slightly_much' => ('Eher viel', const Color(0xFFF97316), Icons.trending_up_rounded),
      'ok' => ('Passend', AppColors.completed, Icons.check_circle_rounded),
      'too_little' => ('Zu wenig', const Color(0xFF0EA5E9), Icons.trending_down_rounded),
      'mixed' => ('Gemischt', const Color(0xFF94A3B8), Icons.compare_arrows_rounded),
      _ => ('Noch unklar', const Color(0xFF94A3B8), Icons.hourglass_empty_rounded),
    };
