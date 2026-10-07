import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

/// Hat der Coach die FTP automatisch angehoben, steht hier was und warum, mit Moeglichkeit zum Rueckgaengigmachen.
/// Danach ruhen automatische Anhebungen 28 Tage.
class FtpChangeCard extends ConsumerStatefulWidget {
  const FtpChangeCard({super.key, required this.change});
  final Json change;

  @override
  ConsumerState<FtpChangeCard> createState() => _FtpChangeCardState();
}

class _FtpChangeCardState extends ConsumerState<FtpChangeCard> {
  bool _busy = false;

  Future<void> _undo() async {
    final old = (widget.change['old_ftp'] as num).round();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('FTP zurücksetzen?'),
        content: Text('Die FTP geht zurück auf $old W. Automatische Anhebungen ruhen danach 28 Tage.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Zurücksetzen')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _busy = true);
    try {
      await ref.read(apiProvider).dio.post('/profile/ftp/undo');
      ref
        ..invalidate(profileProvider)
        ..invalidate(pmcProvider)
        ..invalidate(calendarProvider);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(errorMessage(e))));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final c = widget.change;
    final date = DateFormat('d. MMMM', 'de').format(DateTime.parse(c['date'] as String));
    final reason = (c['reason'] as String?)?.trim();
    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(color: AppColors.power.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.sm)),
            child: const Icon(Icons.bolt_rounded, size: 16, color: AppColors.power),
          ),
          const SizedBox(width: Gap.sm),
          Expanded(child: Text('FTP vom Coach angepasst', style: t.textTheme.titleMedium)),
        ]),
        const SizedBox(height: Gap.md),
        Text('${(c['old_ftp'] as num).round()} → ${(c['new_ftp'] as num).round()} W am $date',
            style: t.textTheme.titleLarge?.copyWith(color: AppColors.power)),
        if (reason != null && reason.isNotEmpty) ...[
          const SizedBox(height: Gap.xs),
          Text(reason, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        ],
        if (c['can_undo'] == true) ...[
          const SizedBox(height: Gap.md),
          OutlinedButton.icon(
            onPressed: _busy ? null : _undo,
            icon: _busy
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.undo_rounded, size: 18),
            label: const Text('Rückgängig'),
          ),
        ],
      ]),
    );
  }
}
