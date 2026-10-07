import 'package:flutter/material.dart';

/// Sportart einer Strava-Aktivitaet: deutscher Name und Symbol.
class SportInfo {
  const SportInfo(this.label, this.icon);
  final String label;
  final IconData icon;
}

const _sports = <String, SportInfo>{
  'Run': SportInfo('Laufen', Icons.directions_run_rounded),
  'TrailRun': SportInfo('Trailrun', Icons.directions_run_rounded),
  'VirtualRun': SportInfo('Laufen (virtuell)', Icons.directions_run_rounded),
  'Walk': SportInfo('Gehen', Icons.directions_walk_rounded),
  'Hike': SportInfo('Wandern', Icons.hiking_rounded),
  'Snowshoe': SportInfo('Schneeschuhwandern', Icons.hiking_rounded),
  'WeightTraining': SportInfo('Krafttraining', Icons.fitness_center_rounded),
  'Workout': SportInfo('Training', Icons.fitness_center_rounded),
  'Crossfit': SportInfo('Crossfit', Icons.fitness_center_rounded),
  'HighIntensityIntervalTraining': SportInfo('HIIT', Icons.fitness_center_rounded),
  'Yoga': SportInfo('Yoga', Icons.self_improvement_rounded),
  'Swim': SportInfo('Schwimmen', Icons.pool_rounded),
  'AlpineSki': SportInfo('Skifahren', Icons.downhill_skiing_rounded),
  'BackcountrySki': SportInfo('Skitour', Icons.downhill_skiing_rounded),
  'NordicSki': SportInfo('Langlauf', Icons.downhill_skiing_rounded),
  'Snowboard': SportInfo('Snowboard', Icons.snowboarding_rounded),
  'IceSkate': SportInfo('Eislaufen', Icons.ice_skating_rounded),
  'Rowing': SportInfo('Rudern', Icons.rowing_rounded),
  'Kayaking': SportInfo('Kajak', Icons.kayaking_rounded),
  'Elliptical': SportInfo('Crosstrainer', Icons.fitness_center_rounded),
  'StairStepper': SportInfo('Stepper', Icons.fitness_center_rounded),
  'RockClimbing': SportInfo('Klettern', Icons.terrain_rounded),
};

bool isCyclingSport(String? sport) => sport == null || sport.contains('Ride'); // ohne Angabe: Rad (aeltere Daten)

SportInfo sportInfo(String? sport) {
  if (isCyclingSport(sport)) {
    return SportInfo(sport == 'VirtualRide' ? 'Rad (virtuell)' : 'Radfahren', Icons.directions_bike_rounded);
  }
  return _sports[sport] ?? SportInfo(sport ?? 'Aktivität', Icons.sports_rounded);
}
