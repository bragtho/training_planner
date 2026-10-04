import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import 'rich_text.dart';

class CoachScreen extends ConsumerStatefulWidget {
  const CoachScreen({super.key});

  @override
  ConsumerState<CoachScreen> createState() => _CoachScreenState();
}

class _CoachScreenState extends ConsumerState<CoachScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <Json>[];
  bool _loading = true;
  bool _sending = false;
  bool _configured = true;
  String? _error;
  String? _lastFailed; // fuer "Erneut senden"

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final dio = ref.read(apiProvider).dio;
      final status = await dio.get('/coach/status');
      final r = await dio.get('/coach/messages');
      _configured = status.data['configured'] == true;
      _messages
        ..clear()
        ..addAll([for (final m in r.data as List) Json.from(m as Map)]);
    } catch (e) {
      _error = errorMessage(e);
    } finally {
      if (mounted) setState(() => _loading = false);
      _toBottom();
    }
  }

  void _toBottom() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.animateTo(_scroll.position.maxScrollExtent,
              duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
        }
      });

  /// Sendet eine Nachricht oder startet eine Schnellaktion; die Antwort kann bis zu einigen Minuten dauern.
  Future<void> _send({String? text, String? quick}) async {
    if (_sending) return;
    final shown = text ?? (quick == 'plan_week' ? 'Woche planen' : 'Letztes Training auswerten');
    setState(() {
      _sending = true;
      _error = null;
      _lastFailed = null;
      _messages.add({'id': -1, 'role': 'user', 'text': shown, 'actions': <String>[]});
    });
    _toBottom();
    try {
      final dio = ref.read(apiProvider).dio;
      final r = await (quick != null
          ? dio.post('/coach/quick', data: {'action': quick}, options: Options(receiveTimeout: const Duration(minutes: 6)))
          : dio.post('/coach/chat', data: {'message': text}, options: Options(receiveTimeout: const Duration(minutes: 6))));
      final out = [for (final m in r.data as List) Json.from(m as Map)];
      if (!mounted) return;
      setState(() {
        _messages.removeLast(); // vorlaeufige Nachricht durch gespeicherte ersetzen
        _messages.addAll(out);
      });
      if ((out.last['actions'] as List).isNotEmpty) {
        ref
          ..invalidate(calendarProvider)
          ..invalidate(pmcProvider);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _messages.removeLast();
        _error = errorMessage(e);
        _lastFailed = text;
        if (quick == null && text != null) _input.text = text;
      });
    } finally {
      if (mounted) setState(() => _sending = false);
      _toBottom();
    }
  }

  Future<void> _clear() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Verlauf löschen?'),
        content: const Text('Das Gespräch mit dem Coach wird gelöscht. Geplante Trainings bleiben bestehen.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Löschen')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(apiProvider).dio.delete('/coach/messages');
      if (mounted) setState(_messages.clear);
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
  }

  void _submit() {
    final t = _input.text.trim();
    if (t.isEmpty || _sending) return;
    _input.clear();
    _send(text: t);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Coach'),
        actions: [
          IconButton(
              tooltip: 'Verlauf löschen',
              onPressed: _messages.isEmpty || _sending ? null : _clear,
              icon: const Icon(Icons.delete_sweep_outlined)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 800),
                child: Column(children: [
                  if (!_configured)
                    Container(
                      width: double.infinity,
                      color: t.colorScheme.errorContainer,
                      padding: const EdgeInsets.all(12),
                      child: const Text(
                          'Der Coach ist noch nicht eingerichtet: ANTHROPIC_API_KEY fehlt in backend/.env.'),
                    ),
                  Expanded(
                    child: _messages.isEmpty
                        ? const _Intro()
                        : ListView.builder(
                            controller: _scroll,
                            padding: const EdgeInsets.all(16),
                            itemCount: _messages.length + (_sending ? 1 : 0),
                            itemBuilder: (_, i) => i == _messages.length
                                ? const _Thinking()
                                : _Bubble(m: _messages[i]),
                          ),
                  ),
                  if (_error != null)
                    Container(
                      width: double.infinity,
                      color: t.colorScheme.errorContainer,
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: Row(children: [
                        Expanded(child: Text(_error!)),
                        if (_lastFailed != null)
                          TextButton(
                              onPressed: () {
                                _input.clear();
                                _send(text: _lastFailed);
                              },
                              child: const Text('Erneut senden')),
                      ]),
                    ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Wrap(spacing: 8, children: [
                        ActionChip(
                          avatar: const Icon(Icons.edit_calendar, size: 18),
                          label: const Text('Woche planen'),
                          onPressed: _sending || !_configured ? null : () => _send(quick: 'plan_week'),
                        ),
                        ActionChip(
                          avatar: const Icon(Icons.fact_check_outlined, size: 18),
                          label: const Text('Letztes Training auswerten'),
                          onPressed: _sending || !_configured ? null : () => _send(quick: 'review_last'),
                        ),
                      ]),
                    ),
                  ),
                  SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(children: [
                        Expanded(
                          child: TextField(
                            controller: _input,
                            enabled: _configured,
                            minLines: 1,
                            maxLines: 5,
                            maxLength: 4000,
                            buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                            textInputAction: TextInputAction.send,
                            onSubmitted: (_) => _submit(),
                            decoration: const InputDecoration(
                              hintText: 'Frag Deinen Coach …',
                              border: OutlineInputBorder(),
                              isDense: true,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        IconButton.filled(
                          tooltip: 'Senden',
                          onPressed: _sending || !_configured ? null : _submit,
                          icon: const Icon(Icons.send),
                        ),
                      ]),
                    ),
                  ),
                ]),
              ),
            ),
    );
  }
}

class _Intro extends StatelessWidget {
  const _Intro();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.psychology, size: 64, color: t.colorScheme.primary),
          const SizedBox(height: 16),
          Text('Dein KI-Coach', style: t.textTheme.titleLarge),
          const SizedBox(height: 8),
          const Text(
            'Er kennt Dein Profil, Deine Fitness und Deinen Kalender. Frag ihn nach Training, Erholung oder Ziel-Events, '
            'oder lass ihn Deine Woche planen. Geplante Trainings landen direkt im Kalender.',
            textAlign: TextAlign.center,
          ),
        ]),
      ),
    );
  }
}

class _Thinking extends StatelessWidget {
  const _Thinking();

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Row(children: [
          SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          SizedBox(width: 12),
          Text('Coach denkt nach …'),
        ]),
      );
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.m});
  final Json m;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final mine = m['role'] == 'user';
    final actions = [for (final a in (m['actions'] as List? ?? const [])) a as String];
    final bg = mine ? t.colorScheme.primaryContainer : t.colorScheme.surfaceContainerHighest;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.85 > 640 ? 640 : MediaQuery.sizeOf(context).width * 0.85),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(14)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SelectableText.rich(simpleMarkdown(m['text'] as String, t.textTheme.bodyMedium!)),
          if (actions.isNotEmpty) ...[
            const SizedBox(height: 8),
            for (final a in actions)
              InkWell(
                onTap: () => context.go('/calendar'),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.check_circle, size: 16, color: t.colorScheme.primary),
                    const SizedBox(width: 6),
                    Flexible(child: Text(a, style: t.textTheme.labelMedium?.copyWith(color: t.colorScheme.primary))),
                  ]),
                ),
              ),
          ],
        ]),
      ),
    );
  }
}
