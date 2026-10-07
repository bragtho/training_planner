import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme.dart';

/// Strichfigur in einer Pose, aufgebaut aus Gelenkwinkeln (Grad, 0 = nach rechts, 90 = nach unten, 270 = nach oben).
/// Die Figur schaut nach rechts. Die Huefte ist der Ursprung, der Boden wird aus dem tiefsten Gelenk bestimmt.
class Pose {
  const Pose(
    this.torso,
    this.thigh,
    this.shin, {
    this.foot = 0,
    this.thigh2,
    this.shin2,
    this.foot2 = 0,
    this.upperArm,
    this.foreArm,
    this.weight = false,
    this.box = false,
    this.bench = false,
    this.benchLeg2 = false,
    this.drop = 0,
  });

  final double torso, thigh, shin, foot;
  final double? thigh2, shin2; // zweites Bein (Standbein ist das erste)
  final double foot2;
  final double? upperArm, foreArm;
  final bool weight; // Kurzhantel in der Hand
  final bool box; // Kiste unter dem ersten Fuss
  final bool bench; // Bank unter dem oberen Ruecken
  final bool benchLeg2; // Bank unter dem hinteren Fuss
  final double drop; // zusaetzlicher Abstand zum Boden (z. B. Fuss steht auf Kiste)
}

const _torsoLen = 26.0, _thighLen = 22.0, _shinLen = 22.0, _footLen = 8.0, _headR = 6.5;
const _upperArmLen = 14.0, _foreArmLen = 13.0;

Offset _dir(double deg) => Offset(math.cos(deg * math.pi / 180), math.sin(deg * math.pi / 180));

/// Gelenkpunkte einer Pose, mit y = 0 am Boden (nach unten positiv, Boden unten).
class Skeleton {
  Skeleton(this.pose) {
    final hip = Offset.zero;
    neck = hip + _dir(pose.torso) * _torsoLen;
    head = neck + _dir(pose.torso) * (_headR + 3);
    this.hip = hip;
    knee = hip + _dir(pose.thigh) * _thighLen;
    ankle = knee + _dir(pose.shin) * _shinLen;
    toe = ankle + _dir(pose.foot) * _footLen;
    if (pose.thigh2 != null) {
      knee2 = hip + _dir(pose.thigh2!) * _thighLen;
      ankle2 = knee2! + _dir(pose.shin2 ?? pose.thigh2!) * _shinLen;
      toe2 = ankle2! + _dir(pose.foot2) * _footLen;
    }
    if (pose.upperArm != null) {
      elbow = neck + _dir(pose.upperArm!) * _upperArmLen;
      wrist = elbow! + _dir(pose.foreArm ?? pose.upperArm!) * _foreArmLen;
    }
    final points = [neck, knee, ankle, toe, ?knee2, ?ankle2, ?toe2, ?elbow, ?wrist];
    final low = points.map((p) => p.dy).reduce(math.max);
    floorY = low + 2.5 + pose.drop; // Strichstaerke steht auf der Linie
    _shift = Offset(0, -floorY);
  }

  final Pose pose;
  late final Offset hip, neck, head, knee, ankle, toe;
  Offset? knee2, ankle2, toe2, elbow, wrist;
  late final double floorY;
  late final Offset _shift;

  /// Punkt mit dem Boden bei y = 0.
  Offset at(Offset p) => p + _shift;

  List<Offset> get all => [
        hip, neck, head, knee, ankle, toe, ?knee2, ?ankle2, ?toe2, ?elbow, ?wrist,
      ].map(at).toList();

  /// Sichtbereich (Boden unten bei y = 0), mit Platz fuer Kopf und Props.
  Rect get bounds {
    final pts = all;
    var r = Rect.fromLTRB(pts.map((p) => p.dx).reduce(math.min), pts.map((p) => p.dy).reduce(math.min) - _headR,
        pts.map((p) => p.dx).reduce(math.max), 0);
    r = r.inflate(8);
    return Rect.fromLTRB(r.left, r.top - 8, r.right, 4);
  }
}

