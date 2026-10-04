import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:training_planner/core/data.dart';
import 'package:training_planner/features/coach/knowledge_sources.dart';

const _card = <String, dynamic>{
  'slug': 'vo2max-4x4',
  'title': 'VO2max-Intervalle 4x4 min',
  'topic_label': 'Intervalle',
  'summary': 'Vier lange Intervalle verbessern die aerobe Leistung.',
  'recommendation': 'Wenn das Ziel VO2max ist, dann 4 x 4 min bei 105-120 % FTP.',
  'evidence': 'C',
  'evidence_label': 'schwache Evidenz',
  'practice': true,
  'directness': 'indirect',
  'directness_label': 'indirekt (andere Population)',
  'applies_to': {
    'population': ['trained', 'elite'],
    'sex': 'male',
    'age': '20-40',
  },
  'caveats': 'Nur Männer untersucht.',
  'contested': true,
  'safety': false,
  'positions': [
    {
      'label': 'Polarisiert',
      'summary': 'Mehr sehr locker und sehr hart.',
      'source_keys': ['a'],
    },
    {
      'label': 'Pyramidal',
      'summary': 'Tempo-Bereich gleichwertig.',
      'source_keys': ['b'],
    },
  ],
  'sources': [
    {
      'citation': 'Seiler et al. 2010',
      'title': 'Quantifying training intensity distribution',
      'journal': 'Scand J Med Sci Sports',
      'design_label': 'Metaanalyse',
      'sample_n': 400,
      'population': 'Ausdauersportler',
      'basis': 'abstract',
      'url': 'https://doi.org/10.1111/x',
    },
  ],
  'reviewed': '2026-10-04',
  'review_overdue': false,
};

Widget _app(Widget child) => ProviderScope(
  overrides: [knowledgeCardProvider.overrideWith((ref, slug) async => Json.from(_card))],
  child: MaterialApp(home: Scaffold(body: child)),
);

void main() {
  setUpAll(() => initializeDateFormatting('de'));

  testWidgets('Chips zeigen Stufe und Titel, getaggte und nur nachgeschlagene Karten', (tester) async {
    await tester.pumpWidget(
      _app(
        const SourceChips(
          sources: [
            {
              'slug': 'a',
              'title': 'VO2max-Intervalle',
              'evidence': 'A',
              'evidence_label': 'starke Evidenz',
              'practice': false,
              'tagged': true,
            },
            {
              'slug': 'b',
              'title': 'Tapering',
              'evidence': 'C',
              'evidence_label': 'schwache Evidenz',
              'practice': true,
              'tagged': false,
              'contested': true,
            },
          ],
        ),
      ),
    );
    expect(find.text('Quellen'), findsOneWidget);
    expect(find.text('VO2max-Intervalle'), findsOneWidget);
    expect(find.text('Tapering'), findsOneWidget);
    expect(find.text('A'), findsOneWidget);
    expect(find.text('C'), findsOneWidget);
    expect(find.byIcon(Icons.balance_rounded), findsOneWidget); // umstrittene Karte
  });

  testWidgets('Tippen auf einen Chip öffnet das Sheet mit Empfehlung, Grenzen und Quellen', (tester) async {
    tester.view.physicalSize = const Size(900, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      _app(
        const SourceChips(
          sources: [
            {'slug': 'vo2max-4x4', 'title': 'VO2max-Intervalle', 'evidence': 'C', 'practice': true, 'tagged': true},
          ],
        ),
      ),
    );
    await tester.tap(find.text('VO2max-Intervalle'));
    await tester.pumpAndSettle();

    expect(find.text('VO2max-Intervalle 4x4 min'), findsOneWidget);
    expect(find.text('C · schwache Evidenz'), findsOneWidget);
    expect(find.text('indirekt (andere Population)'), findsOneWidget);
    expect(find.text('Umstritten'), findsOneWidget);
    expect(find.textContaining('Schwache Evidenz: kleine oder beobachtende Studien'), findsOneWidget);
    expect(find.textContaining('Wenn das Ziel VO2max ist'), findsOneWidget);
    expect(find.text('Trainierte, Elite · Männer · 20-40'), findsOneWidget);
    expect(find.text('Nur Männer untersucht.'), findsOneWidget);
    expect(find.text('Polarisiert'), findsOneWidget);
    expect(find.text('Seiler et al. 2010'), findsOneWidget);
    expect(find.textContaining('nur Abstract geprüft'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('Farben der Evidenzstufen', () {
    expect(evidenceColor('A'), isNot(evidenceColor('C')));
    expect(evidenceColor('D'), evidenceColor(null));
  });
}
