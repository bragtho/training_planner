import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'theme.dart';

/// Zentrierter, scrollbarer Inhaltsbereich mit begrenzter Breite.
class PageBody extends StatelessWidget {
  const PageBody({
    super.key,
    required this.children,
    this.maxWidth = 1100,
    this.onRefresh,
    this.padding,
  });
  final List<Widget> children;
  final double maxWidth;
  final Future<void> Function()? onRefresh;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) {
    final narrow = MediaQuery.sizeOf(context).width < compactWidth;
    final pad = padding ?? EdgeInsets.fromLTRB(narrow ? Gap.md : Gap.lg, Gap.sm, narrow ? Gap.md : Gap.lg, Gap.xxl);
    final list = Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: ListView(physics: const AlwaysScrollableScrollPhysics(), padding: pad, children: children),
      ),
    );
    return SafeArea(
      bottom: false,
      child: onRefresh == null ? list : RefreshIndicator(onRefresh: onRefresh!, child: list),
    );
  }
}

/// Grosse Seitenueberschrift fuer die Hauptbereiche.
class PageHeader extends StatelessWidget {
  const PageHeader({super.key, required this.title, this.subtitle, this.trailing = const []});
  final String title;
  final String? subtitle;
  final List<Widget> trailing;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final narrow = MediaQuery.sizeOf(context).width < compactWidth;
    return Padding(
      padding: narrow ? const EdgeInsets.only(top: Gap.md, bottom: Gap.lg) : const EdgeInsets.only(top: Gap.lg, bottom: Gap.xl),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (subtitle != null)
                  Text(
                    subtitle!.toUpperCase(),
                    style: t.textTheme.labelMedium?.copyWith(
                      color: t.colorScheme.primary,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.1,
                    ),
                  ),
                const SizedBox(height: 2),
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: narrow
                      ? t.textTheme.titleLarge?.copyWith(fontSize: 22)
                      : t.textTheme.headlineMedium,
                ),
              ],
            ),
          ),
          ...trailing,
        ],
      ),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader({super.key, required this.title, this.subtitle, this.trailing});
  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: Gap.md),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: t.textTheme.titleMedium),
                if (subtitle != null)
                  Text(subtitle!, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// Karte mit feinem Rahmen; optional antippbar.
class SurfaceCard extends StatelessWidget {
  const SurfaceCard({
    super.key,
    required this.child,
    this.padding,
    this.onTap,
    this.color,
  });
  final Widget child;
  final EdgeInsets? padding;
  final VoidCallback? onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) => Card(
    color: color,
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: padding ?? EdgeInsets.all(MediaQuery.sizeOf(context).width < compactWidth ? Gap.md : Gap.lg),
        child: child,
      ),
    ),
  );
}

