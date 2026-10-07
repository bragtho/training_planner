import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:training_planner/core/data.dart';
import 'package:training_planner/features/activity/activity_analysis.dart';
import 'package:training_planner/features/dashboard/load_ftp_cards.dart';

const _feedback = <String, dynamic>{
  'headline': 'Intervalle sauber getroffen',
  'summary': 'Alle fünf Intervalle lagen im Ziel.',
  'execution': 'as_planned',
  'load_fit': 'fits',
  'positives': ['Gleichmäßig gefahren'],
  'improvements': ['Mehr trinken'],
  'next': 'Morgen locker.',
  'ftp_hint': 'Deine FTP ist vermutlich zu niedrig: Vorschlag 285 W.',
};

const _analysis = <String, dynamic>{
  'type': 'vo2max',
  'type_label': 'VO2max',
  'race': false,
  'coach_configured': true,
  'feedback_status': 'done',
  'feedback': _feedback,
  'plan': {'title': '5x4 VO2max'},
  'compliance': {
    'tss': {'planned': 85, 'actual': 82, 'pct': 96},
    'duration': {'planned_min': 60, 'actual_min': 62, 'pct': 103},
    'interval_count': 2,
    'hit': 1,
    'avg_pct': 96,
    'fade_pct': -9,
    'intervals': [
      {'n': 1, 'type': 'interval', 'duration_s': 240, 'target_w': 299, 'actual_w': 301, 'pct': 101, 'status': 'ok'},
      {'n': 2, 'type': 'interval', 'duration_s': 240, 'target_w': 299, 'actual_w': 270, 'pct': 90, 'status': 'under'},
    ],
  },
  'metrics': {
    'vi': 1.12,
    'time_above_ftp_s': 1200,
    'matches': 4,
    'pacing': {'change_pct': -3},
    'best_powers': {'5 min': 305, '20 min': 280},
  },
  'personal_bests_90d': [
    {'duration': '5 min', 'watts': 305, 'previous': 295, 'gain_pct': 3.4},
  ],
};

Widget _app(Widget child, {List overrides = const []}) => ProviderScope(
      overrides: [...overrides],
      child: MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child))),
    );

void main() {
  testWidgets('Gespeichertes Feedback zeigt Kernaussage, Punkte und FTP-Hinweis', (tester) async {
    await tester.pumpWidget(_app(const CoachFeedbackCard(id: 1, analysis: _analysis)));
    expect(find.text('Intervalle sauber getroffen'), findsOneWidget);
    expect(find.text('Wie geplant'), findsOneWidget);
    expect(find.text('Belastung passt'), findsOneWidget);
    expect(find.text('Gleichmäßig gefahren'), findsOneWidget);
    expect(find.text('Mehr trinken'), findsOneWidget);
    expect(find.textContaining('Vorschlag 285 W'), findsOneWidget);
  });

  testWidgets('Fehlendes Feedback wird automatisch erstellt', (tester) async {
    final analysis = Map<String, dynamic>.from(_analysis)..['feedback'] = null;
    await tester.pumpWidget(_app(CoachFeedbackCard(id: 7, analysis: analysis), overrides: [
      activityFeedbackProvider.overrideWith((ref, id) async => {..._feedback, 'headline': 'Frisch erstellt $id'}),
    ]));
    await tester.pump();
    await tester.pump();
    expect(find.text('Frisch erstellt 7'), findsOneWidget);
  });

  testWidgets('Ohne eingerichteten Coach gibt es einen Hinweis statt Feedback', (tester) async {
    final analysis = Map<String, dynamic>.from(_analysis)
      ..['feedback'] = null
      ..['coach_configured'] = false;
    await tester.pumpWidget(_app(CoachFeedbackCard(id: 1, analysis: analysis)));
    expect(find.text('Kein Coach-Feedback'), findsOneWidget);
  });

  testWidgets('Soll und Ist je Intervall und Bestwerte', (tester) async {
    await tester.pumpWidget(_app(Column(children: [
      ComplianceCard(
          compliance: Json.from(_analysis['compliance'] as Map), plan: Json.from(_analysis['plan'] as Map)),
      RideDetails(metrics: Json.from(_analysis['metrics'] as Map), bests: _analysis['personal_bests_90d'] as List),
    ])));
    expect(find.text('Geplant: 5x4 VO2max'), findsOneWidget);
    expect(find.text('1 / 2'), findsOneWidget);
    expect(find.text('90 %'), findsOneWidget);
    expect(find.textContaining('Leistungsabfall'), findsOneWidget);
    expect(find.text('5 min  305 W'), findsOneWidget);
    expect(find.byIcon(Icons.emoji_events_rounded), findsOneWidget);
  });

  testWidgets('Belastungskarte nutzt die Einordnung des Coaches', (tester) async {
    await tester.pumpWidget(_app(const LoadCard(), overrides: [
      loadCheckProvider.overrideWith((ref) async => {
            'verdict': 'too_little',
            'flags': [
              {'code': 'ctl_falling', 'level': 'warn', 'text': 'Die Fitness sinkt.', 'kind': 'too_little'},
            ],
            'metrics': {'ramp_7d': -4.2, 'tss_7d': 120},
            'context': {'planned_tss_14d': 0, 'actual_tss_14d': 300, 'season_phase': 'Übergang'},
            'coach': {'verdict': 'ok', 'text': 'Die Pause ist gewollt.'},
          }),
    ]));
    await tester.pump();
    expect(find.text('Passend'), findsOneWidget);
    expect(find.text('Die Pause ist gewollt.'), findsOneWidget);
    expect(find.text('Die Fitness sinkt.'), findsNothing);
    expect(find.text('CTL -4.2 / Woche'), findsOneWidget);
  });

  testWidgets('FTP-Vorschlag bietet das Übernehmen an', (tester) async {
    await tester.pumpWidget(_app(const FtpCard(), overrides: [
      ftpCheckProvider.overrideWith((ref) async => {
            'ftp': 260,
            'recommendation': 'raise',
            'suggested_ftp': 285,
            'reason': 'Die besten 20 min ergeben etwa 285 W.',
            'best_efforts': {
              '20 min': {'watts': 300, 'date': '2026-10-01'},
            },
          }),
    ]));
    await tester.pump();
    expect(find.text('FTP anheben?'), findsOneWidget);
    expect(find.text('Auf 285 W setzen'), findsOneWidget);
    expect(find.text('20 min  300 W'), findsOneWidget);
  });

  test('Farben und Beschriftungen der Urteile', () {
    expect(loadVerdictStyle('too_much').$1, 'Zu viel');
    expect(loadVerdictStyle('unbekannt').$1, 'Noch unklar');
    expect(loadFitStyle('too_little').$1, 'Zu wenig');
  });
}
