import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

/// Zeigt, was sich der Coach ueber den Athleten gemerkt hat, und erlaubt das Loeschen einzelner Eintraege.
class CoachMemoryCard extends ConsumerWidget {
  const CoachMemoryCard({super.key});

  Future<void> _forget(BuildContext context, WidgetRef ref, CoachMemory m) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(apiProvider).dio.delete('/coach/memories/${m.id}');
      ref
        ..invalidate(coachMemoriesProvider)
        ..invalidate(formHintProvider);
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessage(e))));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final muted = t.colorScheme.onSurfaceVariant;
    final memories = ref.watch(coachMemoriesProvider);
    return SurfaceCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(
            title: 'Was der Coach über Dich weiß',
            subtitle: 'Merkt er sich selbst aus Euren Gesprächen',
          ),
          memories.when(
            loading: () => const LoadingBlock(height: 60),
            error: (e, _) => StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(coachMemoriesProvider)),
            data: (list) => list.isEmpty
                ? Text(
                    'Noch nichts gespeichert. Erzähl dem Coach von Deiner Saisonphase, Vorlieben oder Einschränkungen, '
                    'er merkt sich das Wichtige von allein.',
                    style: t.textTheme.bodyMedium?.copyWith(color: muted),
                  )
                : Column(
                    children: [
                      for (final m in list)
                        Container(
                          margin: const EdgeInsets.only(bottom: Gap.sm),
                          padding: const EdgeInsets.only(left: Gap.md),
                          decoration: BoxDecoration(
                            color: t.colorScheme.surfaceContainer.withValues(alpha: 0.6),
                            borderRadius: BorderRadius.circular(Radii.md),
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(top: 12, right: Gap.sm),
                                child: Icon(Icons.auto_awesome, size: 16, color: t.colorScheme.primary),
                              ),
                              Expanded(
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(vertical: 10),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(m.text, style: t.textTheme.bodyMedium),
                                      if (m.validUntil != null)
                                        Text(
                                          'gilt bis ${DateFormat('d. MMMM yyyy', 'de').format(m.validUntil!)}',
                                          style: t.textTheme.labelSmall?.copyWith(color: muted),
                                        ),
                                    ],
                                  ),
                                ),
                              ),
                              IconButton(
                                tooltip: 'Vergessen',
                                onPressed: () => _forget(context, ref, m),
                                icon: const Icon(Icons.close_rounded, size: 18),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
