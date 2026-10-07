import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'highlight.dart';

/// Strecke der Fahrt auf einer OpenStreetMap-Karte. Ein gewaehlter Abschnitt (Leistungskurve) wird farbig hervorgehoben.
class ActivityMapCard extends StatefulWidget {
  const ActivityMapCard({super.key, required this.streams, this.highlight, this.zoomed = false});
  final Json streams;
  final Highlight? highlight;
  final bool zoomed;

  /// Punkte der Strecke; leer, wenn die Fahrt keine GPS-Daten hat (Rolle, Indoor).
  static List<LatLng> route(Json streams) => [
    for (final p in (streams['latlng'] as List?) ?? const [])
      if (p is List && p.length >= 2 && p[0] != null && p[1] != null) LatLng((p[0] as num).toDouble(), (p[1] as num).toDouble()),
  ];

  @override
  State<ActivityMapCard> createState() => _ActivityMapCardState();
}

class _ActivityMapCardState extends State<ActivityMapCard> {
  final _controller = MapController();

  Json get streams => widget.streams;
  Highlight? get highlight => widget.highlight;

  @override
  void didUpdateWidget(ActivityMapCard old) {
    super.didUpdateWidget(old);
    if (old.zoomed != widget.zoomed || (widget.zoomed && old.highlight != widget.highlight)) {
      final all = ActivityMapCard.route(streams);
      final target = widget.zoomed ? _section(all) : all;
      if (target.length >= 2) {
        _controller.fitCamera(CameraFit.bounds(bounds: LatLngBounds.fromPoints(target), padding: const EdgeInsets.all(40), maxZoom: 17));
      }
    }
  }

  List<LatLng> _section(List<LatLng> all) {
    final h = highlight;
    final time = (streams['time'] as List?) ?? const [];
    if (h == null || time.length != all.length) return const [];
    return [
      for (var i = 0; i < all.length; i++)
        if ((time[i] as num) >= h.startS && (time[i] as num) <= h.endS) all[i],
    ];
  }

  @override
  Widget build(BuildContext context) {
    final all = ActivityMapCard.route(streams);
    if (all.length < 2) return const SizedBox.shrink();
    final section = _section(all);
    final t = Theme.of(context);
    return SurfaceCard(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.lg, Gap.lg, 0),
            child: SectionHeader(
              title: 'Karte',
              subtitle: highlight == null ? null : 'Hervorgehoben: beste ${shortDuration(highlight!.durationS)}',
            ),
          ),
          ClipRRect(
            borderRadius: const BorderRadius.vertical(bottom: Radius.circular(Radii.lg)),
            child: SizedBox(
              height: 360,
              child: FlutterMap(
                mapController: _controller,
                options: MapOptions(
                  initialCameraFit: CameraFit.bounds(bounds: LatLngBounds.fromPoints(all), padding: const EdgeInsets.all(32)),
                  interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
                ),
                children: [
                  TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'ch.bragagna.trainingplanner',
                  ),
                  PolylineLayer(
                    polylines: [
                      Polyline(
                        points: all,
                        strokeWidth: highlight == null ? 4 : 3,
                        color: AppColors.accent.withValues(alpha: highlight == null ? 0.95 : 0.55),
                      ),
                      if (section.length >= 2)
                        Polyline(points: section, strokeWidth: 6, color: AppColors.power, borderStrokeWidth: 2, borderColor: Colors.white),
                    ],
                  ),
                  MarkerLayer(markers: [_dot(all.first, AppColors.completed), _dot(all.last, AppColors.heart)]),
                  RichAttributionWidget(
                    alignment: AttributionAlignment.bottomLeft,
                    attributions: [TextSourceAttribution('© OpenStreetMap-Mitwirkende', textStyle: t.textTheme.labelSmall)],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Marker _dot(LatLng p, Color c) => Marker(
    point: p,
    width: 18,
    height: 18,
    child: DecoratedBox(
      decoration: BoxDecoration(
        color: c,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
      ),
    ),
  );
}
