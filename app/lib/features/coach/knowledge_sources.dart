import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

/// Farbe der Evidenzstufe: A stark bis D Expertenpraxis (Beschriftungen kommen vom Backend).
Color evidenceColor(String? level) => switch (level) {
  'A' => const Color(0xFF16A34A),
  'B' => const Color(0xFF3B82F6),
  'C' => const Color(0xFFF59E0B),
  _ => const Color(0xFF64748B),
};

/// Quellen unter einer Coach-Antwort: eine Chip je gelesener Wissenskarte, belegte Aussagen zuerst.
class SourceChips extends StatelessWidget {
  const SourceChips({super.key, required this.sources});
  final List<Json> sources;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.menu_book_rounded, size: 14, color: t.colorScheme.onSurfaceVariant),
            const SizedBox(width: 6),
            Text(
              'Quellen',
              style: t.textTheme.labelSmall?.copyWith(
                color: t.colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        const SizedBox(height: Gap.xs),
        Wrap(
          spacing: Gap.sm,
          runSpacing: Gap.sm,
          children: [for (final s in sources) _SourceChip(source: s)],
        ),
      ],
    );
  }
}

class _SourceChip extends StatelessWidget {
  const _SourceChip({required this.source});
  final Json source;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final level = source['evidence'] as String?;
    final c = evidenceColor(level);
    final practice = source['practice'] == true;
    final tagged = source['tagged'] == true;
    return Tooltip(
      message:
          '${source['evidence_label'] ?? ''}${practice ? ' · Praxiswissen' : ''}${tagged ? '' : ' · nur nachgeschlagen'}',
      child: InkWell(
        borderRadius: BorderRadius.circular(Radii.pill),
        onTap: () => showKnowledgeSheet(context, source['slug'] as String),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 260),
          padding: const EdgeInsets.fromLTRB(4, 4, 10, 4),
          decoration: BoxDecoration(
            color: c.withValues(alpha: tagged ? 0.12 : 0.05),
            borderRadius: BorderRadius.circular(Radii.pill),
            border: Border.all(color: c.withValues(alpha: tagged ? 0.5 : 0.25)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 22,
                height: 22,
                alignment: Alignment.center,
                decoration: BoxDecoration(color: c, shape: BoxShape.circle),
                child: Text(
                  level ?? '?',
                  style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800),
                ),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  source['title'] as String? ?? '',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: t.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              if (source['contested'] == true) ...[
                const SizedBox(width: 4),
                Icon(Icons.balance_rounded, size: 14, color: t.colorScheme.onSurfaceVariant),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

Future<void> showKnowledgeSheet(BuildContext context, String slug) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (_) => DraggableScrollableSheet(
    expand: false,
    initialChildSize: 0.8,
    maxChildSize: 0.95,
    minChildSize: 0.4,
    builder: (context, controller) => _KnowledgeSheet(slug: slug, controller: controller),
  ),
);

const _populations = {'elite': 'Elite', 'trained': 'Trainierte', 'recreational': 'Freizeit'};
const _sexes = {'all': 'alle Geschlechter', 'female': 'Frauen', 'male': 'Männer'};

class _KnowledgeSheet extends ConsumerWidget {
  const _KnowledgeSheet({required this.slug, required this.controller});
  final String slug;
  final ScrollController controller;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = ref.watch(knowledgeCardProvider(slug));
    return card.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ListView(
        controller: controller,
        children: [StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(knowledgeCardProvider(slug)))],
      ),
      data: (c) => _CardBody(card: c, controller: controller),
    );
  }
}

class _CardBody extends StatelessWidget {
  const _CardBody({required this.card, required this.controller});
  final Json card;
  final ScrollController controller;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final level = card['evidence'] as String;
    final c = evidenceColor(level);
    final applies = Json.from((card['applies_to'] as Map?) ?? const {});
    final pops = [for (final p in (applies['population'] as List? ?? const [])) _populations[p] ?? '$p'];
    final sex = _sexes[applies['sex']] ?? '';
    final age = applies['age'] as String?;
    final positions = [for (final p in (card['positions'] as List? ?? const [])) Json.from(p as Map)];
    final sources = [for (final s in (card['sources'] as List? ?? const [])) Json.from(s as Map)];

    Widget heading(String text) => Padding(
      padding: const EdgeInsets.only(top: Gap.lg, bottom: Gap.xs),
      child: Text(text, style: t.textTheme.titleSmall),
    );