/// Pose-Paare je Uebung: Start und Ende. Haltuebungen haben nur eine Pose.
final Map<String, (Pose, Pose?)> exercisePoses = {
  'squat': (const Pose(-90, 90, 90, upperArm: 0), const Pose(-65, 10, 115, upperArm: 0)),
  'goblet_squat': (
    const Pose(-90, 90, 90, upperArm: 70, foreArm: -60, weight: true),
    const Pose(-65, 10, 115, upperArm: 70, foreArm: -60, weight: true),
  ),
  'deadlift': (
    const Pose(-45, 60, 105, upperArm: 100, weight: true),
    const Pose(-90, 90, 90, upperArm: 90, weight: true),
  ),
  'rdl': (
    const Pose(-90, 85, 95, upperArm: 90, weight: true),
    const Pose(-35, 80, 95, upperArm: 115, foreArm: 105, weight: true),
  ),
  'single_leg_rdl': (
    const Pose(-90, 90, 90, thigh2: 95, shin2: 110, foot2: 0, upperArm: 90),
    const Pose(-15, 85, 95, thigh2: 190, shin2: 190, foot2: 90, upperArm: 90),
  ),
  'lunge': (
    const Pose(-90, 90, 90, thigh2: 100, shin2: 95, upperArm: 90),
    const Pose(-90, 5, 95, thigh2: 115, shin2: 195, foot2: 80, upperArm: 90),
  ),
  'split_squat': (
    const Pose(-90, 60, 100, thigh2: 105, shin2: 195, foot2: 180, upperArm: 90, benchLeg2: true),
    const Pose(-88, 10, 100, thigh2: 115, shin2: 200, foot2: 180, upperArm: 90, benchLeg2: true),
  ),
  'step_up': (
    const Pose(-90, 20, 100, thigh2: 90, shin2: 90, upperArm: 90, box: true),
    const Pose(-90, 90, 90, thigh2: 20, shin2: 95, upperArm: 90, box: true, drop: 15),
  ),
  'glute_bridge': (
    const Pose(180, 315, 45, upperArm: 180),
    const Pose(150, 335, 90, upperArm: 180),
  ),
  'hip_thrust': (
    const Pose(207, 330, 60, upperArm: 0, bench: true),
    const Pose(178, 5, 90, upperArm: 0, bench: true),
  ),
  'calf_raise': (
    const Pose(-90, 90, 90, upperArm: 90),
    const Pose(-90, 90, 90, foot: 65, upperArm: 90),
  ),
  'plank': (const Pose(-6, 174, 174, foot: 45, upperArm: 90, foreArm: 0), null),
  'side_plank': (const Pose(-18, 162, 162, foot: 50, upperArm: 90), null),
  'dead_bug': (
    const Pose(180, 270, 0, thigh2: 270, shin2: 0, upperArm: 270),
    const Pose(180, 270, 0, thigh2: 355, shin2: 355, upperArm: 180),
  ),
  'bird_dog': (
    const Pose(-8, 90, 180, foot: 180, upperArm: 90),
    const Pose(-8, 90, 180, foot: 180, thigh2: 183, shin2: 183, foot2: 100, upperArm: -5),
  ),
  'push_up': (
    const Pose(-18, 162, 162, foot: 50, upperArm: 90),
    const Pose(-9, 171, 171, foot: 50, upperArm: 160, foreArm: 90),
  ),
  'row': (
    const Pose(-30, 80, 100, upperArm: 90, weight: true),
    const Pose(-30, 80, 100, upperArm: 165, foreArm: 80, weight: true),
  ),
  'hip_flexor_stretch': (const Pose(-90, 5, 90, thigh2: 95, shin2: 180, foot2: 180, upperArm: 275), null),
  'superman': (
    const Pose(0, 180, 180, foot: 180, foot2: 0, upperArm: 0),
    const Pose(-12, 188, 188, foot: 180, upperArm: -8),
  ),
};

/// Gemeinsamer Sichtbereich beider Posen, damit Start und Ende denselben Massstab haben.
Rect posesBounds(Pose a, Pose? b) {
  final ra = Skeleton(a).bounds;
  return b == null ? ra : ra.expandToInclude(Skeleton(b).bounds);
}

class _FigurePainter extends CustomPainter {
  _FigurePainter({required this.pose, required this.view, required this.body, required this.soft, required this.floor});
  final Pose pose;
  final Rect view;
  final Color body, soft, floor;