/// Kennzahl mit Beschriftung, optionaler Einheit, Erklaerung und Veraenderung.
class MetricTile extends StatelessWidget {
  const MetricTile({
    super.key,
    required this.label,
    required this.value,
    this.unit,
    this.color,
    this.icon,
    this.caption,
    this.delta,
    this.help,
    this.compact = false,
  });
  final String label;
  final String value;
  final String? unit;
  final Color? color;
  final IconData? icon;
  final String? caption;
  final num? delta;
  final String? help;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final c = color ?? t.colorScheme.primary;
    final muted = t.colorScheme.onSurfaceVariant;
    // In sehr schmalen Kacheln (z. B. drei nebeneinander auf dem Handy) Symbol weglassen und kleiner setzen
    return LayoutBuilder(
      builder: (context, box) {
        final tight = box.maxWidth < 150;
        final phone = MediaQuery.sizeOf(context).width < compactWidth;
        final compact = this.compact || tight || phone;
        return SurfaceCard(
          padding: EdgeInsets.all(compact ? Gap.md : Gap.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  if (icon != null && !tight) ...[
                    Container(
                      padding: EdgeInsets.all(phone ? 5 : 6),
                      decoration: BoxDecoration(
                        color: c.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(Radii.sm),
                      ),
                      child: Icon(icon, size: phone ? 14 : 16, color: c),
                    ),
                    const SizedBox(width: Gap.sm),
                  ],
                  Expanded(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: t.textTheme.labelMedium?.copyWith(color: muted, fontWeight: FontWeight.w600),
                    ),
                  ),
                  if (help != null) InfoHint(help!),
                ],
              ),
              SizedBox(height: compact ? Gap.sm : Gap.md),
              Wrap(
                // Umbruch statt Kuerzen: Der Wert bleibt immer sichtbar, Einheit/Aenderung rutschen notfalls nach unten
                spacing: 4,
                crossAxisAlignment: WrapCrossAlignment.end,
                children: [
                  Text(
                    value,
                    maxLines: 1,
                    style: (compact ? t.textTheme.titleLarge : t.textTheme.headlineMedium)?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: color,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                  if (unit != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 3),
                      child: Text(
                        unit!,
                        style: t.textTheme.bodySmall?.copyWith(color: muted, fontWeight: FontWeight.w600),
                      ),
                    ),
                  if (delta != null && delta!.round() != 0)
                    Padding(
                      padding: const EdgeInsets.only(left: Gap.xs, bottom: 3),
                      child: DeltaBadge(delta: delta!),
                    ),
                ],
              ),
              if (caption != null) ...[
                const SizedBox(height: Gap.xs),
                Text(
                  caption!,
                  maxLines: tight ? 3 : 2,
                  overflow: TextOverflow.ellipsis,
                  style: (tight ? t.textTheme.labelSmall : t.textTheme.bodySmall)?.copyWith(color: muted),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

/// Kleine Veraenderungsanzeige (z. B. +4 gegenueber Vorwoche).
class DeltaBadge extends StatelessWidget {
  const DeltaBadge({super.key, required this.delta});
  final num delta;

  @override
  Widget build(BuildContext context) {
    final up = delta > 0;
    final c = Theme.of(context).colorScheme.onSurfaceVariant;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(up ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded, size: 13, color: c),
        Text(
          '${delta.abs().round()}',
          style: Theme.of(context).textTheme.labelSmall?.copyWith(color: c, fontWeight: FontWeight.w700),
        ),
      ],
    );
  }
}

/// Fragezeichen-Symbol mit Erklaerung beim Antippen oder Darueberfahren.
class InfoHint extends StatelessWidget {
  const InfoHint(this.message, {super.key});
  final String message;

  @override
  Widget build(BuildContext context) => Tooltip(
    message: message,
    triggerMode: TooltipTriggerMode.tap,
    showDuration: const Duration(seconds: 6),
    preferBelow: false,
    constraints: const BoxConstraints(maxWidth: 280),
    child: Icon(Icons.help_outline_rounded, size: 16, color: Theme.of(context).colorScheme.outline),
  );
}

class Pill extends StatelessWidget {
  const Pill({super.key, required this.label, required this.color, this.icon, this.filled = false});
  final String label;
  final Color color;
  final IconData? icon;
  final bool filled;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
    decoration: BoxDecoration(
      color: filled ? color : color.withValues(alpha: 0.13),
      borderRadius: BorderRadius.circular(Radii.pill),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[Icon(icon, size: 14, color: filled ? Colors.white : color), const SizedBox(width: 4)],
        Text(
          label,
          style: Theme.of(context).textTheme.labelMedium
              ?.copyWith(color: filled ? Colors.white : color, fontWeight: FontWeight.w700),
        ),
      ],
    ),
  );
}

/// Datumskachel mit Wochentag und Tageszahl fuer Listen.
class DateBadge extends StatelessWidget {
  const DateBadge({super.key, required this.date, this.color});
  final DateTime date;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final c = color ?? t.colorScheme.primary;
    return Container(
      width: 48,
      height: 52,
      decoration: BoxDecoration(color: c.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(Radii.md)),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            DateFormat('E', 'de').format(date).toUpperCase(),
            style: t.textTheme.labelSmall?.copyWith(color: c, fontWeight: FontWeight.w700),
          ),
          Text(
            '${date.day}',
            style: t.textTheme.titleMedium?.copyWith(color: c, fontWeight: FontWeight.w800, height: 1.1),
          ),
        ],
      ),
    );
  }
}

/// Leerer Zustand oder Fehler mit Symbol, Text und optionaler Aktion.
class StatusMessage extends StatelessWidget {
  const StatusMessage({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.actionLabel,
    this.onAction,
    this.error = false,
  });
  final IconData icon;
  final String title;
  final String? message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final bool error;

  factory StatusMessage.error(String message, {VoidCallback? onRetry}) => StatusMessage(
    icon: Icons.cloud_off_rounded,
    title: 'Das hat nicht geklappt',
    message: message,
    actionLabel: onRetry == null ? null : 'Erneut versuchen',
    onAction: onRetry,
    error: true,
  );

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final c = error ? t.colorScheme.error : t.colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Gap.xxl, horizontal: Gap.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(Gap.lg),
            decoration: BoxDecoration(color: c.withValues(alpha: 0.1), shape: BoxShape.circle),
            child: Icon(icon, size: 32, color: c),
          ),
          const SizedBox(height: Gap.lg),
          Text(title, textAlign: TextAlign.center, style: t.textTheme.titleMedium),
          if (message != null) ...[
            const SizedBox(height: Gap.xs),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Text(
                message!,
                textAlign: TextAlign.center,
                style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
              ),
            ),
          ],
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: Gap.lg),
            error
                ? OutlinedButton.icon(onPressed: onAction, icon: const Icon(Icons.refresh), label: Text(actionLabel!))
                : FilledButton(onPressed: onAction, child: Text(actionLabel!)),
          ],
        ],
      ),
    );
  }
}

