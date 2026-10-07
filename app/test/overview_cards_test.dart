import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:training_planner/core/data.dart';
import 'package:training_planner/features/dashboard/today_card.dart';
import 'package:training_planner/features/dashboard/week_card.dart';
import 'package:training_planner/features/profile/ftp_change_card.dart';

final _now = DateTime(2026, 10, 7, 10); // Mittwoch

const _structure = [
  {'type': 'warmup', 'duration_s': 600, 'power_pct': [50, 70]},
  {
    'type': 'repeat',
    'count': 2,
    'steps': [
      {'type': 'interval', 'duration_s': 1200, 'power_pct': [95, 100]},
      {'type': 'rest', 'duration_s': 300, 'power_pct': [55, 55]},
    ],
  },
];

Json _workout(String date, String title, {String status = 'planned', bool structure = true}) => {
      'id': 1,
      'date': date,
      'title': title,
      'status': status,
      'planned_duration_s': 3600,
      'planned_tss': 85,
      'structure': structure ? _structure : null,
    };

Json _activity(String start, {double tss = 80}) =>
    {'id': 7, 'name': 'Lockere Runde', 'start_time': start, 'duration_s': 3600, 'distance_m': 30000, 'tss': tss};

Widget _app(Widget child, {required Json calendar, List<Json> activities = const [], Json? atp}) => ProviderScope(
      overrides: [
        calendarProvider.overrideWith((ref, range) async => calendar),
        activitiesProvider.overrideWith((ref) async => activities),
        atpProvider.overrideWith((ref, range) async => atp ?? {'weeks': [], 'events': []}),
      ],
      child: MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child))),
    );

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  setUpAll(() => initializeDateFormatting('de'));

  group('Heute-Karte', () {
    testWidgets('zeigt das geplante Training von heute mit Profil', (tester) async {
      await tester.pumpWidget(_app(TodayCard(now: _now), calendar: {
        'workouts': [_workout('2026-10-07', 'Schwelle 2x20'), _workout('2026-10-09', 'Später')],
        'activities': [],
      }));
      await _settle(tester);
      expect(find.text('Heute'), findsOneWidget);
      expect(find.text('Schwelle 2x20'), findsOneWidget);
      expect(find.text('1:00 h · 85 TSS'), findsOneWidget);
      expect(find.byType(WorkoutProfile), findsOneWidget);
    });

    testWidgets('zeigt sonst das nächste Training', (tester) async {
      await tester.pumpWidget(_app(TodayCard(now: _now), calendar: {
        'workouts': [_workout('2026-10-08', 'Grundlage', structure: false)],
        'activities': [],
      }));
      await _settle(tester);
      expect(find.text('Nächstes Training'), findsOneWidget);
      expect(find.text('Morgen · 1:00 h · 85 TSS'), findsOneWidget);
      expect(find.byType(WorkoutProfile), findsNothing);
    });

    testWidgets('nach der Fahrt: geschafft mit Feedback-Überschrift', (tester) async {
      await tester.pumpWidget(_app(
        TodayCard(now: _now),
        calendar: {
          'workouts': [_workout('2026-10-07', 'Schwelle 2x20', status: 'completed')],
          'activities': [_activity('2026-10-07T09:15:00')],
        },
        activities: [
          {'id': 7, 'feedback_headline': 'Intervalle sauber getroffen'},
        ],
      ));
      await _settle(tester);
      expect(find.text('Heute geschafft'), findsOneWidget);
      expect(find.text('Lockere Runde'), findsOneWidget);
      expect(find.text('Intervalle sauber getroffen'), findsOneWidget);
    });

    testWidgets('ohne Plan ein Hinweis zum Coach', (tester) async {
      await tester.pumpWidget(_app(TodayCard(now: _now), calendar: {'workouts': [], 'activities': []}));
      await _settle(tester);
      expect(find.text('Nichts geplant'), findsOneWidget);
      expect(find.text('Zum Coach'), findsOneWidget);
    });

    test('Profil entfaltet Wiederholungen', () {
      final steps = WorkoutProfile.flatten(_structure);
      expect(steps.length, 5); // Aufwärmen + 2 x (Intervall, Pause)
      expect(steps[1].$1, 1200);
      expect(steps[1].$2, 97.5);
    });
  });

  group('Wochenkarte', () {
    testWidgets('Ist gegen Wochenziel aus dem Saisonplan, Phase und nächstes Ziel', (tester) async {
      await tester.pumpWidget(_app(
        WeekCard(now: _now),
        calendar: {
          'workouts': [_workout('2026-10-08', 'x')],
          'activities': [_activity('2026-10-05T09:00:00', tss: 100)],
        },
        atp: {
          'weeks': [
            {'week_start': '2026-10-05', 'phase': 'base', 'tss_target': 400, 'recovery': false},
          ],
          'events': [
            {'name': 'Gran Fondo', 'priority': 'A', 'days_to_go': 120, 'form_tsb': 12},
          ],
        },
      ));
      await _settle(tester);
      expect(find.text('von 400 TSS'), findsOneWidget);
      expect(find.text('25 %'), findsOneWidget);
      expect(find.text('Grundlage'), findsOneWidget);
      expect(find.text('Gran Fondo'), findsOneWidget);
      expect(find.text('A-Event in 120 Tagen · Form laut Plan +12'), findsOneWidget);
    });

    testWidgets('ohne Saisonplan zählt die Summe der geplanten Trainings, Hinweis zum Anlegen', (tester) async {
      await tester.pumpWidget(_app(WeekCard(now: _now), calendar: {
        'workouts': [_workout('2026-10-08', 'x'), _workout('2026-10-10', 'y')],
        'activities': [],
      }));
      await _settle(tester);
      expect(find.text('von 170 TSS'), findsOneWidget);
      expect(find.textContaining('Saisonplan anlegen'), findsOneWidget);
    });
  });

  testWidgets('FTP-Karte nennt Änderung und Grund und bietet Rückgängig an', (tester) async {
    await tester.pumpWidget(ProviderScope(
      child: MaterialApp(
        home: Scaffold(
          body: FtpChangeCard(change: {
            'date': '2026-10-12',
            'old_ftp': 350,
            'new_ftp': 365,
            'reason': '95 % der besten 20 min: 400 W',
            'can_undo': true,
          }),
        ),
      ),
    ));
    expect(find.text('FTP vom Coach angepasst'), findsOneWidget);
    expect(find.textContaining('350 → 365 W'), findsOneWidget);
    expect(find.text('95 % der besten 20 min: 400 W'), findsOneWidget);
    expect(find.text('Rückgängig'), findsOneWidget);
    await tester.tap(find.text('Rückgängig'));
    await tester.pumpAndSettle();
    expect(find.text('FTP zurücksetzen?'), findsOneWidget);
    expect(find.textContaining('350 W'), findsOneWidget);
  });
}
