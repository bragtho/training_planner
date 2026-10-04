import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import 'auth.dart';

typedef Json = Map<String, dynamic>;

final pmcProvider = FutureProvider.autoDispose<Json>((ref) async {
  final r = await ref
      .watch(apiProvider)
      .dio
      .get('/metrics/pmc', queryParameters: {'days': 120});
  return Json.from(r.data as Map);
});

final activitiesProvider =
    FutureProvider.autoDispose<List<Json>>((ref) async {
  final r = await ref
      .watch(apiProvider)
      .dio
      .get('/activities', queryParameters: {'limit': 30});
  return [for (final a in r.data as List) Json.from(a as Map)];
});

final activityProvider =
    FutureProvider.autoDispose.family<Json, int>((ref, id) async {
  final r = await ref.watch(apiProvider).dio.get('/activities/$id');
  return Json.from(r.data as Map);
});

/// Streams werden beim ersten Aufruf vom Backend bei Strava geholt (kann dauern).
final streamsProvider =
    FutureProvider.autoDispose.family<Json, int>((ref, id) async {
  final r = await ref.watch(apiProvider).dio.get('/activities/$id/streams');
  return Json.from(r.data as Map);
});

final profileProvider = FutureProvider.autoDispose<Json>((ref) async {
  final r = await ref.watch(apiProvider).dio.get('/profile');
  return Json.from(r.data as Map);
});

/// Formhinweis vom Coach, abgestimmt auf Gespraech und Ziele. null: es gibt keinen oder er ist nicht erreichbar,
/// die Uebersicht zeigt dann den Standardtext. Die Antwort kann wenige Sekunden dauern (Modellaufruf).
final formHintProvider = FutureProvider.autoDispose<String?>((ref) async {
  try {
    final r = await ref.watch(apiProvider).dio.get('/coach/form-hint');
    final text = (r.data as Map)['text'];
    return text is String && text.trim().isNotEmpty ? text.trim() : null;
  } catch (_) {
    return null;
  }
});

/// Eintrag im Gedaechtnis des Coaches.
class CoachMemory {
  const CoachMemory({required this.id, required this.text, this.validUntil});
  final int id;
  final String text;
  final DateTime? validUntil;

  factory CoachMemory.fromJson(Map<String, dynamic> j) => CoachMemory(
        id: j['id'] as int,
        text: j['text'] as String,
        validUntil: j['valid_until'] == null ? null : DateTime.parse(j['valid_until'] as String),
      );
}

final coachMemoriesProvider = FutureProvider.autoDispose<List<CoachMemory>>((ref) async {
  final r = await ref.watch(apiProvider).dio.get('/coach/memories');
  return [for (final m in r.data as List) CoachMemory.fromJson(Map<String, dynamic>.from(m as Map))];
});

final stravaStatusProvider = FutureProvider.autoDispose<Json>((ref) async {
  final r = await ref.watch(apiProvider).dio.get('/integrations/strava/status');
  return Json.from(r.data as Map);
});

final _isoDay = DateFormat('yyyy-MM-dd');
String isoDay(DateTime d) => _isoDay.format(d);

typedef DateRange = (DateTime, DateTime);

/// Geplante Trainings und absolvierte Aktivitaeten fuer einen Zeitraum (max. 100 Tage).
final calendarProvider =
    FutureProvider.autoDispose.family<Json, DateRange>((ref, range) async {
  final r = await ref.watch(apiProvider).dio.get('/calendar',
      queryParameters: {'start': isoDay(range.$1), 'end': isoDay(range.$2)});
  return Json.from(r.data as Map);
});

String formatDuration(num seconds) {
  final s = seconds.round();
  final h = s ~/ 3600;
  final m = (s % 3600) ~/ 60;
  return h > 0 ? '$h:${m.toString().padLeft(2, '0')} h' : '$m min';
}

String formatKm(num meters) => '${(meters / 1000).toStringAsFixed(1)} km';