/// Grauer Platzhalter waehrend des Ladens.
class LoadingBlock extends StatelessWidget {
  const LoadingBlock({super.key, this.height = 120});
  final double height;

  @override
  Widget build(BuildContext context) => Container(
    height: height,
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surfaceContainer,
      borderRadius: BorderRadius.circular(Radii.lg),
    ),
  );
}

/// Farbige Linie fuer Diagramm-Legenden.
class LegendDot extends StatelessWidget {
  const LegendDot({super.key, required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
      ),
      const SizedBox(width: 6),
      Text(label, style: Theme.of(context).textTheme.labelMedium),
    ],
  );
}

/// Ordnet Kinder je nach Breite in mehreren Spalten an (Grid ohne feste Hoehe).
class ResponsiveGrid extends StatelessWidget {
  const ResponsiveGrid({super.key, required this.children, this.minItemWidth = 160, this.spacing = Gap.md});
  final List<Widget> children;
  final double minItemWidth;
  final double spacing;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) {
      final cols = ((c.maxWidth + spacing) / (minItemWidth + spacing)).floor().clamp(1, children.length);
      final w = (c.maxWidth - spacing * (cols - 1)) / cols;
      return Wrap(
        spacing: spacing,
        runSpacing: spacing,
        children: [for (final ch in children) SizedBox(width: w, child: ch)],
      );
    },
  );
}

/// Einordnung der Form (TSB) in verstaendliche Bereiche.
class FormStatus {
  const FormStatus(this.label, this.advice, this.color, this.icon);
  final String label;
  final String advice;
  final Color color;
  final IconData icon;

  static FormStatus of(num tsb) {
    if (tsb > 25) {
      return const FormStatus(
        'Sehr erholt',
        'Deine Ermüdung ist sehr niedrig. Ohne neue Belastung sinkt die Fitness langsam.',
        Color(0xFF0EA5E9),
        Icons.bedtime_outlined,
      );
    }
    if (tsb > 5) {
      return const FormStatus(
        'Frisch',
        'Gute Voraussetzungen für einen Wettkampf oder eine harte Einheit.',
        Color(0xFF16A34A),
        Icons.bolt_rounded,
      );
    }
    if (tsb > -10) {
      return const FormStatus(
        'Ausgeglichen',
        'Belastung und Erholung halten sich die Waage. Fitness bleibt etwa gleich.',
        Color(0xFF64748B),
        Icons.balance_rounded,
      );
    }
    if (tsb > -30) {
      return const FormStatus(
        'Produktives Training',
        'Optimaler Bereich für Fitnessaufbau. Achte auf Schlaf und Ernährung.',
        Color(0xFFF59E0B),
        Icons.trending_up_rounded,
      );
    }
    return const FormStatus(
      'Überlastet',
      'Hohe Ermüdung, erhöhtes Risiko für Übertraining. Plane Erholungstage ein.',
      Color(0xFFEF4444),
      Icons.warning_amber_rounded,
    );
  }
}

String greeting([DateTime? now]) {
  final h = (now ?? DateTime.now()).hour;
  if (h < 11) return 'Guten Morgen';
  if (h < 18) return 'Guten Tag';
  return 'Guten Abend';
}

/// Logo aus Verlaufskachel mit Fahrrad, optional mit Namen.
class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.showName = false, this.size = 40});
  final bool showName;
  final double size;

  @override
  Widget build(BuildContext context) {
    final mark = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(size * 0.3),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.brand, AppColors.accent],
        ),
      ),
      child: Icon(Icons.directions_bike_rounded, color: Colors.white, size: size * 0.58),
    );
    if (!showName) return mark;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        mark,
        const SizedBox(width: Gap.md),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Training',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800, height: 1),
            ),
            Text(
              'Planner',
              style: Theme.of(context).textTheme.titleMedium
                  ?.copyWith(fontWeight: FontWeight.w800, height: 1.1, color: Theme.of(context).colorScheme.primary),
            ),
          ],
        ),
      ],
    );
  }
}