  @override
  void paint(Canvas canvas, Size size) {
    final k = Skeleton(pose);
    final scale = math.min(size.width / view.width, size.height / view.height);
    final ox = (size.width - view.width * scale) / 2 - view.left * scale;
    final oy = (size.height - view.height * scale) / 2 - view.top * scale;
    Offset s(Offset p) => Offset(ox + p.dx * scale, oy + p.dy * scale);

    // Boden
    final fy = s(const Offset(0, 0)).dy;
    canvas.drawLine(Offset(0, fy), Offset(size.width, fy), Paint()
      ..color = floor
      ..strokeWidth = 2);

    final stroke = (5 * scale).clamp(3.0, 9.0);
    Paint limb(Color c) => Paint()
      ..color = c
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;
    void line(Paint p, List<Offset> pts) {
      final path = Path()..moveTo(s(k.at(pts.first)).dx, s(k.at(pts.first)).dy);
      for (final q in pts.skip(1)) {
        final t = s(k.at(q));
        path.lineTo(t.dx, t.dy);
      }
      canvas.drawPath(path, p);
    }

    // Props hinter der Figur
    final prop = Paint()..color = floor;
    if (pose.box) {
      final a = s(k.at(k.ankle));
      final r = Rect.fromLTRB(a.dx - 12 * scale, a.dy + stroke * 0.7, a.dx + 12 * scale, fy - 1);
      canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(3)), prop);
    }
    if (pose.bench) {
      final n = s(k.at(k.neck));
      final r = Rect.fromLTRB(n.dx - 14 * scale, n.dy + stroke * 0.7, n.dx + 8 * scale, fy - 1);
      canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(3)), prop);
    }
    if (pose.benchLeg2 && k.ankle2 != null) {
      final a = s(k.at(k.ankle2!));
      final r = Rect.fromLTRB(a.dx - 12 * scale, a.dy + stroke * 0.7, a.dx + 6 * scale, fy - 1);
      canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(3)), prop);
    }

    // zweites Bein (heller), dann Rumpf und Bein, Arm
    if (k.knee2 != null) line(limb(soft), [k.hip, k.knee2!, k.ankle2!, k.toe2!]);
    line(limb(body), [k.hip, k.neck]);
    line(limb(body), [k.hip, k.knee, k.ankle, k.toe]);
    if (k.elbow != null) line(limb(body), [k.neck, k.elbow!, k.wrist!]);
    final h = s(k.at(k.head));
    canvas.drawCircle(h, _headR * scale, Paint()..color = body);

    if (pose.weight && k.wrist != null) {
      final w = s(k.at(k.wrist!));
      final plate = Paint()..color = body.withValues(alpha: 0.95);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromCenter(center: w, width: 11 * scale, height: 3 * scale), const Radius.circular(1)),
        Paint()..color = floor.withValues(alpha: 1),
      );
      for (final dx in [-5.5, 5.5]) {
        canvas.drawRRect(
          RRect.fromRectAndRadius(Rect.fromCenter(center: w + Offset(dx * scale, 0), width: 3.4 * scale, height: 9 * scale), const Radius.circular(1.5)),
          plate,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_FigurePainter o) => o.pose != pose || o.view != view || o.body != body;
}

/// Eine Pose als kleines Bild.
class PoseImage extends StatelessWidget {
  const PoseImage({super.key, required this.pose, required this.view, this.label});
  final Pose pose;
  final Rect view;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return AspectRatio(
      aspectRatio: 1.25,
      child: Container(
        decoration: BoxDecoration(
          color: t.colorScheme.surfaceContainer.withValues(alpha: 0.7),
          borderRadius: BorderRadius.circular(Radii.md),
        ),
        child: Stack(children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _FigurePainter(
                pose: pose,
                view: view,
                body: AppColors.power,
                soft: AppColors.power.withValues(alpha: 0.5),
                floor: t.colorScheme.outline.withValues(alpha: 0.55),
              ),
            ),
          ),
          if (label != null)
            Positioned(
              left: 8,
              top: 6,
              child: Text(label!, style: t.textTheme.labelSmall?.copyWith(color: t.colorScheme.onSurfaceVariant, fontWeight: FontWeight.w700)),
            ),
        ]),
      ),
    );
  }
}

/// Start- und Endposition einer Uebung nebeneinander (Haltuebungen: eine Position).
class ExerciseFigures extends StatelessWidget {
  const ExerciseFigures({super.key, required this.exerciseId});
  final String exerciseId;

  static bool has(String? id) => id != null && exercisePoses.containsKey(id);

  @override
  Widget build(BuildContext context) {
    final p = exercisePoses[exerciseId];
    if (p == null) return const SizedBox.shrink();
    final view = posesBounds(p.$1, p.$2);
    if (p.$2 == null) {
      return Row(children: [Expanded(child: PoseImage(pose: p.$1, view: view, label: 'Position')), const Spacer()]);
    }
    return Row(children: [
      Expanded(child: PoseImage(pose: p.$1, view: view, label: 'Start')),
      const SizedBox(width: Gap.sm),
      Expanded(child: PoseImage(pose: p.$2!, view: view, label: 'Ende')),
    ]);
  }
}
