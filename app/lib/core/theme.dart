import 'package:flutter/material.dart';

/// Farben mit fester Bedeutung, in hellem und dunklem Modus gleich.
abstract final class AppColors {
  static const brand = Color(0xFF0FA968);
  static const brandDeep = Color(0xFF0B7A55);
  static const accent = Color(0xFF3B82F6);

  static const ctl = Color(0xFF3B82F6); // Fitness
  static const atl = Color(0xFFEC4899); // Ermuedung
  static const tsb = Color(0xFFF59E0B); // Form

  static const power = Color(0xFF6366F1);
  static const heart = Color(0xFFEF4444);
  static const altitude = Color(0xFF64748B);
  static const cadence = Color(0xFF14B8A6);

  static const completed = Color(0xFF16A34A);
  static const strava = Color(0xFFFC4C02);

  /// Coggan-Zonen Z1 bis Z7.
  static const zones = [
    Color(0xFF94A3B8),
    Color(0xFF3B82F6),
    Color(0xFF22C55E),
    Color(0xFFEAB308),
    Color(0xFFF97316),
    Color(0xFFEF4444),
    Color(0xFFA855F7),
  ];

  /// Untere Grenzen der Zonen in Prozent der FTP (wie backend/app/metrics/power.py).
  static const zoneBounds = [0, 55, 75, 90, 105, 120, 150];

  static int zoneIndex(num pctFtp) {
    for (var i = zoneBounds.length - 1; i > 0; i--) {
      if (pctFtp >= zoneBounds[i]) return i;
    }
    return 0;
  }

  static Color zoneColor(num pctFtp) => zones[zoneIndex(pctFtp)];
}

/// Trainingsphasen des Saisonplans (ATP) mit deutschem Namen und Farbe; Reihenfolge wie im Backend.
abstract final class Phases {
  static const all = <String, (String, Color)>{
    'preparation': ('Vorbereitung', Color(0xFF64748B)),
    'base': ('Grundlage', Color(0xFF0EA5E9)),
    'build': ('Aufbau', Color(0xFFF59E0B)),
    'peak': ('Spitze', Color(0xFFEF4444)),
    'race': ('Wettkampf', Color(0xFFA855F7)),
    'transition': ('Übergang', Color(0xFF14B8A6)),
  };

  static String label(String? key) => all[key]?.$1 ?? '';
  static Color color(String? key) => all[key]?.$2 ?? const Color(0xFF94A3B8);
}

/// Prioritaet eines Events: A = Hauptziel, B = wichtig, C = Trainingswettkampf.
abstract final class EventPriority {
  static Color color(String p) => switch (p) {
        'A' => const Color(0xFFE11D48),
        'B' => const Color(0xFFF59E0B),
        _ => const Color(0xFF64748B),
      };
}

/// Abstaende und Radien, damit alle Bildschirme denselben Rhythmus haben.
abstract final class Gap {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
  static const xxl = 32.0;
}

abstract final class Radii {
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 20.0;
  static const pill = 999.0;
}

ThemeData buildTheme(Brightness b) {
  final dark = b == Brightness.dark;
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.brand, brightness: b).copyWith(
    primary: dark ? const Color(0xFF34D399) : AppColors.brandDeep,
    onPrimary: dark ? const Color(0xFF052E1F) : Colors.white,
    surface: dark ? const Color(0xFF0E1116) : const Color(0xFFF4F6F8),
    surfaceContainerLowest: dark ? const Color(0xFF0A0D11) : Colors.white,
    surfaceContainerLow: dark ? const Color(0xFF151A21) : Colors.white,
    surfaceContainer: dark ? const Color(0xFF1A2029) : const Color(0xFFEEF1F4),
    surfaceContainerHigh: dark ? const Color(0xFF212833) : const Color(0xFFE7EBEF),
    surfaceContainerHighest: dark ? const Color(0xFF29313D) : const Color(0xFFDFE4E9),
    outlineVariant: dark ? const Color(0xFF2A323D) : const Color(0xFFE2E7EC),
  );

  final base = ThemeData(colorScheme: scheme, useMaterial3: true, brightness: b);
  final text = base.textTheme.copyWith(
    displaySmall: base.textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -1),
    headlineLarge: base.textTheme.headlineLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.8),
    headlineMedium: base.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.6),
    headlineSmall: base.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.4),
    titleLarge: base.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.3),
    titleMedium: base.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
    titleSmall: base.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
    labelSmall: base.textTheme.labelSmall?.copyWith(letterSpacing: 0.2),
  ).apply(bodyColor: scheme.onSurface, displayColor: scheme.onSurface);

  final fieldBorder = OutlineInputBorder(
    borderRadius: BorderRadius.circular(Radii.md),
    borderSide: BorderSide(color: scheme.outlineVariant),
  );

  return base.copyWith(
    scaffoldBackgroundColor: scheme.surface,
    textTheme: text,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      scrolledUnderElevation: 0,
      centerTitle: false,
      // Groessen kommen sonst erst spaeter aus der Typografie dazu, deshalb hier explizit
      titleTextStyle: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, letterSpacing: -0.3, color: scheme.onSurface),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: scheme.surfaceContainerLow,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Radii.lg),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerLow,
      border: fieldBorder,
      enabledBorder: fieldBorder,
      focusedBorder: fieldBorder.copyWith(borderSide: BorderSide(color: scheme.primary, width: 1.6)),
      errorBorder: fieldBorder.copyWith(borderSide: BorderSide(color: scheme.error)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 48),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 44),
        side: BorderSide(color: scheme.outlineVariant),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.pill)),
      side: BorderSide(color: scheme.outlineVariant),
      backgroundColor: scheme.surfaceContainerLow,
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        visualDensity: VisualDensity.compact,
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      surfaceTintColor: Colors.transparent,
      indicatorColor: scheme.primary.withValues(alpha: 0.14),
      height: 68,
      labelTextStyle: const WidgetStatePropertyAll(TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      indicatorColor: scheme.primary.withValues(alpha: 0.14),
      selectedIconTheme: IconThemeData(color: scheme.primary),
      selectedLabelTextStyle: TextStyle(fontSize: 12, color: scheme.primary, fontWeight: FontWeight.w700),
      unselectedLabelTextStyle: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant, fontWeight: FontWeight.w500),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      surfaceTintColor: Colors.transparent,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.lg)),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: scheme.primary,
      foregroundColor: scheme.onPrimary,
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.lg)),
    ),
    dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: 1),
    listTileTheme: ListTileThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
    ),
  );
}
