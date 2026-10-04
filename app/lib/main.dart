import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/router.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('de');
  // Keine automatischen Wiederholungen: Fehler (z. B. Backend offline) sofort anzeigen
  runApp(ProviderScope(retry: (_, _) => null, child: const TrainingApp()));
}

class TrainingApp extends ConsumerWidget {
  const TrainingApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Training Planner',
      routerConfig: ref.watch(routerProvider),
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
    );
  }

  ThemeData _theme(Brightness b) => ThemeData(
        colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF0B6E4F), brightness: b),
        useMaterial3: true,
      );
}