    return ListView(
      controller: controller,
      padding: const EdgeInsets.fromLTRB(Gap.xl, 0, Gap.xl, Gap.xxl),
      children: [
        Text(
          (card['topic_label'] as String).toUpperCase(),
          style: t.textTheme.labelMedium?.copyWith(
            color: t.colorScheme.primary,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.1,
          ),
        ),
        Text(card['title'] as String, style: t.textTheme.headlineSmall),
        const SizedBox(height: Gap.md),
        Wrap(
          spacing: Gap.sm,
          runSpacing: Gap.sm,
          children: [
            Pill(label: '$level · ${card['evidence_label']}', color: c, icon: Icons.verified_outlined),
            Pill(label: card['directness_label'] as String, color: muted, icon: Icons.person_search_outlined),
            if (card['contested'] == true) Pill(label: 'Umstritten', color: AppColors.tsb, icon: Icons.balance_rounded),
            if (card['safety'] == true)
              Pill(label: 'Sicherheitsrelevant', color: t.colorScheme.error, icon: Icons.health_and_safety_outlined),
          ],
        ),
        if (card['practice'] == true) ...[
          const SizedBox(height: Gap.md),
          Container(
            padding: const EdgeInsets.all(Gap.md),
            decoration: BoxDecoration(color: c.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(Radii.md)),
            child: Text(
              level == 'D'
                  ? 'Praxiswissen: beruht auf Erfahrung von Trainern, nicht auf kontrollierten Studien.'
                  : 'Schwache Evidenz: kleine oder beobachtende Studien. Als Orientierung nutzen, nicht als gesichert.',
              style: t.textTheme.bodySmall,
            ),
          ),
        ],
        heading('Empfehlung'),
        Text(card['recommendation'] as String, style: t.textTheme.bodyMedium?.copyWith(height: 1.45)),
        heading('Kurz gesagt'),
        Text(card['summary'] as String, style: t.textTheme.bodyMedium?.copyWith(color: muted, height: 1.45)),
        if (pops.isNotEmpty || sex.isNotEmpty || age != null) ...[
          heading('Gilt für'),
          Text(
            [if (pops.isNotEmpty) pops.join(', '), if (sex.isNotEmpty) sex, ?age].join(' · '),
            style: t.textTheme.bodyMedium,
          ),
        ],
        if ((card['caveats'] as String?) != null) ...[
          heading('Grenzen'),
          Text(card['caveats'] as String, style: t.textTheme.bodyMedium?.copyWith(height: 1.45)),
        ],
        if (positions.isNotEmpty) ...[
          heading('Positionen in der Forschung'),
          for (final p in positions)
            Container(
              margin: const EdgeInsets.only(bottom: Gap.sm),
              padding: const EdgeInsets.all(Gap.md),
              decoration: BoxDecoration(
                color: t.colorScheme.surfaceContainer.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(Radii.md),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(p['label'] as String, style: t.textTheme.titleSmall),
                  Text(p['summary'] as String, style: t.textTheme.bodySmall?.copyWith(color: muted)),
                ],
              ),
            ),
        ],
        heading('Quellen'),
        for (final s in sources) _SourceTile(source: s),
        const SizedBox(height: Gap.lg),
        Text(
          'Geprüft am ${DateFormat('d. MMMM yyyy', 'de').format(DateTime.parse(card['reviewed'] as String))}'
          '${card['review_overdue'] == true ? ' · Überprüfung fällig' : ''}',
          style: t.textTheme.labelSmall?.copyWith(color: muted),
        ),
      ],
    );
  }
}

class _SourceTile extends StatelessWidget {
  const _SourceTile({required this.source});
  final Json source;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final url = source['url'] as String?;
    final n = source['sample_n'] as num?;
    return Padding(
      padding: const EdgeInsets.only(bottom: Gap.sm),
      child: SurfaceCard(
        padding: const EdgeInsets.all(Gap.md),
        onTap: url == null ? null : () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(source['citation'] as String, style: t.textTheme.titleSmall),
                  Text(source['title'] as String, style: t.textTheme.bodySmall),
                  const SizedBox(height: 2),
                  Text(
                    [
                      if (source['journal'] != null) source['journal'] as String,
                      source['design_label'] as String,
                      if (n != null) 'n = ${n.round()}',
                      if (source['population'] != null) source['population'] as String,
                      if (source['basis'] == 'abstract') 'nur Abstract geprüft',
                    ].join(' · '),
                    style: t.textTheme.labelSmall?.copyWith(color: muted),
                  ),
                ],
              ),
            ),
            if (url != null) Icon(Icons.open_in_new_rounded, size: 18, color: t.colorScheme.primary),
          ],
        ),
      ),
    );
  }
}
